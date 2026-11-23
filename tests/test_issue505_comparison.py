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
            compact = compare.compact_record(row)
            self.assertNotIn('events', compact)
            self.assertNotIn('result', compact)
            self.assertNotIn('state', compact)
            self.assertEqual(compact['initial_vector_sha256'], row['result']['initial_vector_sha256'])
            window = compact['windows']['1']
            self.assertEqual(window['vector_sha256'], row['windows']['1']['vector_sha256'])
            self.assertEqual(len(window['vector']), 25)
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




    def test_saved_compact_records_and_vector_identity(self):
        import csv
        import json
        from lpf.search.storage import vector_sha
        folder = Path(__file__).resolve().parents[1]/'project/diagnostics/issue505'
        with (folder/'summary.json').open() as stream:
            summary = json.load(stream)
        with (folder/'paired.csv').open(newline='') as stream:
            paired = list(csv.DictReader(stream))
        self.assertEqual(len(summary['runs']), 6)
        self.assertEqual(len(paired), 18)
        self.assertEqual(len(summary['selected_vectors']), 10)
        self.assertFalse((folder/'raw').exists())
        self.assertFalse((folder/'controls.tar').exists())
        for digest, vector in summary['selected_vectors'].items():
            self.assertEqual(len(vector), 25)
            self.assertEqual(vector_sha(vector), digest)
        by_key = {(row['run'], row['window_s']): row for row in paired}
        self.assertEqual(len(by_key), 18)
        for run in summary['runs']:
            for window in ('1', '5', '20'):
                chosen = run['windows'][window]
                row = by_key[(run['run'], window)]
                self.assertEqual(row['vector_sha256'], chosen['vector_sha256'])
                self.assertEqual(float(row['terminal_J_db']), chosen['terminal_J_db'])
                self.assertEqual(float(row['search_objective_db2']), chosen['search_objective_db2'])
                self.assertEqual(row['independent_mna'], 'pass')
                self.assertFalse(chosen['finite_grid_pass'])


    def test_temporary_first_hybrid_local_vs_trf(self):
        """One-off audit of original #505 measurements; remove after extraction."""
        import gzip
        import json
        import subprocess
        import gc
        import numpy as np
        from lpf.search.storage import vector_sha
        from lpf.search import _development_runner as runner
        from lpf.minimax_profile import signed_margins
        from lpf.search.plan import ROOT, grid_from_record
        ancestor = 'e7afe33efa954d3c41a0b7502b16e1e5a27c05f5'
        full = json.loads((ROOT/'project/diagnostics/issue505/summary.json').read_text())
        refsha = next(iter(full['selected_vectors']))
        trfsha = full['runs'][1]['windows']['1']['vector_sha256']
        trf_x = np.asarray(full['selected_vectors'][trfsha])
        config = json.loads((ROOT/'project/diagnostics/issue470/config.json').read_text())
        starts = json.loads((ROOT/'project/diagnostics/issue470/starts.json').read_text())
        config['arms'][0]['steps'][0]['options'].update(max_search_forwards=150000, batch_fd=True, partial_fd=True)
        config['budget'] = dict(rf_samples=70*150024+476, rf_forwards=150025, independent_mna_samples=2)
        frozen, _, profile, model, _ = runner.freeze_run(config, starts, root=ROOT, spot_checks={'terminal':[0,111]},
            search_bounds=None, checkpoint_interval=1000)
        grid = grid_from_record(frozen.data['grids']['terminal'])
        evaluator = model.evaluator(grid)
        for run_id in ('h1', 'h2', 'h3'):
            raw = subprocess.run(['git','show',f'{ancestor}:project/diagnostics/issue505/raw/{run_id}.json.gz'],
                                 check=True,stdout=subprocess.PIPE).stdout
            data = json.loads(gzip.decompress(raw))
            runs = data['result']['steps'][0]['local_run_details']
            first = runs[0]
            x = np.asarray(first['end_x'])
            _, m = signed_margins(profile,grid,evaluator.evaluate(x))
            j=float(np.max(m))
            result={'run':run_id,'local_runs':len(runs),
                'first_nfev':first['nfev'],'first_nit':first['nit'],
                'first_success':first['success'],'first_status':first['status'],
                'first_fun':first['end_fun'],'first_sha':vector_sha(x),
                'first_terminal_J_db':j,
                'trf_fun':full['runs'][1]['windows']['1']['search_objective_db2'],
                'trf_sha':trfsha,'trf_J_db':full['runs'][1]['windows']['1']['terminal_J_db'],
                'same_vector':np.array_equal(x,trf_x),'max_abs_component_delta':float(np.max(np.abs(x-trf_x))),
                'euclidean_component_delta':float(np.linalg.norm(x-trf_x)),
                'other_locals':[{key:run[key] for key in ('success','status','nfev','end_fun')} for run in runs[1:]]}
            print('FIRST_LOCAL_AUDIT='+json.dumps(result,separators=(',',':')),flush=True)
            del data,raw,runs
            gc.collect()

if __name__ == '__main__':
    unittest.main()
