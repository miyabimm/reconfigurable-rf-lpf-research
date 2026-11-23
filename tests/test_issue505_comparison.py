"""Selection and wall-censoring contracts for the Issue 505 diagnostic."""
import importlib.util
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[1]/'project/diagnostics/issue505/compare.py'
spec = importlib.util.spec_from_file_location('issue505', path)
compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare)

class ComparisonTests(unittest.TestCase):
    def test_no_future_first_tie_and_missing(self):
        events = [dict(elapsed_s=1., objective=2., sequence=1),
                  dict(elapsed_s=2., objective=2., sequence=2),
                  dict(elapsed_s=5.001, objective=0., sequence=3)]
        self.assertIsNone(compare.select(events, .9))
        self.assertEqual(compare.select(events, 5)['sequence'], 1)
        self.assertEqual(compare.select(events, 20)['sequence'], 3)

    def test_real_runner_callbacks_and_input_identity(self):
        with tempfile.TemporaryDirectory(prefix='issue505-test-') as tmp:
            rows = [compare.run(arm, 28, Path(tmp)/arm) for arm in ('hybrid', 'trf')]
        for row in rows:
            self.assertIsNone(row['error'])
            self.assertTrue(row['events'])
            self.assertEqual(row['result']['initial_vector_sha256'], row['events'][0]['vector_sha256'])
            self.assertEqual(len(row['events']), row['result']['steps'][0]['forward_count'])
            self.assertEqual([e['sequence'] for e in row['events']], list(range(1, len(row['events'])+1)))
            self.assertEqual(sorted(e['elapsed_s'] for e in row['events']), [e['elapsed_s'] for e in row['events']])
            self.assertEqual(row['windows']['1']['status'], 'budget_censored')
            self.assertEqual(row['windows']['1']['terminal']['independent']['status'], 'pass')
        self.assertEqual(rows[0]['result']['initial_vector_sha256'], rows[1]['result']['initial_vector_sha256'])
        self.assertEqual(rows[0]['result']['search_bounds_sha256'], rows[1]['result']['search_bounds_sha256'])
        self.assertEqual(rows[0]['result']['plan']['grids'], rows[1]['result']['plan']['grids'])

    def test_batch_observation_not_timestamped_before_batch_finishes(self):
        from lpf.rf_core.model import RFEvaluator
        original = RFEvaluator.evaluate_partial_batch
        calls = []
        def delayed(evaluator, *args, **kwargs):
            time.sleep(.05)
            result = original(evaluator, *args, **kwargs)
            calls.append(True)
            return result
        with tempfile.TemporaryDirectory(prefix='issue505-batch-') as tmp, \
             patch.object(RFEvaluator, 'evaluate_partial_batch', delayed):
            row = compare.run('hybrid', 28, Path(tmp)/'run')
        self.assertTrue(calls)
        self.assertIsNone(row['error'])
        # First scalar is followed by a batch: no point can be observed while
        # the delayed batch computation is still running.
        self.assertGreaterEqual(row['events'][1]['elapsed_s']-row['events'][0]['elapsed_s'], .05)

    def test_stop_categories(self):
        self.assertEqual(compare.classify('converged', 2, 5), 'early_convergence_hold')
        self.assertEqual(compare.classify('evaluation_limit', 2, 5), 'budget_censored')
        self.assertEqual(compare.classify('evaluation_budget_exhausted', 2, 5), 'budget_censored')
        self.assertEqual(compare.classify('converged', 6, 5), 'observed')
        self.assertEqual(compare.classify('solver_failure', 2, 5), 'early_other_stop')
        self.assertEqual(compare.classify(None, 2, 5, 'RF error'), 'rf_or_execution_stop')


    def test_extract_compact_from_archived_observations_for_storage_migration(self):
        """Temporary migration: print selected windows, never the full trace."""
        import gzip
        import json
        from lpf.search.storage import vector_sha
        folder = Path(__file__).resolve().parents[1]/'project/diagnostics/issue505/raw'
        for run_id in ('h1','t1','t2','h2','h3','t3'):
            with gzip.open(folder/(run_id+'.json.gz'), 'rt') as f:
                raw = json.load(f)
            rr = raw['result']
            step = rr['steps'][0]
            windows = {}
            for label in ('1','5','20'):
                stored = raw['windows'][label]
                e = compare.select(raw['events'], int(label))
                self.assertEqual(stored['selected_sequence'], e['sequence'])
                self.assertEqual(stored['vector_sha256'], e['vector_sha256'])
                self.assertEqual(vector_sha(e['vector']), e['vector_sha256'])
                windows[label] = dict(
                    status=stored['status'],
                    selected_sequence=e['sequence'],
                    observed_s=e['elapsed_s'],
                    forward_count=e['forward_count'],
                    search_objective=e['objective'],
                    vector_sha256=e['vector_sha256'],
                    vector=e['vector'],
                    terminal=stored['terminal'])
            d = dict(
                run=run_id, arm=raw['arm'], seed=rr['seed'], limit=raw['limit'],
                plan_sha256=raw['plan_sha256'],
                source_sha256=rr['source_sha256'],
                initial_vector_sha256=rr['initial_vector_sha256'],
                search_bounds_sha256=rr['search_bounds_sha256'],
                status=rr['status'], stop_reason=step['stop_reason'],
                converged=step['converged'],
                solver_wall_s=raw['solver_wall_s'],
                solver_cpu_s=raw['solver_cpu_s'],
                runner_wall_s=raw['runner_wall_s'],
                runner_cpu_s=raw['runner_cpu_s'],
                loadavg_start=raw['loadavg_start'],
                loadavg_end=raw['loadavg_end'],
                forward_count=step['forward_count'],
                requested_samples=step['requested_samples'],
                actual=raw['state']['jobs'][0]['actual'],
                local_runs=step.get('local_runs'),
                trf_details={
                    key:step['trf_details'][key] for key in
                    ('nfev','njev','sensitivity_evaluations','computed_samples',
                     'status','message','wall_s','cpu_s')
                } if raw['arm']=='trf' else None,
                windows=windows)
            print('ISSUE505_EXTRACT='+json.dumps(d, separators=(',', ':')),flush=True)

if __name__ == '__main__':
    unittest.main()
