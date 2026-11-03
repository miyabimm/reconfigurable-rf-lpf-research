"""Live RF API in an actual Pi sparse checkout; no historical evidence needed."""
import unittest
from pathlib import Path

import numpy as np

from test_phase2_problem_seed import make
from lpf.constraint_versions import constraint_fingerprint, load_constraint
from lpf.port_parasitics import get_two_port_s

ROOT = Path(__file__).resolve().parents[1]


class PiSparseRFTests(unittest.TestCase):
    def test_current_rf_api_without_historical_directories(self):
        for name in ('docs', 'data', 'experiments'):
            self.assertFalse((ROOT / name).exists(), name)
        formal = load_constraint()
        self.assertEqual(len(constraint_fingerprint(formal)), 64)
        trial = load_constraint('RF-T008', allow_trial=True)
        for port in ('input_parasitic', 'output_parasitic'):
            self.assertTrue(np.isfinite(get_two_port_s(trial, port, 1e9, root=ROOT)).all())
        problem, vector = make('RF-T008', 3)
        vector[6] = 0.  # non-neighbor coupling is forbidden by this fixture
        evaluator = problem.circuit.forward_evaluator(1)
        self.assertEqual(len(evaluator.f), 28)
        self.assertEqual(set(evaluator.setting), set(range(6)))
        self.assertTrue(np.isfinite(evaluator.il(vector)).all())
        result = problem.circuit.evaluate_sampled(vector, points_per_interval=1)
        self.assertTrue(result['candidate_promotion_blocked'])
        self.assertFalse(result['rf_compliance_certified'])
        self.assertFalse(result['independent_mna_checked'])


if __name__ == '__main__':
    unittest.main()
