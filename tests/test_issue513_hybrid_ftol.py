"""Hybrid ftol is opt-in and reaches L-BFGS-B through the existing runner."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from lpf.optimizers.hybrid import hybrid_minimize
from lpf.search import _development_runner as runner
from lpf.search.development_plan import solver_options
from lpf.search.plan import validate_solver
from lpf.timing import TimerCollector


class HybridFtolTests(unittest.TestCase):
    def test_plan_validation_and_default(self):
        step = dict(solver='hybrid', aggregation='sum', options={'max_search_forwards': 2})
        validate_solver(step)
        self.assertEqual(solver_options(step), dict(max_evaluations=2, restart_sigma=.1,
                                                   batch_fd=True, partial_fd=True))
        step['options']['ftol'] = 1e-7
        validate_solver(step)
        self.assertEqual(solver_options(step)['ftol'], 1e-7)
        for value in (None, 0, -1, float('nan'), float('inf'), True, '1', 10**1000):
            step['options']['ftol'] = value
            with self.subTest(value=str(value)[:20]), self.assertRaises(ValueError):
                validate_solver(step)

    def test_scipy_options_all_modes(self):
        for batch in (False, True):
            for timed in (False, True):
                for ftol in ('omitted', None, 1e-7):
                    with self.subTest(batch=batch, timed=timed, ftol=ftol):
                        kw = dict(seed=3, max_evaluations=4, restart_sigma=.1, batch_fd=batch)
                        if ftol != 'omitted':
                            kw['ftol'] = ftol
                        if batch:
                            kw['residuals_batch'] = lambda xs: [[x[0]] for x in xs]
                        if timed:
                            kw['_timing'] = (TimerCollector(), 'search')
                        with patch('lpf.optimizers.hybrid.minimize', wraps=minimize) as call:
                            hybrid_minimize(lambda x: [x[0]], [.5], [(0, 1)], **kw)
                        self.assertTrue(call.called)
                        for invocation in call.call_args_list:
                            options = invocation.kwargs['options']
                            self.assertEqual('ftol' in options, ftol == 1e-7)
                            if ftol == 1e-7:
                                self.assertEqual(options['ftol'], ftol)
                            self.assertEqual('workers' in options, batch)
        for value in (0, -1, float('nan'), float('inf'), True, '1', 10**1000):
            with self.subTest(value=str(value)[:20]), self.assertRaises(ValueError):
                hybrid_minimize(lambda x: [x[0]], [.5], [(0, 1)], seed=1,
                                max_evaluations=2, restart_sigma=.1, ftol=value)

    def test_runner_worker_propagation(self):
        config = json.loads((ROOT/'project/diagnostics/issue470/config.json').read_text())
        starts = json.loads((ROOT/'project/diagnostics/issue470/starts.json').read_text())
        step = config['arms'][0]['steps'][0]
        step['options'].update(max_search_forwards=2, ftol=1e-7)
        config['budget'] = dict(rf_samples=70*26+476, rf_forwards=27, independent_mna_samples=2)
        with tempfile.TemporaryDirectory(prefix='issue513-test-') as tmp:
            out = Path(tmp)/'run'
            with patch('lpf.optimizers.hybrid.minimize', wraps=minimize) as call:
                runner.run(config, starts, out, root=ROOT, spot_checks={'terminal': [0, 111]},
                           checkpoint_interval=1, rf_cache_mode='lk')
            self.assertTrue(call.called)
            self.assertEqual(call.call_args.kwargs['options']['ftol'], 1e-7)
            plan = json.loads((out/'plan.json').read_text())
            self.assertEqual(plan['config']['arms'][0]['steps'][0]['effective_options']['ftol'], 1e-7)
            result = json.loads((out/'job-0001/result.json').read_text())
            self.assertEqual(result['steps'][0]['solver_options']['ftol'], 1e-7)
            self.assertEqual(result['terminal']['candidates'][0]['independent']['status'], 'pass')

    def test_saved_comparison_evidence(self):
        from lpf.search.storage import vector_sha
        folder = ROOT/'project/diagnostics/issue513'
        summary = json.loads((folder/'summary.json').read_text())
        with (folder/'paired.csv').open(newline='') as f:
            paired = list(csv.DictReader(f))
        jobs = [j for r in summary['runs'] for j in r['jobs']]
        by = {(j['seed'], j['arm']): j for j in jobs}
        self.assertEqual(summary['state'], 'completed')
        self.assertEqual(len(by), 60)
        self.assertEqual(len(paired), 20)
        for row in paired:
            seed = int(row['seed'])
            for arm in ('H0', 'H1', 'T'):
                job = by[seed, arm]
                self.assertEqual(vector_sha(job['initial_vector']), row['initial_sha'])
                self.assertEqual(vector_sha(job['final_vector']), row[f'{arm}_final_sha'])
                self.assertEqual(float(row[f'{arm}_J']), job['J'])
                self.assertEqual(job['independent']['status'], 'pass')
            for left, right in (('H1', 'H0'), ('T', 'H1'), ('T', 'H0')):
                self.assertAlmostEqual(float(row[f'{left}_minus_{right}_J']),
                                       by[seed, left]['J']-by[seed, right]['J'])


if __name__ == '__main__':
    unittest.main()
