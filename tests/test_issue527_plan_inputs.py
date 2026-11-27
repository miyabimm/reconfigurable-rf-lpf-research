"""Input-only checks for Issue 527; no RF search or forward."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.minimax_profile import load_minimax_profile
from lpf.search.component_constraints import physical_bounds
from lpf.search.development_plan import freeze_run
from lpf.search.plan import Loader, ROOT
from lpf.search.proposals import definition_from_data
from lpf.search.starts import generate_for_definition
from lpf.search.storage import sha, vector_sha

sys.path.insert(0, str(ROOT / 'scripts'))
from generate_develop_inputs import prepare
import run_rf_search


class InputTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / 'project/diagnostics/issue470/config.json').read_text())
        self.config['arms'][0]['steps'][0].update(solver='trf', options={'max_evaluations': 1000})
        self.spots = {'terminal': [0, 111]}
        self.profile = load_minimax_profile('RF-T010', root=ROOT, allow_trial=True)
        self.policy = json.loads(self.profile.base_json)
        self.definition = definition_from_data(json.loads((ROOT / self.config['definition']['path']).read_text()))
        self.physical = physical_bounds(self.definition, self.profile.build_model(self.definition).schema, self.policy)

    def test_limits_freeze_and_default(self):
        self.assertEqual(self.definition.inductor_types, ('LQP02HV',) * 4)
        for value in (10.0, 5.0, None):
            settings = {'search_limits': {} if value is None else {'GJM01': {'max': value}}}
            box, starts, allocation, plan = prepare(self.config, settings, self.spots)
            physical = np.asarray(self.physical)
            changed = np.flatnonzero(np.any(np.asarray(box) != physical, axis=1)).tolist()
            self.assertEqual(changed, [] if value is None else [4, 5, 6])
            np.testing.assert_array_equal(np.asarray(box)[:, 0], physical[:, 0])
            self.assertEqual(box[:4], [[0.4, 27.0]] * 4)
            if value is not None:
                self.assertEqual([box[i] for i in (4, 5, 6)], [[0.1, value]] * 3)
            self.assertEqual(plan.data['search_bounds'], box)
            self.assertEqual(plan.data['search_bounds_sha256'], sha(box))
            rec = starts['1013']['baseline']
            self.assertEqual(rec['vector_sha256'], vector_sha(rec['vector']))
            self.assertEqual(allocation['1013']['baseline'], 1013)
            self.assertEqual(rec['vector'], generate_for_definition(self.definition, self.policy, 1013, bounds=box)['vector'])
            if value is None:
                default = freeze_run(self.config, starts, root=ROOT, spot_checks=self.spots,
                                     search_bounds=None, checkpoint_interval=1000)[0]
                self.assertEqual(default.data['search_bounds'], box)
                self.assertEqual(rec['vector'], generate_for_definition(self.definition, self.policy, 1013)['vector'])
            else:
                bad = copy.deepcopy(starts)
                bad['1013']['baseline']['vector'][4] = value + 1
                bad['1013']['baseline']['vector_sha256'] = vector_sha(bad['1013']['baseline']['vector'])
                with self.assertRaises(ValueError):
                    freeze_run(self.config, bad, root=ROOT, spot_checks=self.spots,
                               search_bounds=box, checkpoint_interval=1000)

    def test_invalid_settings(self):
        for limits in ({'GJM01': {'max': v}} for v in (0.09, 0, -1, True, '10', float('nan'), float('inf'))):
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                prepare(self.config, {'search_limits': limits}, self.spots)
        for settings in ({}, {'search_limits': None}, {'search_limits': {'L': {'max': 10}}},
                         {'search_limits': {'GJM01': {'min': 1, 'max': 10}}}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                prepare(self.config, settings, self.spots)

    def test_runner_cli_bounds_omission_and_explicit(self):
        with tempfile.TemporaryDirectory(prefix='issue527-cli-') as tmp:
            root = Path(tmp)
            config = root / 'config.yaml'
            starts = root / 'starts.json'
            bounds = root / 'bounds.json'
            config.write_text('{}')
            starts.write_text('{}')
            bounds.write_text('[[0.1, 10.0]]')
            args = ['develop', '--config', str(config), '--starts', str(starts),
                    '--output', str(root / 'run'), '--spot-checks', '{"terminal":[0]}']
            with patch.object(run_rf_search, 'run', return_value={'status': 'done', 'plan_sha256': 'x', 'jobs': []}) as run:
                self.assertEqual(run_rf_search.main(args), 0)
                self.assertIsNone(run.call_args.kwargs['search_bounds'])
                self.assertEqual(run_rf_search.main(args + ['--search-bounds', str(bounds)]), 0)
                self.assertEqual(run.call_args.kwargs['search_bounds'], [[0.1, 10.0]])

    def test_multi_arm_and_cli_artifacts(self):
        self.config['seeds'] = [1013, 0]
        arm = copy.deepcopy(self.config['arms'][0])
        arm['name'] = 'other'
        self.config['arms'].append(arm)
        self.config['budget'] = {key: value * 4 for key, value in self.config['budget'].items()}
        with tempfile.TemporaryDirectory(prefix='issue527-test-') as tmp:
            root = Path(tmp)
            config = root / 'in.yaml'
            config.write_text(yaml.safe_dump(self.config))
            output = root / 'inputs'
            proc = subprocess.run([sys.executable, str(ROOT / 'scripts/generate_develop_inputs.py'),
                                   '--config', str(config), '--settings', str(ROOT / 'scripts/develop_search_limits.yaml'),
                                   '--spot-checks', json.dumps(self.spots), '--output', str(output)],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            manifest = json.loads((output / 'manifest.json').read_text())
            for name, digest in manifest['files_sha256'].items():
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest)
            self.assertEqual(manifest['sobol_seeds'], {'1013': {'baseline': 1013, 'other': 1},
                                                       '0': {'baseline': 0, 'other': 2}})
            cfg = yaml.load((output / 'config.yaml').read_text(), Loader=Loader)
            starts = json.loads((output / 'starts.json').read_text())
            box = json.loads((output / 'bounds.json').read_text())
            plan = freeze_run(cfg, starts, root=ROOT, spot_checks=self.spots, search_bounds=box,
                              checkpoint_interval=1000)[0]
            self.assertEqual(manifest['plan_sha256'], plan.sha256)
            self.assertEqual(manifest['search_bounds_sha256'], sha(box))
            self.assertEqual(len({j['vector_sha256'] for j in plan.data['jobs']}), 4)
            self.assertEqual(proc.returncode, 0)
            again = subprocess.run(proc.args, capture_output=True, text=True)
            self.assertEqual(again.returncode, 2)


if __name__ == '__main__':
    unittest.main()
