"""Single-job development runner contract; no formal EXP."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_issue315_fixed_stage as fixtures
from lpf.search._development_runner import run_development_worker
from lpf.search._development_worker import DevelopmentWorker, _save_checkpoint
from lpf.search.plan import ROOT
from lpf.search.storage import sha, vector_sha


class RunnerTests(unittest.TestCase):
    setUp = fixtures.FixedStageTests.setUp
    setup_model = fixtures.FixedStageTests.setup_model

    def inputs(self):
        def configure(c):
            first = c['arms'][0]['steps'][0]
            first.update(solver='hybrid', aggregation='sum', max_requested_samples=168,
                         options=dict(max_search_forwards=3))
            second = copy.deepcopy(first)
            second.update(name='fine', solver='slsqp', points_per_interval=3, max_requested_samples=252,
                          options=dict(max_iterations=2, max_evaluations=3))
            c['arms'][0]['steps'].append(second)
        plan, d, policy, x = self.setup_model('RF-T008', mutate=configure)
        starts = Path(self.raw.name) / 'starts.json'
        starts.write_text(json.dumps({'23': {'vector': x.tolist(), 'vector_sha256': vector_sha(x)}}))
        return plan, d, policy, x, starts, Path(self.sources.name) / 'plan.yaml'

    def test_direct_cli_and_checkpoints(self):
        plan, d, policy, x, starts, config = self.inputs()
        spots = {'terminal': [0, 111]}
        direct_path = Path(self.raw.name) / 'direct'
        direct = DevelopmentWorker(plan, d, policy, 'demo', 23, x, vector_sha(x), root=ROOT,
                                   checkpoint=direct_path, spot_checks=spots).run()
        output = Path(self.raw.name) / 'job'
        p = subprocess.run([sys.executable, str(ROOT/'scripts/run_development_worker.py'),
                            '--config', str(config), '--starts', str(starts), '--seed', '23',
                            '--arm', 'demo', '--output', str(output), '--spot-checks', json.dumps(spots)],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 4 if direct['status'] == 'not_converged' else 0, p.stderr)
        self.assertEqual(json.loads((output/'result.json').read_text()), direct)
        api_output = Path(self.raw.name) / 'api-job'
        returned = run_development_worker(config, starts, 23, 'demo', api_output, spot_checks=spots)
        self.assertEqual(returned, direct)
        self.assertEqual(json.loads((api_output/'result.json').read_text()), returned)
        record = json.loads((output/'input.json').read_text())
        self.assertEqual(record['plan_sha256'], plan.sha256)
        self.assertEqual(record['plan'], plan.data)
        self.assertEqual(record['start']['vector_sha256'], vector_sha(x))
        self.assertEqual(record['start']['vector'], x.tolist())
        self.assertEqual(record['policy_id'], 'RF-T008')
        self.assertEqual(record['spot_checks'], spots)
        self.assertEqual((record['search_bounds_mode'], record['search_bounds'], record['search_bounds_sha256']),
                         ('physical_full', None, None))
        paths = sorted((output/'checkpoints').glob('*.json'))
        self.assertGreaterEqual(len(paths), 2)
        for i, path in enumerate(paths, 1):
            row = json.loads(path.read_text())
            self.assertEqual(path.name, f'{i:06d}.json')
            self.assertEqual(row['sequence'], i)
            self.assertEqual(row['grid_sha256'], plan.data['grids'][f"demo/{row['step']}"]['sha256'])
            self.assertEqual(row['best']['vector_sha256'], vector_sha(row['best']['vector']))
            self.assertEqual(path.read_bytes(), (direct_path/path.name).read_bytes())
        self.assertEqual(direct['terminal']['candidates'][0]['independent']['status'], 'pass')
        before = {p: p.read_bytes() for p in output.rglob('*.json')}
        with self.assertRaises(FileExistsError):
            run_development_worker(config, starts, 23, 'demo', output)
        self.assertEqual(before, {p: p.read_bytes() for p in output.rglob('*.json')})

    def test_search_bounds_runner_record_and_cli(self):
        _, _, _, x, starts, config = self.inputs()
        from lpf.optimizers.hybrid import hybrid_minimize
        from lpf.optimizers.slsqp import slsqp_minimize
        from lpf.search.component_constraints import physical_bounds
        from lpf.rf_core import build_rf_model
        from test_issue307_constraints import make
        p, d, _, _, _ = make('RF-T008')
        box = [list(pair) for pair in physical_bounds(d, build_rf_model(d, p).schema, p)]
        box[0] = [x[0], x[0]]
        box[1] = [x[1] - .01, x[1] + .01]
        output = Path(self.raw.name)/'boxed'
        seen = []
        def observe(fn):
            def call(callback, start, bounds, **kw):
                seen.append((start.copy(), copy.deepcopy(bounds)))
                return fn(callback, start, bounds, **kw)
            return call
        with patch('lpf.search._worker_next.hybrid_minimize', side_effect=observe(hybrid_minimize)), \
             patch('lpf.search._development_worker.slsqp_minimize', side_effect=observe(slsqp_minimize)):
            result = run_development_worker(config, starts, 23, 'demo', output, search_bounds=box)
        record = json.loads((output/'input.json').read_text())
        self.assertEqual(record['search_bounds_mode'], 'specified')
        self.assertEqual(record['search_bounds'], box)
        self.assertEqual(record['search_bounds_sha256'], sha(box))
        self.assertEqual(len(seen), 2)
        for start, applied in seen:
            self.assertEqual([list(row) for row in applied], record['search_bounds'])
            self.assertEqual(start[0], x[0])
        for step in result['steps']:
            self.assertEqual(step['rf_best']['vector'][0], x[0])
        for path in (output/'checkpoints').glob('*.json'):
            self.assertEqual(json.loads(path.read_text())['best']['vector'][0], x[0])
        bounds_file = Path(self.raw.name)/'box.json'
        bounds_file.write_text(json.dumps(box))
        cli_output = Path(self.raw.name)/'cli-boxed'
        cli = subprocess.run([sys.executable, str(ROOT/'scripts/run_development_worker.py'),
                              '--config', str(config), '--starts', str(starts), '--seed', '23',
                              '--arm', 'demo', '--output', str(cli_output), '--search-bounds', str(bounds_file)],
                             capture_output=True, text=True)
        self.assertIn(cli.returncode, (0, 4), cli.stderr)
        self.assertEqual(json.loads((cli_output/'input.json').read_text())['search_bounds'], box)
        self.assertEqual(json.loads((cli_output/'result.json').read_text()), result)

    def test_full_box_matches_default_and_box_stop_preserves_input(self):
        _, d, p, x, starts, config = self.inputs()
        from lpf.rf_core import build_rf_model
        from lpf.search.component_constraints import physical_bounds
        box = [list(pair) for pair in physical_bounds(d, build_rf_model(d, p).schema, p)]
        default = Path(self.raw.name)/'default-full'
        explicit = Path(self.raw.name)/'explicit-full'
        self.assertEqual(run_development_worker(config, starts, 23, 'demo', default),
                         run_development_worker(config, starts, 23, 'demo', explicit, search_bounds=box))
        for path in (default/'checkpoints').glob('*.json'):
            self.assertEqual(path.read_bytes(), (explicit/'checkpoints'/path.name).read_bytes())
        bad = copy.deepcopy(box); bad[0] = [box[0][0], float(x[0]) - .1]
        stopped = Path(self.raw.name)/'boxed-stop'
        with patch('lpf.search._worker_next.hybrid_minimize') as solver:
            with self.assertRaises(ValueError):
                run_development_worker(config, starts, 23, 'demo', stopped, search_bounds=bad)
            solver.assert_not_called()
        before = (stopped/'input.json').read_bytes()
        self.assertEqual(json.loads(before)['search_bounds_sha256'], sha(bad))
        self.assertFalse((stopped/'result.json').exists())
        with self.assertRaises(FileExistsError):
            run_development_worker(config, starts, 23, 'demo', stopped, search_bounds=box)
        self.assertEqual((stopped/'input.json').read_bytes(), before)

    def test_rejections_and_failure_preservation(self):
        plan, d, policy, x, starts, config = self.inputs()
        for seed, arm in ((24, 'demo'), (23, 'absent')):
            with self.assertRaises(ValueError):
                run_development_worker(config, starts, seed, arm, Path(self.raw.name)/f'bad-{seed}-{arm}')
        bad = Path(self.raw.name)/'bad.json'
        bad.write_text(json.dumps({'23': {'vector': x.tolist(), 'vector_sha256': '0'*64}}))
        with self.assertRaisesRegex(ValueError, 'SHA'):
            run_development_worker(config, bad, 23, 'demo', Path(self.raw.name)/'bad-sha')
        with self.assertRaises(ValueError):
            run_development_worker(config, starts, 23, 'demo', ROOT/'bad-output')
        repo = Path(self.raw.name)/'other-repo'
        repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        with self.assertRaisesRegex(ValueError, 'Git'):
            run_development_worker(config, starts, 23, 'demo', repo/'job')
        cli = subprocess.run([sys.executable, str(ROOT/'scripts/run_development_worker.py'),
                              '--config', str(config), '--starts', str(bad), '--seed', '23',
                              '--arm', 'demo', '--output', str(Path(self.raw.name)/'cli-fail')],
                             capture_output=True, text=True)
        self.assertEqual(cli.returncode, 2)
        self.assertIn('STOP:', cli.stderr)
        output = Path(self.raw.name)/'failed'
        def fail(worker):
            _save_checkpoint(worker.path/'000001.json', {'preserved': True})
            raise RuntimeError('worker failure')
        with patch.object(DevelopmentWorker, 'run', fail):
            with self.assertRaisesRegex(RuntimeError, 'worker failure'):
                run_development_worker(config, starts, 23, 'demo', output)
        self.assertTrue((output/'input.json').is_file())
        self.assertEqual(json.loads((output/'checkpoints/000001.json').read_text()), {'preserved': True})
        self.assertFalse((output/'result.json').exists())
        with self.assertRaises(FileExistsError):
            run_development_worker(config, starts, 23, 'demo', output)

    def test_save_failure_stops_without_retry(self):
        _, _, _, _, starts, config = self.inputs()
        input_fail = Path(self.raw.name)/'input-failed'
        with patch('lpf.search._development_runner._save_checkpoint', side_effect=OSError('input disk full')), \
             patch('lpf.search._development_runner.DevelopmentWorker') as worker:
            with self.assertRaisesRegex(OSError, 'input disk full'):
                run_development_worker(config, starts, 23, 'demo', input_fail)
            worker.assert_not_called()
        self.assertTrue(input_fail.is_dir())
        output = Path(self.raw.name)/'save-failed'
        def save(path, value):
            if path.name == 'result.json':
                raise OSError('disk full')
            return _save_checkpoint(path, value)
        with patch('lpf.search._development_runner._save_checkpoint', side_effect=save) as writer:
            with self.assertRaisesRegex(OSError, 'disk full'):
                run_development_worker(config, starts, 23, 'demo', output)
        self.assertEqual([c.args[0].name for c in writer.call_args_list], ['input.json', 'result.json'])
        self.assertTrue((output/'input.json').exists())
        self.assertTrue(list((output/'checkpoints').glob('*.json')))
        self.assertFalse((output/'result.json').exists())


if __name__ == '__main__':
    unittest.main()
