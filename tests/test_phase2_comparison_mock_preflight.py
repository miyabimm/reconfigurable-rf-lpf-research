"""Issue 299 mock-only API wiring; no scientific forward or EXP."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import numpy as np

from test_phase2_problem_seed import make
from lpf.phase2_models.comparison_mock_preflight import run_mock_arm


class ComparisonMockPreflightTests(unittest.TestCase):
    def setUp(self):
        self.problem, _ = make('RF-T008', 4)
        self.circuit = self.problem.circuit
        self.mock = Mock(side_effect=lambda evaluator, x: np.where(evaluator.role == 0, .4, 30.))

    def test_four_arms_share_pipeline_sobol_and_c1_replays(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = [run_mock_arm(self.circuit, arm, 23, mock_forward=self.mock,
                     output=Path(directory) / (arm + '.json')) for arm in 'ABCD']
            for row in rows:
                self.assertEqual(row['state'], 'returned_unverified', row)
                self.assertEqual(row['start'], rows[0]['start'])
                self.assertEqual(row['production_g0_g1_g2'], 'not_run')
                self.assertEqual(row['anytime'], 'partial_BCD_only')
                self.assertEqual(json.loads((Path(directory) / (row['arm'] + '.json')).read_text()), row)
            a = rows[0]
            self.assertEqual(a['result']['seed']['vector'][:-1], a['start']['x'])
            # Initial C1 seed and deterministic replay are separate forward calls.
            self.assertGreaterEqual(a['cost']['frequency_samples_requested'], 112)
            self.assertEqual(rows[1]['cost']['frequency_samples_requested'], 56 + 476)
            self.assertEqual(rows[2]['cost']['frequency_samples_requested'], 168 + 476)
            self.assertGreaterEqual(rows[3]['cost']['frequency_samples_requested'], 224 + 476)
            d = rows[3]
            counts = d['result']['counts']
            self.assertGreater(sum(counts['selection'].values()), 0)
            self.assertEqual(d['cost_by_grid_samples']['84']['calls'],
                             sum(counts['selection'].values()) + sum(counts['slp'].values()))
            self.assertNotEqual(d['result']['nfev'], d['cost']['frequency_samples_requested'])

    def test_budget_and_forward_failure_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            row = run_mock_arm(self.circuit, 'C', 23, mock_forward=self.mock,
                               output=p / 'budget.json', max_samples=560)
            self.assertEqual(row['state'], 'budget_exhausted')
            self.assertEqual(row['cost']['frequency_samples_requested'], 560)
            self.assertEqual(row['scans'][-1]['milestone'], 'terminal')
            self.assertEqual(row['cost_by_grid_samples']['84']['requested'], 84)
            self.assertEqual(row['cost_by_grid_samples']['476']['requested'], 476)
            self.assertIsNotNone(row['last_observation'])
            fail = Mock(side_effect=RuntimeError('forward failed'))
            row = run_mock_arm(self.circuit, 'B', 23, mock_forward=fail, output=p / 'fail.json')
            self.assertEqual(row['state'], 'failed')
            self.assertEqual(row['cost']['frequency_samples_requested'], 56)
            self.assertEqual(row['cost']['frequency_samples_completed'], 0)
            self.assertEqual(row['cost']['forward_failures'], 1)
            self.assertIsNone(row['last_observation'])
            self.assertEqual(json.loads((p / 'fail.json').read_text()), row)

    def test_milestone_scans_last_observation_and_keeps_terminal_reserve(self):
        with tempfile.TemporaryDirectory() as directory:
            row = run_mock_arm(self.circuit, 'B', 23, mock_forward=self.mock,
                output=Path(directory) / 'scan.json', max_samples=1008, milestones=(56,))
            self.assertEqual(row['state'], 'returned_unverified')
            self.assertEqual([s['milestone'] for s in row['scans']], [56, 'terminal'])
            self.assertEqual(row['scans'][0]['samples_at_completion'], 532)
            self.assertEqual(row['scans'][0]['x_sha256'], row['last_observation']['sha256'])
            self.assertTrue(row['scans'][0]['strict_finite_grid_feasible'])
            self.assertEqual(row['cost']['frequency_samples_requested'], 1008)
            self.assertEqual(row['cost_by_grid_samples']['476']['calls'], 2)

    def test_strict_threshold_and_nonfinite_forward(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            almost = Mock(side_effect=lambda e, x: np.where(e.role == 0, .4, np.nextafter(30., 0.)))
            row = run_mock_arm(self.circuit, 'B', 23, mock_forward=almost,
                               output=path / 'strict.json', max_samples=1008, milestones=(56,))
            self.assertFalse(row['scans'][0]['strict_finite_grid_feasible'])
            invalid = Mock(side_effect=lambda e, x: np.full(len(e.f), np.nan))
            row = run_mock_arm(self.circuit, 'B', 23, mock_forward=invalid, output=path / 'nan.json')
            self.assertEqual(row['state'], 'failed')
            self.assertEqual(row['cost']['frequency_samples_requested'], 56)
            # Forward returned; invalid data are rejected after completed samples.
            self.assertEqual(row['cost']['frequency_samples_completed'], 56)
            self.assertIsNone(row['last_observation'])

    def test_interrupt_is_not_saved_as_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'interrupt.json'
            with self.assertRaises(KeyboardInterrupt):
                run_mock_arm(self.circuit, 'B', 23,
                    mock_forward=Mock(side_effect=KeyboardInterrupt()), output=path)
            saved = json.loads(path.read_text())
            self.assertEqual(saved['state'], 'interrupted')
            self.assertEqual(saved['cost']['frequency_samples_requested'], 56)
            self.assertEqual(saved['cost']['frequency_samples_completed'], 0)

    def test_requires_mock_and_new_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'x.json'
            with self.assertRaises(TypeError):
                run_mock_arm(self.circuit, 'A', 23, mock_forward=lambda e, x: 0, output=path)
            path.touch()
            with self.assertRaises(ValueError):
                run_mock_arm(self.circuit, 'A', 23, mock_forward=self.mock, output=path)


if __name__ == '__main__':
    unittest.main()
