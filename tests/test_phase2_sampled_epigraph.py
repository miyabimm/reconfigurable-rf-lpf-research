"""Small finite-grid regressions; no optimization or historical EXP imports."""
import sys
from pathlib import Path
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from lpf.constraint_versions import load_constraint
from lpf.phase2_models.api import CircuitDefinition, build_nominal_circuit
from lpf.phase2_models.circuit_layout import CapacitorPlacement, InductorTree
from lpf.phase2_models.sampled_epigraph import SampledEpigraph
from lpf.phase2_models.numerical_diagnostics import CircuitNumericalError


def circuit(policy_id):
    definition = CircuitDefinition(
        inductor_tree=InductorTree(4, ((0, 1), (1, 2), (1, 3))),
        inductor_types=("LQP02HV",) * 3,
        physical_order=(0, 1, 2),
        coupling_pairs=((0, 1), (1, 2), (0, 2)),
        capacitor_placement=CapacitorPlacement(4, ((1, -1),), (), ()),
        fixed_c_types=("PCB_PATTERN_C",), variable_roles=(),
    )
    return build_nominal_circuit(load_constraint(policy_id, allow_trial=True), definition)


class SampledEpigraphTests(unittest.TestCase):
    def test_grid_roles_and_signs_all_trials(self):
        for policy_id in ("RF-T005", "RF-T007", "RF-T008"):
            with self.subTest(policy_id=policy_id):
                c = circuit(policy_id)
                p = SampledEpigraph(c, 2)
                x = np.array([2., 3., 4., .1, .01, -.02, .01, 7.])
                il = p.evaluator.il(x[:-1])
                expected = np.where(p.evaluator.role == 0, 7 - il, il - 30)
                np.testing.assert_allclose(p.residuals(x), expected)
                self.assertEqual(p.objective(x), 7.)
                self.assertEqual(len(p.residuals(x)), 56)
                self.assertEqual(set(p.evaluator.segment), set(range(28)))
                self.assertEqual(set(p.evaluator.setting), set(range(6)))
                self.assertEqual(set(p.evaluator.role), {0, 1, 2})
                self.assertEqual(p.policy_fingerprint, c.policy_fingerprint)
                # Numerical derivative dimensions, without running SLSQP.
                eps = 1e-6
                jac = np.column_stack([(p.residuals(x + np.eye(len(x))[i]*eps)
                                        - p.residuals(x))/eps for i in range(len(x))])
                self.assertEqual(jac.shape, (56, len(x)))
                np.testing.assert_allclose(jac[:, -1], p.evaluator.role == 0, atol=1e-8)

    def test_invalid_vectors_and_non_spd(self):
        p = SampledEpigraph(circuit("RF-T005"), 1)
        x = np.array([2., 3., 4., .1, .01, -.02, .01, 7.])
        for invalid in (x[:-1], np.r_[x[:-1], np.nan]):
            with self.assertRaises(ValueError):
                p.residuals(invalid)
        x[4:7] = (-.9, -.9, -.9)
        with self.assertRaises(CircuitNumericalError):
            p.residuals(x)

    def test_independent_instances_and_policy_copy(self):
        a = SampledEpigraph(circuit("RF-T005"), 1)
        b = SampledEpigraph(circuit("RF-T007"), 2)
        x = np.array([2., 3., 4., .1, .01, -.02, .01, 7.])
        before = a.residuals(x)
        b.residuals(x)
        a.circuit.resolved_policy["evaluation"]["full_phase2"]["minimum_h2_h3_db"] = 0
        np.testing.assert_array_equal(a.residuals(x), before)
        self.assertEqual(a.mandatory_stop_db, 30)


if __name__ == "__main__":
    unittest.main()
