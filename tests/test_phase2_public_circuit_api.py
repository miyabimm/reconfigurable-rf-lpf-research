"""Stable Phase-2 circuit API contract and approved-trial integration tests.

These use historical saved vectors only as read-only regression fixtures.
A passing component check or forward IL is not a new RF certification.
"""
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lpf.constraint_versions import load_constraint
from lpf.phase2_models.api import CircuitDefinition, build_nominal_circuit
from lpf.phase2_models.circuit_layout import CapacitorPlacement, InductorTree
from lpf.phase2_models import exp042, exp055, exp058_area4l_gjm

RUNS = ROOT / "experiments/chatgpt_topology_search/runs"
SNAP = ROOT / "data/pareto_snapshots"
L4 = exp055.L_EDGES
K4 = exp055.K_PAIRS


def definition(fixed, variable, fixed_types, roles, *, paired=False):
    return CircuitDefinition(
        inductor_tree=InductorTree(5, L4),
        inductor_types=("LQP02HV",) * 4,
        physical_order=(0, 1, 3, 2),
        coupling_pairs=K4,
        capacitor_placement=CapacitorPlacement(
            5, fixed, variable, variable if paired else ()
        ),
        fixed_c_types=fixed_types,
        variable_roles=roles,
    )


class PublicPhase2CircuitAPITests(unittest.TestCase):
    def verify_case(self, policy_id, config, x, reference):
        circuit = build_nominal_circuit(
            load_constraint(policy_id, allow_trial=True), config
        )
        self.assertEqual(circuit.policy_id, policy_id)
        values = circuit.decode(x)
        np.testing.assert_array_equal(circuit.encode(values), x)
        check = circuit.validate_components(x)
        self.assertTrue(check["component_policy_pass"])
        self.assertEqual(check["constraint_id"], policy_id)
        self.assertEqual(check["constraint_fingerprint"],
                         circuit.policy_fingerprint)
        model = circuit.forward_evaluator(3)
        np.testing.assert_allclose(model.il(x), reference.il(x),
                                   atol=1e-9, rtol=0)
        report = circuit.evaluate_sampled(x, points_per_interval=3)
        self.assertFalse(report["rf_compliance_certified"])
        self.assertFalse(report["independent_mna_checked"])
        self.assertFalse(report["component_policy"].get(
            "independent_mna_checked", False))
        self.assertAlmostEqual(
            report["sampled_forward_metrics"]["worst_IL_db"],
            float(max(model.il(x)[model.role == 0])), places=9
        )
        return circuit

    def test_one_entry_t005_exp042(self):
        _, raw = exp042.policy_and_seed()
        x = np.asarray(raw, float)
        config = definition(
            exp042.C_EDGES[:4], exp042.C_EDGES[4:],
            ("GJM01", "GJM01", "GJM01", "PCB_PATTERN_C"),
            ("shunt_to_ground", "shunt_to_ground", "bridge")
        )
        self.verify_case("RF-T005", config, x,
                         exp042.Evaluator(
                             load_constraint("RF-T005", allow_trial=True), 3))

    def test_one_entry_t007_exp055_and_fixed_parasitic(self):
        x = np.asarray(json.loads(
            (RUNS / "EXP-055/checkpoints/cv1_input_tip_best.json").read_text()
        )["vector"], float)
        caps = exp055.capacitor_edges("cv1_input_tip")
        config = definition(
            caps[:4], caps[4:7],
            ("GJM01", "GJM01", "PCB_PATTERN_C", "PCB_PATTERN_C"),
            ("shunt_to_ground", "bridge", "bridge")
        )
        circuit = self.verify_case(
            "RF-T007", config, x,
            exp055.Evaluator(load_constraint("RF-T007", allow_trial=True),
                             3, "cv1_input_tip", True)
        )
        self.assertEqual(circuit.schema.constant_caps_pf, (0.5,))
        self.assertEqual(circuit.topology.capacitor_q[-1], 40.)

    def test_one_entry_t008_exp058_composite(self):
        x = np.asarray(json.loads(
            (SNAP / "rf_t008_exp058_area4p667_20261020.json").read_text()
        )["best"]["vector"], float)
        config = definition(
            exp058_area4l_gjm.ALL_FIXED,
            exp058_area4l_gjm.DTC["input_output"],
            ("GJM01", "PCB_PATTERN_C", "PCB_PATTERN_C", "PCB_PATTERN_C"),
            ("bridge", "bridge"), paired=True,
        )
        circuit = self.verify_case(
            "RF-T008", config, x,
            exp058_area4l_gjm.Evaluator(
                load_constraint("RF-T008", allow_trial=True),
                "input_output", ("cf0",), 3
            )
        )
        self.assertEqual(circuit.schema.n_ic_fixed, 2)
        self.assertEqual(circuit.schema.constant_caps_pf, ())
        self.assertEqual(circuit.topology.capacitor_q[-2:], (60., 60.))

    def test_immutable_definition_and_defensive_metadata(self):
        fixed = ["GJM01", "PCB_PATTERN_C", "PCB_PATTERN_C", "PCB_PATTERN_C"]
        roles = ["bridge", "bridge"]
        config = definition(
            exp058_area4l_gjm.ALL_FIXED,
            exp058_area4l_gjm.DTC["input_output"], fixed, roles, paired=True
        )
        fixed[0] = "UNKNOWN"
        roles[0] = "UNKNOWN"
        self.assertEqual(config.fixed_c_types[0], "GJM01")
        self.assertEqual(config.variable_roles[0], "bridge")
        with self.assertRaises(FrozenInstanceError):
            config.fixed_c_types = ()
        policy = load_constraint("RF-T008", allow_trial=True)
        circuit = build_nominal_circuit(policy, config)
        self.assertEqual(circuit.topology.capacitor_q[0], 80.)
        with self.assertRaises(FrozenInstanceError):
            circuit._adapter = None

    def test_policy_bound_five_l_graph_without_exp_specific_class(self):
        # 5L is a forward/API extension regression, not a new RF result.
        definition = CircuitDefinition(
            inductor_tree=InductorTree(
                6, ((0, 1), (1, 3), (3, 4), (4, 5), (5, 2)),
                source_node=0, load_node=2
            ),
            inductor_types=("LQP02HV",) * 5,
            physical_order=(0, 1, 2, 3, 4),
            coupling_pairs=(),
            capacitor_placement=CapacitorPlacement(
                6, ((0, -1), (5, -1), (2, -1)), (), ()
            ),
            fixed_c_types=("PCB_PATTERN_C",) * 3,
            variable_roles=(),
        )
        model = build_nominal_circuit(
            load_constraint("RF-T005", allow_trial=True), definition
        )
        x = np.asarray([2., 3., 4., 5., 6., .1, .1, .1], dtype=float)
        self.assertTrue(model.validate_components(x)["component_policy_pass"])
        self.assertEqual(model.schema.vector_length, len(x))
        self.assertEqual(model.schema.n_variable, 0)
        np.testing.assert_array_equal(model.encode(model.decode(x)), x)
        results = model.evaluate_sampled(x, points_per_interval=3)
        self.assertFalse(results["rf_compliance_certified"])
        self.assertTrue(results["candidate_promotion_blocked"])
        self.assertTrue(np.all(np.isfinite(model.forward_evaluator(3).il(x))))

    def test_fail_closed_for_unreviewed_policy_and_wrong_model(self):
        c = definition(exp042.C_EDGES[:4], exp042.C_EDGES[4:],
                       ("GJM01", "GJM01", "GJM01", "PCB_PATTERN_C"),
                       ("shunt_to_ground", "shunt_to_ground", "bridge"))
        for identifier in ("RF-F003", "RF-T006"):
            with self.subTest(policy=identifier), self.assertRaises(ValueError):
                build_nominal_circuit(load_constraint(identifier,
                                                       allow_trial=True), c)
        with self.assertRaises(ValueError):
            build_nominal_circuit(load_constraint("RF-T008", allow_trial=True),
                                  c)  # Missing paired IC-fixed C.
        with self.assertRaises(TypeError):
            build_nominal_circuit(load_constraint("RF-T005", allow_trial=True),
                                  {"inductor_tree": L4})


if __name__ == "__main__":
    unittest.main()
