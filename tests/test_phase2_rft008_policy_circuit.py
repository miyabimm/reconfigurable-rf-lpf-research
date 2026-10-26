"""Issue #163: RF-T008 v3 component/physical-coupling policy gate.

Uses immutable saved EXP-058 vectors only as numeric regression fixtures; it
does not retroactively certify EXP results or independent MNA performance.
"""
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lpf.constraint_versions import constraint_fingerprint, load_constraint
from lpf.phase2_models.circuit_layout import CapacitorPlacement, InductorTree
from lpf.phase2_models.coupled_lc import CircuitValues
from lpf.phase2_models.rft008_policy_circuit import PolicyBoundRFT008Circuit
from lpf.phase2_models import exp058_area3, exp058_area4, exp058_area4l_gjm

SNAP = ROOT / "data/pareto_snapshots"
PAIRS4 = ((0, 1), (1, 3), (3, 2))
ORDER4 = (0, 1, 3, 2)
PAIRS3 = ((0, 2), (2, 1))
ORDER3 = (0, 2, 1)


class PolicyBoundT008Tests(unittest.TestCase):
    def setUp(self):
        self.policy = load_constraint("RF-T008", allow_trial=True)

    def make4(self, *, policy=None, fixed_types=None, physical_order=ORDER4,
              var_edges=None, roles=None, ltypes=None, k_pairs=PAIRS4):
        placement = CapacitorPlacement(
            5, exp058_area4l_gjm.ALL_FIXED,
            exp058_area4l_gjm.DTC["input_output"] if var_edges is None else var_edges,
            exp058_area4l_gjm.DTC["input_output"] if var_edges is None else var_edges
        )
        return PolicyBoundRFT008Circuit.from_policy(
            self.policy if policy is None else policy,
            inductor_tree=InductorTree(5, exp058_area4l_gjm.old4.L_EDGES),
            inductor_types=("LQP02HV",)*4 if ltypes is None else ltypes,
            physical_order=physical_order, coupling_pairs=k_pairs,
            capacitor_placement=placement,
            fixed_c_types=("GJM01", "PCB_PATTERN_C", "PCB_PATTERN_C", "PCB_PATTERN_C")
                          if fixed_types is None else fixed_types,
            variable_roles=("bridge", "bridge") if roles is None else roles,
        )

    def saved4(self):
        path = SNAP / "rf_t008_exp058_area4p667_20261020.json"
        return np.asarray(json.loads(path.read_text())["best"]["vector"], float)

    def make3(self, gjm=False):
        variable = ((3, -1), (1, 2))
        p = CapacitorPlacement(4, exp058_area3.PCB_EDGES, variable, variable)
        return PolicyBoundRFT008Circuit.from_policy(
            self.policy,
            inductor_tree=InductorTree(4, exp058_area3.THREE_L_EDGES),
            inductor_types=("LQP02HV",)*3,
            physical_order=ORDER3, coupling_pairs=PAIRS3,
            capacitor_placement=p,
            fixed_c_types=("GJM01" if gjm else "PCB_PATTERN_C",
                           "PCB_PATTERN_C", "PCB_PATTERN_C"),
            variable_roles=("shunt_to_ground", "bridge"),
        )

    def test_saved_4l_candidate_component_gate_and_forward_parity(self):
        bound = self.make4()
        x = self.saved4()
        check = bound.validate_candidate(x)
        self.assertTrue(check["component_policy_pass"])
        self.assertEqual(check["constraint_id"], "RF-T008")
        self.assertEqual(check["constraint_fingerprint"],
                         constraint_fingerprint(self.policy))
        self.assertEqual(check["installed_variable_c_branches"], 2)
        self.assertEqual(check["checked_settings"], 6)
        self.assertGreater(check["min_L_eigenvalue_H"], 0)
        self.assertFalse(check["rf_performance_checked"])
        self.assertFalse(check["independent_mna_checked"])
        original = exp058_area4l_gjm.Evaluator(
            self.policy, "input_output", ("cf0",), 3
        )
        np.testing.assert_allclose(bound.evaluator(3).il(x),
                                   original.il(x), atol=1e-9, rtol=0)
        report = bound.checked_summary(x, 3)
        self.assertFalse(report["rf_compliance_certified"])
        self.assertFalse(report["independent_mna_checked"])
        self.assertEqual(report["points_per_interval"], 3)
        self.assertAlmostEqual(report["sampled_forward_metrics"]["worst_IL_db"],
                               original.summary(x)["worst_IL_db"], places=9)

    def test_saved_3l_zero_and_one_gjm_parameter_policy(self):
        rows = json.loads((SNAP /
            "rf_t008_exp058_area3_to_3p667_20261020.json"
        ).read_text())["observed_nondominated"]
        for row in rows:
            with self.subTest(gjm_count=row["GJM_count"]):
                bound = self.make3(gjm=bool(row["GJM_count"]))
                vector = np.asarray(row["vector"], float)
                self.assertTrue(bound.validate_candidate(vector)["component_policy_pass"])
                old = exp058_area3.Evaluator(
                    self.policy, "shunt_output", 3,
                    0 if row["GJM_count"] else None
                )
                np.testing.assert_allclose(bound.evaluator(3).il(vector),
                                           old.il(vector), atol=1e-9, rtol=0)

    def test_zero_one_two_dtc_branches_policy_not_exactly_two(self):
        tree = InductorTree(4, exp058_area3.THREE_L_EDGES)
        for n in (0, 1, 2):
            var = ((3, -1), (1, 2))[:n]
            layout = CapacitorPlacement(4, exp058_area3.PCB_EDGES, var, var)
            bound = PolicyBoundRFT008Circuit.from_policy(
                self.policy, inductor_tree=tree,
                inductor_types=("LQP02HV",)*3, physical_order=ORDER3,
                coupling_pairs=PAIRS3, capacitor_placement=layout,
                fixed_c_types=("PCB_PATTERN_C",)*3,
                variable_roles=("shunt_to_ground", "bridge")[:n],
            )
            fixed_ic = tuple(0.5 if -1 in e else 0.2 for e in var)
            x = np.array((2., 7., 13.) + (.1, .1, .1) + (.01, -.01) +
                         fixed_ic + (0.,)*(6*n))
            with self.subTest(count=n):
                self.assertTrue(bound.validate_candidate(x)["component_policy_pass"])
                self.assertEqual(bound.schema.vector_length, x.size)
                self.assertEqual(bound.validate_candidate(x)["installed_variable_c_branches"], n)
                # In the OFF state fixed IC C remains present in the network.
                decoded = bound.schema.decode(x)
                self.assertEqual(decoded.capacitors_pf_by_setting[0][-n:]
                                 if n else (), fixed_ic)
        var = ((3, -1), (1, 2), (0, 1))
        with self.assertRaises(ValueError):
            PolicyBoundRFT008Circuit.from_policy(
                self.policy, inductor_tree=tree,
                inductor_types=("LQP02HV",)*3, physical_order=ORDER3,
                coupling_pairs=PAIRS3,
                capacitor_placement=CapacitorPlacement(4, (), var, var),
                fixed_c_types=(),
                variable_roles=("shunt_to_ground", "bridge", "bridge"),
            )

    def test_wrong_policy_missing_roles_and_types_fail_closed(self):
        old = load_constraint("RF-T007", allow_trial=True)
        with self.assertRaises(ValueError):
            self.make4(policy=old)
        with self.assertRaises(ValueError):
            self.make4(roles=("bridge",))
        with self.assertRaises(ValueError):
            self.make4(roles=("shunt_to_ground", "bridge"))
        # GJM count has no formal hard cap; area is a Pareto objective.
        self.assertEqual(
            len(self.make4(fixed_types=("GJM01",)*4).capacitor_layout.gjm_positions),
            4
        )
        with self.assertRaises(ValueError):
            self.make4(fixed_types=("PCB_UNKNOWN",)*4)
        with self.assertRaises(ValueError):
            self.make4(fixed_types=("PCB_PATTERN_C",)*3)
        with self.assertRaises(ValueError):
            self.make4(ltypes=("LQP02",)*4)
        with self.assertRaises(ValueError):
            self.make4(ltypes=("LQP01",)*4)
        with self.assertRaises(ValueError):
            self.make4(physical_order=(0, 1, 2))
        with self.assertRaises(ValueError):
            self.make4(k_pairs=((0, 1), (1, 0)))

    def test_l_limits_adjacency_and_explicit_series_q(self):
        bound = self.make4()
        x = self.saved4()
        def mutate(i, value):
            y = x.copy()
            y[i] = value
            with self.assertRaises(ValueError):
                bound.validate_candidate(y)
        mutate(0, 27.01)
        mutate(0, 0.39)
        mutate(8, 0.101)  # adjacent |k| upper bound
        # With one additional k slot, the nonadjacent pair must remain zero.
        extended = self.make4(k_pairs=PAIRS4 + ((0, 2),))
        extra = np.r_[x[:11], .015, x[11:]]
        with self.assertRaises(ValueError):
            extended.validate_candidate(extra)
        # An HQ chip uses Q20 and up to 56nH, not historical Q25/56nH.
        hq = self.make4(ltypes=("LQP02HQ",) + ("LQP02HV",)*3)
        y = x.copy()
        y[0] = 32.
        self.assertTrue(hq.validate_candidate(y)["component_policy_pass"])
        self.assertEqual(hq.topology.inductor_q[0], 20.)
        with self.assertRaises(ValueError):
            bound.validate_candidate(y)

    def test_pcb_l_cap_limits_and_six_setting_invariance(self):
        x = self.saved4()
        bound = self.make4()
        for idx, invalid in ((4, 100.01),  # GJM max 100
                             (5, 1.0001),  # grounded PCB max 1
                             (6, .201),   # hot-hot PCB max 0.2
                             (11, .19),   # IC fixed hot-hot min .2
                             (13, 3.01)): # variable C max 3
            with self.subTest(position=idx):
                y = x.copy()
                y[idx] = invalid
                with self.assertRaises(ValueError):
                    bound.validate_candidate(y)
        # Values object cannot sneak in a band-dependent fixed C.
        v = bound.schema.decode(x)
        rows = list(v.capacitors_pf_by_setting)
        rows[1] = (rows[1][0] + .01,) + rows[1][1:]
        with self.assertRaises(ValueError):
            bound.validate_candidate(CircuitValues(
                v.inductances_nh, v.coupling_k, tuple(rows)
            ))
        # PCB L Q12, <=2nH, no chip-to-PCB coupling nominally.
        pcb = self.make4(ltypes=("PCB_L",)+("LQP02HV",)*3,
                         physical_order=(1, 3, 2))
        z = x.copy()
        z[0] = 1.9
        z[8] = 0.
        with self.assertRaises(ValueError):
            pcb.validate_candidate(x)
        self.assertTrue(pcb.validate_candidate(z)["component_policy_pass"])
        self.assertEqual(pcb.topology.inductor_q[0], 12.)
        z[0] = 2.01
        with self.assertRaises(ValueError):
            pcb.validate_candidate(z)

    def test_retains_protected_resolved_policy_snapshot(self):
        pol = load_constraint("RF-T008", allow_trial=True)
        bound = self.make4(policy=pol)
        before = bound.policy_fingerprint
        pol["components"]["LQP02"]["series"]["LQP02HV"]["max_inductance_nH"] = 1
        derived = bound.policy
        derived["trial_ic_fixed_c_by_connection"]["fixed_c_q"] = 999
        self.assertEqual(bound.policy_fingerprint, before)
        self.assertEqual(constraint_fingerprint(bound.policy), before)
        self.assertTrue(bound.validate_candidate(self.saved4())["component_policy_pass"])


if __name__ == "__main__":
    unittest.main()
