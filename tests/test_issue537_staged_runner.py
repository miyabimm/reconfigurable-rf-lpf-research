"""Staged orchestration, reservations and STOP propagation without RF forwards."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.search import _staged_runner as staged
from lpf.search.plan import ROOT
from lpf.search.source import source_identity
from lpf.search.storage import canonical, sha, vector_sha

sys.path.insert(0, str(ROOT/'scripts'))
import run_rf_search

FIXTURE = ROOT/'tests/fixtures/issue537-staged-smoke.json'


def config():
    return json.loads(FIXTURE.read_text())


def candidate(seed, vector, phase, objective=1.):
    return dict(seed=seed, vector=vector, vector_sha256=vector_sha(vector), terminal_margins=[float(seed)],
                terminal_grid_sha256=phase, search_objective=objective, converged=True,
                worst_il_db=1., min_h2_db=2., min_h3_db=3., performance_feasible=False,
                provenance=dict(phase=phase, job=str(seed), plan_sha256='plan', receipt={}, source_sha256='source'))


class StagedRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = config()
        cls.manifest, cls.profile = staged._preflight(cls.cfg, ROOT, source_identity(ROOT))

    def test_preflight_exact_reservations_and_budget_before_run(self):
        self.assertEqual(self.manifest['maximum_cost'], dict(rf_forwards=48, rf_samples=63378, independent_mna_samples=182))
        cfg = copy.deepcopy(self.cfg)
        cfg['budget']['rf_samples'] -= 1
        with tempfile.TemporaryDirectory(prefix='issue537-budget-') as tmp, \
             patch.object(staged.development, 'run') as lower:
            output = Path(tmp)/'run'
            with self.assertRaisesRegex(ValueError, 'global budget'):
                staged.run(cfg, output, root=ROOT)
            lower.assert_not_called()
            self.assertEqual(json.loads((output/'summary.json').read_text())['status'], 'STOP')

    def _control(self, *, discovery=2, failure=None):
        cfg = copy.deepcopy(self.cfg)
        initial = self.manifest['initial_starts']
        calls = []
        def phase(name, inputs, *args):
            calls.append((name, copy.deepcopy(inputs)))
            if name == failure:
                raise ValueError('synthetic STOP')
            rows = [candidate(x['seed'], x['vector'], name, objective=(1. if i < discovery else 2e12))
                    for i, x in enumerate(inputs)]
            return rows
        with tempfile.TemporaryDirectory(prefix='issue537-control-') as tmp, \
             patch.object(staged, '_preflight', return_value=(copy.deepcopy(self.manifest), self.profile)), \
             patch.object(staged, '_run_phase', side_effect=phase), \
             patch.object(staged, '_ledger', return_value={'total': {k: {'unknown': 0} for k in staged.COSTS}}):
            output = Path(tmp)/'run'
            if failure:
                with self.assertRaisesRegex(ValueError, 'synthetic STOP'):
                    staged.run(cfg, output, root=ROOT)
                result = json.loads((output/'summary.json').read_text())
            else:
                result = staged.run(cfg, output, root=ROOT)
        return result, calls, initial

    def test_all_candidates_inherited_and_final(self):
        result, calls, initial = self._control()
        self.assertEqual([n for n, _ in calls], list(staged.PHASES))
        self.assertEqual([len(i) for _, i in calls], [3, 2, 2, 2])
        self.assertEqual([x['seed'] for x in calls[1][1]], [2001, 2002])
        for (_, prev), (_, current) in zip(calls, calls[1:]):
            self.assertTrue({r['vector_sha256'] for r in current} <= {r['vector_sha256'] for r in prev})
        self.assertTrue(result['reproducible'])
        self.assertEqual(len(result['phases']['refinement']['candidates']), 2)
        self.assertEqual(calls[0][1][0]['vector_sha256'], initial[0]['vector_sha256'])

    def test_zero_and_insufficient_candidates(self):
        result, calls, _ = self._control(discovery=0)
        self.assertEqual(result['status'], 'no_promising_candidate')
        self.assertEqual([n for n, _ in calls], ['screening', 'discovery'])
        self.assertFalse(result['reproducible'])
        result, calls, _ = self._control(discovery=1)
        self.assertEqual([len(i) for _, i in calls], [3, 2, 1, 1])
        self.assertFalse(result['reproducible'])

    def test_exception_stops_later_phases(self):
        result, calls, _ = self._control(failure='discovery')
        self.assertEqual(result['status'], 'STOP')
        self.assertEqual([n for n, _ in calls], ['screening', 'discovery'])
        self.assertEqual(result['phases']['exploitation']['status'], 'not_started')

    def test_unverified_completed_receipt_stops_before_next_phase(self):
        calls = []
        def phase(name, inputs, *args):
            calls.append(name)
            return [candidate(x['seed'], x['vector'], name) for x in inputs]
        def ledger(summary, *args, **kwargs):
            bad = summary['phases']['screening']['status'] == 'completed'
            return {'total': {k: {'unknown': int(bad)} for k in staged.COSTS}}
        with tempfile.TemporaryDirectory(prefix='issue537-unverified-') as tmp, \
             patch.object(staged, '_preflight', return_value=(copy.deepcopy(self.manifest), self.profile)), \
             patch.object(staged, '_run_phase', side_effect=phase), patch.object(staged, '_ledger', side_effect=ledger):
            output = Path(tmp)/'run'
            with self.assertRaisesRegex(ValueError, 'unverified'):
                staged.run(self.cfg, output, root=ROOT)
            saved = json.loads((output/'summary.json').read_text())
        self.assertEqual(calls, ['screening'])
        self.assertEqual(saved['status'], 'STOP')
        self.assertEqual(saved['ledger']['total']['rf_forwards']['unknown'], 1)

    def test_negative_solver_status_is_stop_not_nonconvergence(self):
        vector = [1.]
        data = dict(jobs=[dict(seed=1, arm='baseline', vector_sha256=vector_sha(vector))],
                    grids=dict(terminal=dict(sha256='grid')))
        checked = dict(scientific_status='not_converged', actual={}, released={}, raw={})
        job = dict(seed=1, arm='baseline', status='completed', raw_path='job-0001', **checked)
        job['raw'] = {'receipt.json': {}}
        checked['raw'] = job['raw']
        state = dict(status='completed', jobs=[job], plan_sha256=sha(data), plan_raw={}, source_sha256='s')
        result = dict(steps=[dict(stop_reason='solver_failure', local_run_details=[dict(status=-1)])],
                      terminal=dict(candidates=[{}]))
        with tempfile.TemporaryDirectory(prefix='issue537-stop-') as tmp:
            directory = Path(tmp); (directory/'job-0001').mkdir()
            (directory/'run.json').write_text(canonical(state))
            (directory/'plan.json').write_text(canonical(data))
            state['plan_raw'] = staged.development._bytes_info((directory/'plan.json').read_bytes())
            (directory/'run.json').write_text(canonical(state))
            (directory/'job-0001/result.json').write_text(canonical(result))
            with patch.object(staged.development, '_verify_receipt', return_value=checked):
                with self.assertRaisesRegex(ValueError, 'solver_failure'):
                    staged._load_candidates(directory, state, data, self.profile, 'screening')

    def test_receipt_candidate_uses_profile_regions(self):
        vector = [1.]
        grid = dict(sha256='grid', frequency_hz=list(range(28)), setting=[0]*28, segment=list(range(28)))
        data = dict(jobs=[dict(seed=1, arm='baseline', vector=vector, vector_sha256=vector_sha(vector))],
                    grids=dict(terminal=grid))
        checked = dict(scientific_status='not_converged', actual={}, released={}, raw={'receipt.json': {}})
        job = dict(seed=1, arm='baseline', status='completed', job_id='job-0001', raw_path='job-0001', **checked)
        state = dict(status='completed', jobs=[job], plan_sha256=sha(data), plan_raw={}, source_sha256='s')
        step = dict(stop_reason='evaluation_budget_exhausted', local_run_details=[dict(status=0)],
                    solver_result=dict(x=vector, objective=3.), converged=False)
        terminal = dict(vector=vector, vector_sha256=vector_sha(vector), signed_margins_db=[1.]*28,
                        response=dict(grid={k: grid[k] for k in ('frequency_hz', 'setting', 'segment')},
                                      il_db=list(map(float, range(28)))), performance_feasible=False)
        result = dict(steps=[step], terminal=dict(candidates=[terminal]),
                      terminal_grid_sha256='grid', initial_vector_sha256=vector_sha(vector))
        with tempfile.TemporaryDirectory(prefix='issue537-read-') as tmp:
            directory = Path(tmp); (directory/'job-0001').mkdir()
            (directory/'plan.json').write_text(canonical(data))
            state['plan_raw'] = staged.development._bytes_info((directory/'plan.json').read_bytes())
            (directory/'run.json').write_text(canonical(state))
            (directory/'job-0001/result.json').write_text(canonical(result))
            with patch.object(staged.development, '_verify_receipt', return_value=checked):
                row = staged._load_candidates(directory, state, data, self.profile, 'screening')[0]
        records = self.profile.records
        self.assertEqual(row['worst_il_db'], max(i for i, r in enumerate(records) if r['type'] == 'pass'))
        self.assertEqual(row['min_h2_db'], min(i for i, r in enumerate(records) if r['region'] == 'H2'))
        self.assertEqual(row['min_h3_db'], min(i for i, r in enumerate(records) if r['region'] == 'H3'))
        self.assertEqual(row['provenance']['receipt'], {})

    def test_staged_cli_exit_codes(self):
        args = ['develop-staged', '--config', str(FIXTURE), '--output', '/tmp/unused-issue537']
        with patch.object(staged, 'run', return_value=dict(status='completed', reproducible=True)):
            self.assertEqual(run_rf_search.main(args), 0)
        with patch.object(staged, 'run', return_value=dict(status='no_promising_candidate', reproducible=False)):
            self.assertEqual(run_rf_search.main(args), 4)
        with patch.object(staged, 'run', side_effect=ValueError('bad')):
            self.assertEqual(run_rf_search.main(args), 2)
        with self.assertRaises(SystemExit) as error:
            run_rf_search.main(args + ['--starts', 'not-allowed'])
        self.assertEqual(error.exception.code, 2)

    def test_unknown_not_released(self):
        manifest = copy.deepcopy(self.manifest)
        summary = dict(budget=self.cfg['budget'], phases={n: dict(status='not_started') for n in staged.PHASES})
        summary['phases']['screening']['status'] = 'running'
        with tempfile.TemporaryDirectory(prefix='issue537-ledger-') as tmp:
            ledger = staged._ledger(summary, manifest, Path(tmp))['total']
        for k in staged.COSTS:
            self.assertEqual(ledger[k]['unknown'], manifest['reservations']['screening']['maximum'][k])
            self.assertEqual(ledger[k]['released'], 0)
            self.assertEqual(sum(ledger[k][n] for n in ('completed', 'released', 'unknown', 'not_started')),
                             ledger[k]['maximum'])
        summary['phases']['screening']['status'] = 'completed'
        with tempfile.TemporaryDirectory(prefix='issue537-missing-ledger-') as tmp:
            final = staged._ledger(summary, manifest, Path(tmp), normal_end=True)['total']
        for k in staged.COSTS:
            self.assertEqual(final[k]['unknown'], manifest['reservations']['screening']['maximum'][k])


if __name__ == '__main__':
    unittest.main()
