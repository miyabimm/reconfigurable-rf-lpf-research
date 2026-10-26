"""Issue #165: role evidence is not silently conflated with policy PASS.

A connected hot-node L tree validates that hot-hot C spans an inductive
path, but does not prove physical insertion in a mandatory series path.
These tests are read-only saved-vector regressions, not new EXP evidence.
"""
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lpf.constraint_versions import load_constraint
from lpf.phase2_models.api import CircuitDefinition, build_nominal_circuit
from lpf.phase2_models.circuit_layout import CapacitorPlacement, InductorTree
from lpf.phase2_models.role_audit import audit_variable_connection_roles
from lpf.phase2_models import exp055

RUNS = ROOT / "experiments/chatgpt_topology_search/runs"


class ConnectionRoleAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = InductorTree(5, exp055.L_EDGES)

    def definition(self, roles, *, var=None):
        edges = exp055.capacitor_edges("cv1_input_tip")
        return CircuitDefinition(
            inductor_tree=self.tree,
            inductor_types=("LQP02HV",) * 4,
            physical_order=(0, 1, 3, 2),
            coupling_pairs=exp055.K_PAIRS,
            capacitor_placement=CapacitorPlacement(
                5, edges[:4], edges[4:7] if var is None else var
            ),
            fixed_c_types=(
                "GJM01", "GJM01", "PCB_PATTERN_C", "PCB_PATTERN_C"
            ),
            variable_roles=roles,
        )

    def test_tree_proves_ground_and_electrical_chord_not_series(self):
        r = audit_variable_connection_roles(
            self.tree, ((3, -1), (0, 3), (1, 2)),
            ("shunt_to_ground", "bridge", "series")
        )
        self.assertEqual(r.unverified_indices, (2,))
        self.assertFalse(r.all_verified)
        self.assertEqual(r.branches[0].evidence, "verified_ground_endpoint")
        self.assertEqual(r.branches[1].electrical_class,
                         "inductor_tree_chord")
        self.assertEqual(r.branches[1].evidence,
                         "verified_L_path_between_terminals")
        self.assertEqual(r.branches[2].evidence,
                         "series_path_not_provable_from_spanning_L_tree")
        self.assertFalse(r.as_dict()["all_verified"])

    def test_public_policy_pass_not_promotion_for_declared_series(self):
        saved = np.asarray(json.loads(
            (RUNS / "EXP-055/checkpoints/cv1_input_tip_best.json").read_text()
        )["vector"], float)
        policy = load_constraint("RF-T007", allow_trial=True)
        approved_bridge = build_nominal_circuit(
            policy, self.definition(("shunt_to_ground", "bridge", "bridge"))
        )
        series_unproved = build_nominal_circuit(
            policy, self.definition(("shunt_to_ground", "series", "bridge"))
        )
        valid = approved_bridge.validate_components(saved)
        unresolved = series_unproved.validate_components(saved)
        self.assertTrue(valid["component_policy_pass"])
        self.assertTrue(unresolved["component_policy_pass"])
        self.assertTrue(valid["connection_role_audit"]["all_verified"])
        self.assertFalse(valid["candidate_promotion_blocked"])
        self.assertFalse(unresolved["connection_role_audit"]["all_verified"])
        self.assertEqual(unresolved["connection_role_audit"][
            "unverified_indices"], (1,))
        self.assertTrue(unresolved["candidate_promotion_blocked"])
        np.testing.assert_allclose(
            approved_bridge.forward_evaluator(3).il(saved),
            series_unproved.forward_evaluator(3).il(saved),
            rtol=0, atol=1e-12
        )
        report = series_unproved.evaluate_sampled(
            saved, points_per_interval=3
        )
        self.assertTrue(report["candidate_promotion_blocked"])
        self.assertFalse(report["rf_compliance_certified"])
        self.assertFalse(report["independent_mna_checked"])

    def test_grounded_role_mismatch_and_missing_role_fail(self):
        for roles in (
            ("bridge", "bridge", "bridge"),
            ("shunt_to_ground", "shunt_to_ground", "bridge"),
            ("shunt_to_ground",),
        ):
            with self.subTest(roles=roles), self.assertRaises(ValueError):
                audit_variable_connection_roles(
                    self.tree, ((3, -1), (0, 3), (1, 2)), roles
                )
        with self.assertRaises(TypeError):
            audit_variable_connection_roles(
                None, (), ()
            )

    def test_no_dtc_branches_vacuously_verified(self):
        r = audit_variable_connection_roles(self.tree, (), ())
        self.assertEqual(r.branches, ())
        self.assertEqual(r.unverified_indices, ())
        self.assertTrue(r.all_verified)

    def test_two_models_audit_is_instance_local(self):
        a = audit_variable_connection_roles(
            self.tree, ((3, -1), (0, 3)),
            ("shunt_to_ground", "series")
        )
        b = audit_variable_connection_roles(
            self.tree, ((3, -1), (0, 3)),
            ("shunt_to_ground", "bridge")
        )
        self.assertFalse(a.all_verified)
        self.assertTrue(b.all_verified)
        self.assertEqual(a.unverified_indices, (1,))
        self.assertEqual(b.unverified_indices, ())


if __name__ == "__main__":
    unittest.main()
