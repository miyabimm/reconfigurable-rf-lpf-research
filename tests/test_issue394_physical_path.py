"""Issue 394: bounded development-path checks, not an RF benchmark or EXP."""
import copy
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import test_issue315_fixed_stage as fixtures
from lpf.rf_core.coupled_lc import CircuitValues, CoupledLCTopology
from lpf.rf_core.numerical_diagnostics import CircuitNumericalError
from lpf.topology_management import InductorTree
from lpf.search._worker_next import MinimalWorker
from lpf.search.component_constraints import validate_values
from lpf.search.plan import ROOT
from lpf.search.storage import vector_sha
from lpf.search.worker import freeze_development_job
from lpf.search._window_evaluation import WindowJobEvaluation
from lpf.search.evaluation import FixedStageEvaluation
from pathlib import Path


class PhysicalPathTests(unittest.TestCase):
    setUp = fixtures.FixedStageTests.setUp
    setup_model = fixtures.FixedStageTests.setup_model

    def prepare(self):
        def configure(c):
            c['arms'][0]['steps'][0].update(solver='hybrid', aggregation='sum',
                options=dict(maxiter=3, max_restarts=0, max_evaluations=3, restart_sigma=.1))
        plan, d, p, x = self.setup_model('RF-T008', mutate=configure)
        with patch('lpf.search._worker_next.physical_bounds', wraps=__import__(
                'lpf.search.component_constraints', fromlist=['physical_bounds']).physical_bounds) as bounds:
            w = MinimalWorker(plan, d, p, 'demo', 23, x, vector_sha(x), root=ROOT)
            self.assertEqual(bounds.call_count, 1)
        return plan, d, p, x, w

    def test_box_matches_full_check_at_each_boundary_and_rejects_bad_inputs(self):
        _, d, p, x, w = self.prepare()
        for i, (lo, hi) in enumerate(w.bounds):
            for endpoint in (lo, hi):
                v = x.copy(); v[i] = endpoint
                with self.subTest(i=i, endpoint=endpoint):
                    self.assertTrue(validate_values(d, w.model.schema, v, p)['component_policy_pass'])
                    np.testing.assert_array_equal(w._check_box(v), v)
            for outside in (np.nextafter(lo, -np.inf), np.nextafter(hi, np.inf)):
                v = x.copy(); v[i] = outside
                with self.subTest(i=i, outside=outside), self.assertRaises(ValueError):
                    w.evaluate(v)
        for bad in (x[:-1], x.reshape(1, -1), [True]*len(x), [str(z) for z in x],
                    np.full_like(x, np.nan), np.full_like(x, np.inf)):
            with self.assertRaises(ValueError):
                w.evaluate(bad)

    def test_solver_callback_only_core_spd_and_boundary_checks(self):
        _, _, _, x, w = self.prepare()
        eig = np.linalg.eigvalsh
        with patch('lpf.search._worker_next.validate_values', side_effect=AssertionError('duplicate validation')), \
             patch('lpf.search._worker_next.physical_bounds', side_effect=AssertionError('rebuilt bounds')), \
             patch('lpf.rf_core.nominal_inductors.check_nominal_inductors', side_effect=AssertionError('duplicate SPD')), \
             patch('numpy.linalg.eigvalsh', wraps=eig) as eigen:
            residual = w._solver_residuals(x)
            self.assertTrue(np.all(np.isfinite(residual)))
            self.assertEqual(eigen.call_count, 1)
        w.bounds = list(w.bounds)
        w.bounds[0] = (w.bounds[0][0] - 1, w.bounds[0][1])
        with patch('lpf.search._worker_next.hybrid_minimize') as solver:
            with self.assertRaises(ValueError): w.solve()
            solver.assert_not_called()

    def test_solver_output_boundary_and_source_mismatch(self):
        plan, d, p, x, w = self.prepare()
        bad = x.copy(); bad[0] = w.bounds[0][1] + 1
        with patch('lpf.search._worker_next.hybrid_minimize', return_value=SimpleNamespace(
                best_x=bad, runs=[])):
            with self.assertRaises(ValueError): w.solve()
        with self.assertRaises(ValueError):
            MinimalWorker(plan, replace(d, physical_order=tuple(reversed(d.physical_order))),
                          p, 'demo', 23, x, vector_sha(x), root=ROOT)
        changed = copy.deepcopy(p); changed['source_ohms']['real'] += 1
        with self.assertRaises(ValueError):
            MinimalWorker(plan, d, changed, 'demo', 23, x, vector_sha(x), root=ROOT)

    def test_window_real_forward_matches_detailed_stage_and_evidence(self):
        plan, d, p, x, _ = self.prepare()
        spec = freeze_development_job(plan, d, p, 'demo', 23, x, storage_mode='window100')
        with patch.object(WindowJobEvaluation, '_validate_checkpoint'):
            window = WindowJobEvaluation(plan, d, p, 'demo', Path(self.raw.name)/'window.json',
                                         spec, root=ROOT)
        old = FixedStageEvaluation(plan, d, p, 'demo', 'coarse', Path(self.raw.name)/'old.json')
        window.activate('demo/coarse', 'demo/coarse')
        reference = old.evaluate(x)
        actual = window.evaluate(x)
        for field in ('worst_il_db', 'mandatory_g', 'strict_feasible',
                      'max_violation_db', 'sum_violation_db'):
            self.assertEqual(actual['assessment'][field], reference['assessment'][field])
        best = window.scientific_best['demo/coarse']
        self.assertEqual(best['physical_checks'], old.rows[-1]['physical_checks'])
        self.assertEqual((window.requested, window.completed), (old.requested, old.completed))
        window.finish()

    def test_direct_core_spd_threshold_without_search(self):
        topology = CoupledLCTopology(InductorTree(3, ((0, 1), (1, 2))),
                                     ((0, 1),), (30., 30.), (), ())
        def values(k):
            return CircuitValues((1., 1.), (k,), ((),)*6)
        topology.matrices(values(1. - 3e-12))
        for k in (1. - 1e-12, 1., 1.01):
            with self.subTest(k=k), self.assertRaises(CircuitNumericalError) as raised:
                topology.matrices(values(k))
            self.assertEqual(raised.exception.code, 'mutual_not_spd')


if __name__ == '__main__':
    unittest.main()
