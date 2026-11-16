"""Single-seed development uses the same parent ledger as multiple seeds."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_issue435_weighted_development as fixtures
from lpf.search._development_runner import _weighted_plan
from lpf.search._development_worker import DevelopmentWorker
from lpf.search.component_constraints import physical_bounds
from lpf.search.plan import ROOT
from lpf.search.runner import run_weighted_development
from lpf.search.storage import sha, vector_sha
from lpf.rf_core import build_rf_model


class RunnerTests(unittest.TestCase):
    setUp = fixtures.WeightedTests.setUp
    setup_model = fixtures.WeightedTests.setup_model
    inputs = fixtures.WeightedTests.inputs

    def prepared(self):
        config, starts_file, definition, policy, x = self.inputs()
        box = [list(pair) for pair in physical_bounds(
            definition, build_rf_model(definition, policy).schema, policy)]
        plan = _weighted_plan(config, ROOT, 'demo', 3, search_bounds=box)
        starts = {23: dict(vector=x.tolist(), vector_sha256=vector_sha(x))}
        return config, starts_file, definition, policy, x, box, plan, starts

    def test_single_seed_cli_uses_parent_and_keeps_original_job(self):
        config, starts_file, _, _, x, box, _, _ = self.prepared()
        output = Path(self.raw.name)/'single-parent'
        process = subprocess.run([sys.executable, str(ROOT/'scripts/run_rf_search.py'), 'develop',
            '--config', str(config), '--starts', str(starts_file), '--output', str(output),
            '--objective-mode', 'weighted_violation', '--max-search-forwards', '3',
            '--spot-checks', '{"terminal":[0,111]}'], capture_output=True, text=True)
        self.assertEqual(process.returncode, 4, process.stderr)
        parent = json.loads((output/'run.json').read_text())
        summary = json.loads((output/'summary.json').read_text())
        self.assertEqual(summary['status'], 'completed')
        self.assertEqual(len(parent['jobs']), 1)
        row = parent['jobs'][0]
        job = output/row['raw_path']
        record = json.loads((job/'input.json').read_text())
        result = json.loads((job/'result.json').read_text())
        self.assertEqual(record['plan_sha256'], sha(record['plan']))
        self.assertEqual(record['start']['vector_sha256'], vector_sha(x))
        self.assertEqual(record['search_bounds'], box)
        self.assertEqual(result['terminal']['candidates'][0]['independent']['status'], 'pass')
        self.assertEqual(result['steps'][0]['forward_count'], 3)
        before = {p: p.read_bytes() for p in output.rglob('*.json')}
        second = subprocess.run(process.args, capture_output=True, text=True)
        self.assertEqual(second.returncode, 2)
        self.assertEqual(before, {p: p.read_bytes() for p in output.rglob('*.json')})

    def test_parent_and_direct_worker_match_for_same_frozen_job(self):
        _, _, d, p, x, box, plan, starts = self.prepared()
        spots = {'terminal': [0, 111]}
        direct_path = Path(self.raw.name)/'direct'
        direct = DevelopmentWorker(plan, d, p, 'demo', 23, x, vector_sha(x), root=ROOT,
            checkpoint=direct_path, search_bounds=box, objective_mode='weighted_violation',
            spot_checks=spots).run()
        output = Path(self.raw.name)/'parent'
        summary = run_weighted_development(plan, d, p, starts, output, root=ROOT, spot_checks=spots)
        self.assertEqual(summary['status'], 'completed', summary.get('exit_reason'))
        job = output/summary['jobs'][0]['raw_path']
        self.assertEqual(json.loads((job/'result.json').read_text()), direct)
        for checkpoint in direct_path.glob('*.json'):
            self.assertEqual(checkpoint.read_bytes(), (job/'checkpoints'/checkpoint.name).read_bytes())

    def test_invalid_start_and_box_stop_before_worker(self):
        _, _, d, p, x, box, plan, starts = self.prepared()
        bad = copy.deepcopy(starts)
        bad[23]['vector_sha256'] = '0'*64
        with patch('lpf.search._development_runner.run_prepared_weighted_job') as worker:
            with self.assertRaisesRegex(ValueError, 'SHA'):
                run_weighted_development(plan, d, p, bad, Path(self.raw.name)/'bad-sha', root=ROOT)
            worker.assert_not_called()
        outside = copy.deepcopy(box)
        outside[0] = [box[0][0], float(x[0])-.1]
        bad_plan = _weighted_plan(Path(self.sources.name)/'plan.yaml', ROOT, 'demo', 3, search_bounds=outside)
        with patch('lpf.search._development_runner.run_prepared_weighted_job') as worker:
            with self.assertRaises(ValueError):
                run_weighted_development(bad_plan, d, p, starts, Path(self.raw.name)/'bad-box', root=ROOT)
            worker.assert_not_called()

    def test_worker_failure_keeps_unknown_and_never_retries(self):
        _, _, d, p, _, _, plan, starts = self.prepared()
        output = Path(self.raw.name)/'failed'
        with patch('lpf.search._development_runner.run_prepared_weighted_job',
                   side_effect=OSError('disk full')) as worker:
            summary = run_weighted_development(plan, d, p, starts, output, root=ROOT)
        worker.assert_called_once()
        self.assertEqual(summary['status'], 'unknown')
        self.assertEqual(summary['jobs'][0]['reserved'], 3*70+84+476)
        self.assertEqual(json.loads((output/'run.json').read_text())['status'], 'unknown')
        with self.assertRaises(ValueError):
            run_weighted_development(plan, d, p, starts, output, root=ROOT)


if __name__ == '__main__':
    unittest.main()
