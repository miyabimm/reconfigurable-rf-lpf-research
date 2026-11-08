"""Current RF bounds formerly mixed with historical matching search tests."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.constraint_versions import load_constraint
from lpf.rf_core import build_rf_model
from lpf.search.component_constraints import physical_bounds
from lpf.topology_management import CircuitDefinition
from lpf.topology_management.circuit_layout import CapacitorPlacement, InductorTree


class ExplicitSeriesSearchTests(unittest.TestCase):
    def test_series_bounds_and_three_variable_dimensions(self):
        policy = load_constraint('RF-T005', allow_trial=True)
        definition = CircuitDefinition(
            InductorTree(3, ((0, 1), (1, 2))),
            ('LQP02HV', 'LQP02HQ'), (0, 1), (),
            CapacitorPlacement(3, (), ((0, -1), (1, -1), (2, -1))),
            (), ('shunt_to_ground',) * 3)
        circuit = build_rf_model(definition, policy)
        np.testing.assert_allclose(
            physical_bounds(definition, circuit.schema, policy),
            [(0.4, 27), (0.2, 56)] + [(0, 3)] * 18)


if __name__ == '__main__':
    unittest.main()
