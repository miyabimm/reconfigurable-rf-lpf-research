"""Post-search dispatch and fail-closed checks; no production dense run."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from test_phase2_problem_seed import make, seed
from lpf.phase2_models.limited_candidate_evidence import _identity
from lpf.phase2_models.post_search_validation import validate_post_search, _forward, _independent
from lpf.phase2_models.api import NominalCircuit
from lpf.phase2_models.evaluation_cost import SampleBudgetCost, SampleBudgetExceeded
from lpf.phase2_models.staged_optimization import run_c1_staged


class PostSearchTests(unittest.TestCase):
    def setUp(self):
        p, self.x = make('RF-T008', 4)
        self.c = p.circuit
        ident = _identity(self.c, self.x)
        keys = ('git_head', 'source_tree_sha256', 'source_worktree_dirty', 'input_sha256', 'environment')
        self.source = {k: ident[k] for k in keys}
        def optimizer(problem, vector, maxiter, target):
            return vector, dict(success=True, status=0, message='mock', nit=0, nfev=0)
        self.raw = run_c1_staged(self.c, seed(p, self.x), coarse_points=1, fine_points=2,
            optimize_stage=optimizer, source_provenance=self.source,
            cost_meter=SampleBudgetCost(1000))
        self.budgets = dict(separate17=476, dense1001=28028,
                            independent_forward84=84, independent_mna84=84)

    def invoke(self, **kwargs):
        snapshots = []
        result = validate_post_search(self.c, self.x, optimization_record=self.raw,
            source_provenance=self.source, budgets=kwargs.pop('budgets', self.budgets),
            run_dense=kwargs.pop('run_dense', True), run_independent=kwargs.pop('run_independent', True),
            record_sink=snapshots.append, **kwargs)
        return result, snapshots

    def test_real_17_grid_and_budget_without_dense(self):
        result, snapshots = self.invoke(run_dense=False, run_independent=False)
        self.assertIn(result['separate17']['state'], ('pass', 'fail'))
        self.assertEqual(len(result['separate17']['segments']), 28)
        self.assertEqual(result['evaluation_cost']['separate17']['frequency_samples_requested'], 476)
        self.assertEqual(result['dense1001']['state'], 'not_run')
        self.assertEqual(snapshots[0]['optimization_record'], self.raw)
        self.assertEqual(snapshots[0]['separate17']['state'], 'not_run')
        self.assertEqual(snapshots[-1], result)
        budgets = dict(self.budgets, separate17=475)
        result, _ = self.invoke(budgets=budgets)
        self.assertEqual(result['separate17']['state'], 'budget_exhausted')
        self.assertEqual(result['evaluation_cost']['separate17']['frequency_samples_requested'], 0)
        self.assertEqual(result['dense1001']['state'], 'not_run')

    def test_raw_mandatory_and_guard_thresholds_are_distinct(self):
        base = self.c.forward_evaluator(17)
        for attenuation, state, guard in ((29.999999999, 'fail', False),
                                          (30.003, 'pass', False), (30.005, 'pass', True)):
            values = np.where(base.role == 0, 1., attenuation)
            fake = SimpleNamespace(f=base.f, role=base.role, setting=base.setting,
                                   segment=base.segment, il=lambda x: values)
            with patch.object(NominalCircuit, 'forward_evaluator', return_value=fake):
                result = _forward(self.c, self.x, 17, SampleBudgetCost(476), 30.)
            self.assertEqual(result['state'], state)
            self.assertEqual(result['guard_achieved'], guard)
            self.assertEqual(result['min_h2_db'], attenuation)

    def test_real_independent_84_and_budget(self):
        forward, independent = SampleBudgetCost(84), SampleBudgetCost(84)
        result = _independent(self.c, self.x, forward, independent)
        self.assertEqual(result['state'], 'pass')
        self.assertEqual(len(result['samples']), 84)
        self.assertEqual(result['mna_dimension'], 9)
        self.assertEqual(forward.frequency_samples_requested, 84)
        self.assertEqual(independent.frequency_samples_requested, 84)
        with self.assertRaises(SampleBudgetExceeded):
            _independent(self.c, self.x, SampleBudgetCost(84), SampleBudgetCost(0))

    def test_explicit_dispatch_and_blocking(self):
        for state17, state1001, expect in [('fail', 'pass', []), ('pass', 'fail', []), ('pass', 'pass', [True])]:
            with self.subTest(state17=state17, state1001=state1001):
                called = []
                def fake_forward(c, x, points, meter, mandatory):
                    return {'state': state17 if points == 17 else state1001}
                def fake_independent(*args):
                    called.append(True)
                    return {'state': 'pass'}
                with patch('lpf.phase2_models.post_search_validation._forward', side_effect=fake_forward), \
                     patch('lpf.phase2_models.post_search_validation._independent', side_effect=fake_independent):
                    result, _ = self.invoke()
                self.assertEqual(called, expect)
                self.assertEqual(result['independent84']['state'], 'pass' if expect else 'not_run')
                self.assertFalse(result['rf_compliance_certified'])

    def test_provenance_and_sink_fail_closed(self):
        wrong = self.x.copy()
        wrong[0] += .01
        with self.assertRaisesRegex(ValueError, 'provenance mismatch'):
            validate_post_search(self.c, wrong, optimization_record=self.raw,
                source_provenance=self.source, budgets=self.budgets, run_dense=True,
                run_independent=True, record_sink=lambda _: None)
        with self.assertRaisesRegex(RuntimeError, 'sink'):
            validate_post_search(self.c, self.x, optimization_record=self.raw,
                source_provenance=self.source, budgets=self.budgets, run_dense=False,
                run_independent=False, record_sink=lambda _: (_ for _ in ()).throw(RuntimeError('sink')))


if __name__ == '__main__':
    unittest.main()
