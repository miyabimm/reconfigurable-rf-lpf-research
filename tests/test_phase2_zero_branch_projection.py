"""Issue #165: explicit zero-placeholder removal with circuit and RF guards.

Historical EXP-055 uses a 29-parameter source vector with six zero slots
for the physically absent third DTC in its two_dtc variant. This test
projects only that genuinely absent *hot-hot* device to a 23-parameter
vector. No existing archived vector/checkpoint is changed.
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
from lpf.phase2_models.vector_migration import project_zero_variable_branches
from lpf.phase2_models.circuit_layout import CapacitorPlacement, InductorTree
from lpf.phase2_models import exp055, exp058_area4l_gjm

RUNS = ROOT / "experiments/chatgpt_topology_search/runs"
SNAP = ROOT / "data/pareto_snapshots"


class ZeroPlaceholderProjectionTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_constraint("RF-T007", allow_trial=True)
        self.edges = exp055.capacitor_edges("two_dtc")
        self.vector = np.asarray(json.loads(
            (RUNS / "EXP-055/checkpoints/cv1_input_tip_best.json").read_text()
        )["vector"], float)
        self.placeholder = self.vector.copy()
        self.placeholder[12 + 3 * np.arange(6)] = 0.

    def build(self, *, constraint="RF-T007", installed=(0, 1, 2),
              pairs=exp055.K_PAIRS, roles=None):
        var = tuple(self.edges[4 + i] for i in installed)
        roles = (
            tuple("shunt_to_ground" if -1 in edge else "bridge" for edge in var)
            if roles is None else roles
        )
        definition = CircuitDefinition(
            inductor_tree=InductorTree(5, exp055.L_EDGES),
            inductor_types=("LQP02HV",) * 4,
            physical_order=(0, 1, 3, 2),
            coupling_pairs=pairs,
            capacitor_placement=CapacitorPlacement(
                5, self.edges[:4], var
            ),
            fixed_c_types=(
                "GJM01", "GJM01", "PCB_PATTERN_C", "PCB_PATTERN_C"
            ),
            variable_roles=roles,
        )
        return build_nominal_circuit(
            load_constraint(constraint, allow_trial=True), definition
        )

    def test_two_dtc_source_placeholder_projects_losslessly(self):
        original = self.build()
        reduced = self.build(installed=(0, 2))
        before = self.placeholder.copy()
        proof = project_zero_variable_branches(
            original, reduced, self.placeholder, (0, 2)
        )
        self.assertEqual(proof.kept_variable_indices, (0, 2))
        self.assertEqual(proof.removed_variable_indices, (1,))
        self.assertEqual(proof.policy_fingerprint,
                         original.policy_fingerprint)
        self.assertEqual(len(proof.vector), 23)
        np.testing.assert_array_equal(self.placeholder, before)
        np.testing.assert_array_equal(
            reduced.encode(reduced.decode(proof.vector)), proof.vector
        )
        p = self.policy
        ref = exp055.Evaluator(p, 3, "two_dtc", True)
        np.testing.assert_allclose(
            original.forward_evaluator(3).il(self.placeholder),
            ref.il(self.placeholder), atol=1e-9, rtol=0
        )
        np.testing.assert_allclose(
            reduced.forward_evaluator(3).il(proof.vector),
            ref.il(self.placeholder), atol=1e-9, rtol=0
        )
        self.assertTrue(reduced.validate_components(proof.vector)[
            "candidate_promotion_blocked"
        ])  # Migration is not independent MNA/RF certification.

    def test_nonzero_removed_branch_in_any_setting_is_rejected(self):
        source, dest = self.build(), self.build(installed=(0, 2))
        for setting in (0, 2, 5):
            bad = self.placeholder.copy()
            bad[12 + 3*setting] = 1e-15  # no implicit tolerance
            with self.subTest(setting=setting), self.assertRaisesRegex(
                ValueError, "exactly zero"
            ):
                project_zero_variable_branches(source, dest, bad, (0, 2))

    def test_invalid_index_mapping_and_changed_physical_graph_rejected(self):
        source, dest = self.build(), self.build(installed=(0, 2))
        for keep in ((0, 0), (1, 2), (0,), (0, 9), (True, 2)):
            with self.subTest(indices=keep), self.assertRaises(ValueError):
                project_zero_variable_branches(
                    source, dest, self.placeholder, keep
                )
        changed = self.build(installed=(0, 2),
                             pairs=((0, 1), (3, 2), (1, 3)))
        with self.assertRaisesRegex(ValueError, "topology"):
            project_zero_variable_branches(source, changed,
                                           self.placeholder, (0, 2))

    def test_cannot_erase_grounded_shunt_or_t007_permanent_parasite(self):
        source = self.build()
        no_ground = self.build(installed=(1, 2))
        fake = self.placeholder.copy()
        fake[11 + 3*np.arange(6)] = 0.
        with self.assertRaisesRegex(ValueError, "hot-hot"):
            project_zero_variable_branches(source, no_ground, fake, (1, 2))
        self.assertNotEqual(source.schema.constant_caps_pf,
                            no_ground.schema.constant_caps_pf)

    def test_cross_trial_and_t008_composite_c_is_never_projected(self):
        source = self.build()
        t005 = self.build(constraint="RF-T005", installed=(0, 2))
        with self.assertRaisesRegex(ValueError, "same approved"):
            project_zero_variable_branches(source, t005,
                                           self.placeholder, (0, 2))
        # T008 paired IC-fixed components must remain even when Cvar=0.
        policy = load_constraint("RF-T008", allow_trial=True)
        fixed = exp058_area4l_gjm.ALL_FIXED
        var = exp058_area4l_gjm.DTC["input_output"]
        def composite(v):
            return build_nominal_circuit(
                policy, CircuitDefinition(
                    inductor_tree=InductorTree(5, exp055.L_EDGES),
                    inductor_types=("LQP02HV",)*4,
                    physical_order=(0, 1, 3, 2),
                    coupling_pairs=exp055.K_PAIRS,
                    capacitor_placement=CapacitorPlacement(5, fixed, v, v),
                    fixed_c_types=("GJM01", "PCB_PATTERN_C",
                                   "PCB_PATTERN_C", "PCB_PATTERN_C"),
                    variable_roles=("bridge",)*len(v),
                )
            )
        c2, c1 = composite(var), composite(var[:1])
        x = np.asarray(json.loads((
            SNAP / "rf_t008_exp058_area4p667_20261020.json"
        ).read_text())["best"]["vector"], float)
        with self.assertRaisesRegex(ValueError, "same approved"):
            project_zero_variable_branches(c2, c1, x, (0,))


if __name__ == "__main__":
    unittest.main()
