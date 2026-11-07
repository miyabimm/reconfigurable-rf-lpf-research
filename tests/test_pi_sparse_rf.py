"""Live RF API in an actual Pi sparse checkout; no historical evidence needed."""
import csv
import os
import unittest
from pathlib import Path

import numpy as np

from test_issue323_dependencies import make
from lpf.constraint_versions import constraint_fingerprint, load_constraint
from lpf.rf_core import EvaluationGrid
from lpf.rf_core._grid import validated_band_segments
from lpf.rf_core.port_parasitics import get_two_port_s
from lpf.search.component_constraints import validate_values

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('PI_SPARSE_RF') == '1', 'requires a Pi sparse checkout')
class PiSparseRFTests(unittest.TestCase):
    def test_current_rf_api_without_historical_directories(self):
        for name in ('docs', 'data', 'experiments'):
            self.assertFalse((ROOT / name).exists(), name)
        formal = load_constraint()
        self.assertEqual(len(constraint_fingerprint(formal)), 64)
        trial = load_constraint('RF-T008', allow_trial=True)
        for port in ('input_parasitic', 'output_parasitic'):
            self.assertTrue(np.isfinite(get_two_port_s(trial, port, 1e9, root=ROOT)).all())
        policy, definition, model, _, vector = make('RF-T008')
        # Use legal zero coupling; the midpoint of a signed k bound is zero.
        validate_values(definition, model.schema, vector, policy)
        with (ROOT / 'rf/bands.csv').open(newline='', encoding='utf-8') as source:
            segments = validated_band_segments(list(csv.DictReader(source)))
        grid = EvaluationGrid(
            np.array([row[2] * 1e6 for row in segments]),
            np.array([row[0] for row in segments]),
            np.arange(len(segments)),
        )
        self.assertEqual(len(grid.frequency_hz), 28)
        self.assertEqual(set(grid.setting), set(range(6)))
        result = model.evaluator(grid).evaluate(vector)
        self.assertTrue(np.isfinite(result.il_db).all())
        self.assertFalse(result.independent_mna_checked)


if __name__ == '__main__':
    unittest.main()
