"""RF-T005/T007 new-candidate policy gate tests using frozen EXP vectors.

Old sources are only read as test oracles; no EXP scripts/results are rewritten
or legacy feasibility/physical claims promoted to new RF approvals.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lpf.constraint_versions import load_constraint
from lpf.phase2_models.circuit_layout import CapacitorPlacement, InductorTree
from lpf.phase2_models.coupled_lc import CircuitValues
from lpf.phase2_models.rft005_t007_policy_circuit import PolicyBoundRFT005T007Circuit
from lpf.phase2_models import exp042, exp055

RUNS = ROOT / "experiments/chatgpt_topology_search/runs"
FOUR_ORDER = (0, 1, 3, 2)
FOUR_K = ((0, 1), (1, 3), (3, 2))


def build(policy_id, *, tree=None, fixed=None, var=None, kinds=None, roles=None,
          inductor_types=None, physical_order=None, k_slots=None, ic_fixed=()):
    p = load_constraint(policy_id, allow_trial=True)
    defaults = exp042.C_EDGES
    fixed = defaults[:4] if fixed is None else fixed
    var = defaults[4:] if var is None else var
    roles = (("shunt_to_ground", "shunt_to_ground", "bridge")
             if roles is None else roles)
    return PolicyBoundRFT005T007Circuit.from_policy(
        p,
        inductor_tree=InductorTree(5, exp055.L_EDGES if tree is None else tree),
        inductor_types=("LQP02HV",)*4 if inductor_types is None else inductor_types,
        physical_order=FOUR_ORDER if physical_order is None else physical_order,
        coupling_pairs=FOUR_K if k_slots is None else k_slots,
        capacitor_placement=CapacitorPlacement(5, fixed, var, ic_fixed),
        fixed_c_types=("GJM01", "GJM01", "GJM01", "PCB_PATTERN_C")
                       if kinds is None else kinds,
        variable_roles=roles
    )


class T005T007PolicyCircuitTests(unittest.TestCase):
    def test_t005_exp042_four_l_saved_vector_matches_without_parasite(self):
        _, vec = exp042.policy_and_seed()
        bound = build("RF-T005")
        proof = bound.validate_candidate(vec)
        self.assertTrue(proof["component_policy_pass"])
        self.assertEqual(proof["installed_shunt_parasites"], 0)
        self.assertEqual(bound.schema.vector_length, 29)
        self.assertEqual(bound.topology.capacitor_edges, exp042.C_EDGES)
        np.testing.assert_allclose(
            bound.evaluator(3).il(vec),
            exp042.Evaluator(load_constraint("RF-T005", allow_trial=True), 3).il(vec),
            atol=1e-9, rtol=0
        )
        self.assertTrue(np.isfinite(
            bound.evaluator(3).summary(vec)["worst_IL_db"]
        ))  # Candidate promotion flags live only on public NominalCircuit.

    def test_t007_exp055_four_l_saved_vector_and_independent_mna(self):
        p = load_constraint("RF-T007", allow_trial=True)
        vec = np.asarray(json.loads(
            (RUNS / "EXP-055/checkpoints/cv1_input_tip_best.json").read_text()
        )["vector"], float)
        edges = exp055.capacitor_edges("cv1_input_tip")
        bound = build(
            "RF-T007", fixed=edges[:4], var=edges[4:7],
            kinds=("GJM01", "GJM01", "PCB_PATTERN_C", "PCB_PATTERN_C"),
            roles=("shunt_to_ground", "bridge", "bridge")
        )
        proof = bound.validate_candidate(vec)
        self.assertEqual(proof["installed_shunt_parasites"], 1)
        self.assertEqual(bound.topology.capacitor_edges, edges)
        self.assertEqual(bound.schema.constant_caps_pf, (0.5,))
        self.assertEqual(bound.topology.capacitor_q[-1], 40.)
        self.assertEqual(bound.topology.capacitor_q[4:7], (35.,)*3)
        np.testing.assert_allclose(
            bound.evaluator(3).il(vec),
            exp055.Evaluator(p, 3, "cv1_input_tip", True).il(vec),
            atol=1e-9, rtol=0
        )
        independent = exp055.independent_mna(p, vec, "cv1_input_tip", 3)
        self.assertTrue(independent["pass"], independent)
        self.assertFalse(proof["independent_mna_checked"])

    def test_t007_zero_variable_only_fixed_parasitic_remains(self):
        p = load_constraint("RF-T007", allow_trial=True)
        vec = np.asarray(json.loads(
            (RUNS / "EXP-055/checkpoints/cv1_input_tip_best.json").read_text()
        )["vector"], float)
        edges = exp055.capacitor_edges("cv1_input_tip")
        b007 = build("RF-T007", fixed=edges[:4], var=edges[4:7],
                     kinds=("GJM01", "GJM01", "PCB_PATTERN_C", "PCB_PATTERN_C"),
                     roles=("shunt_to_ground", "bridge", "bridge"))
        b005 = build("RF-T005", fixed=edges[:4], var=edges[4:7],
                     kinds=("GJM01", "GJM01", "PCB_PATTERN_C", "PCB_PATTERN_C"),
                     roles=("shunt_to_ground", "bridge", "bridge"))
        v = vec.copy()
        v[11:] = 0.
        self.assertTrue(b007.validate_candidate(v)["component_policy_pass"])
        self.assertTrue(b005.validate_candidate(v)["component_policy_pass"])
        self.assertEqual(b007.topology.capacitor_edges[-1], (3, -1))
        self.assertEqual(b007.schema.decode(v).capacitors_pf_by_setting[0][-1], 0.5)
        self.assertEqual(len(b005.topology.capacitor_edges), 7)
        self.assertGreater(float(np.max(np.abs(b007.evaluator(3).il(v) -
                                               b005.evaluator(3).il(v)))), 1e-6)
        np.testing.assert_allclose(
            b005.evaluator(3).il(v),
            exp055.Evaluator(p, 3, "cv1_input_tip", False).il(v),
            atol=1e-9, rtol=0
        )

    def test_t007_zero_to_three_shunts_and_no_hot_hot_parasites(self):
        for constraint in ("RF-T005", "RF-T007"):
            for n in range(4):
                var = ((3, -1), (2, -1), (1, -1))[:n]
                c = build(constraint, fixed=((0, 1),), var=var,
                          kinds=("PCB_PATTERN_C",),
                          roles=("shunt_to_ground",)*n)
                x = np.r_[np.full(4, 3.), .1, (.01, -.01, .02), np.zeros(6*n)]
                with self.subTest(constraint=constraint,n=n):
                    result = c.validate_candidate(x)
                    self.assertTrue(result["component_policy_pass"])
                    self.assertEqual(result["installed_shunt_parasites"],
                                     n if constraint == "RF-T007" else 0)
                    self.assertEqual(c.topology.capacitor_q[-n:] if n and constraint=="RF-T007"
                                     else (), (40.,)*n if constraint=="RF-T007" else ())
                    self.assertEqual(c.schema.encode(c.schema.decode(x)).tolist(), x.tolist())
        with self.assertRaises(ValueError):
            build("RF-T007", fixed=(), kinds=(),
                  var=((3,-1),(2,-1),(1,-1),(0,1)),
                  roles=("shunt_to_ground",)*3+("bridge",))
        hot = build("RF-T007", fixed=(), kinds=(), var=((0, 1), (1, 2)),
                    roles=("bridge", "series"))
        self.assertEqual(hot.schema.constant_caps_pf, ())

    def test_t007_two_dtc_placeholder_legacy_vector_mapping(self):
        p = load_constraint("RF-T007", allow_trial=True)
        vec = np.asarray(json.loads(
            (RUNS / "EXP-055/checkpoints/cv1_input_tip_best.json").read_text()
        )["vector"], float)
        legacy = exp055.Evaluator(p, 3, "two_dtc", True)
        placeholder = vec.copy()
        placeholder[12+3*np.arange(6)] = 0.
        x = np.r_[placeholder[:11], placeholder[11:].reshape(6,3)[:,[0,2]].ravel()]
        edges = exp055.capacitor_edges("two_dtc")
        bound = build("RF-T007", fixed=edges[:4],
                      var=(edges[4],edges[6]), kinds=("GJM01","GJM01",
                      "PCB_PATTERN_C","PCB_PATTERN_C"),
                      roles=("shunt_to_ground","bridge"))
        self.assertEqual(bound.schema.vector_length,23)
        self.assertTrue(bound.validate_candidate(x)["component_policy_pass"])
        np.testing.assert_allclose(
            bound.evaluator(3).il(x), legacy.il(placeholder),
            atol=1e-9, rtol=0
        )

    def test_t005_zero_gjm_exp043_3l_and_two_gjm_case(self):
        archive = RUNS / "EXP-043"
        spec = importlib.util.spec_from_file_location(
            "t005_legacy_search_3l", archive / "search_3l.py")
        source = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(source)
        p = load_constraint("RF-T005", allow_trial=True)
        for name in ("zero_gjm_double", "two_gjm_bridge"):
            row = json.loads((archive / "checkpoints" / (name+".json")).read_text())
            var = source.CONFIGS[name][1]
            types = tuple("GJM01" if q=="GJM" else "PCB_PATTERN_C"
                          for q in source.CONFIGS[name][0])
            circuit = PolicyBoundRFT005T007Circuit.from_policy(
                p, inductor_tree=InductorTree(4, source.L_EDGES),
                inductor_types=("LQP02HV",)*3,
                physical_order=(0,2,1), coupling_pairs=((0,2),(2,1)),
                capacitor_placement=CapacitorPlacement(4,source.CF_EDGES,var),
                fixed_c_types=types,
                variable_roles=tuple("shunt_to_ground" if -1 in e else "bridge"
                                     for e in var)
            )
            vec = np.asarray(row["vector"],float)
            with self.subTest(config=name):
                self.assertTrue(circuit.validate_candidate(vec)["component_policy_pass"])
                np.testing.assert_allclose(circuit.evaluator(3).il(vec),
                                           source.Evaluator(p,name,3).il(vec),
                                           atol=1e-9,rtol=0)

    def test_reject_wrong_trial_and_unauthorized_legacy_composite_c(self):
        for constraint in ("RF-T005", "RF-T007"):
            with self.subTest(trial=constraint):
                forged=load_constraint(constraint, allow_trial=True)
                forged["components"]["IC_VARIABLE_C"]["q"]=90
                with self.assertRaisesRegex(ValueError,"approved registry"):
                    PolicyBoundRFT005T007Circuit.from_policy(
                        forged, inductor_tree=InductorTree(5,exp055.L_EDGES),
                        inductor_types=("LQP02HV",)*4, physical_order=FOUR_ORDER,
                        coupling_pairs=FOUR_K,
                        capacitor_placement=CapacitorPlacement(5),
                        fixed_c_types=(), variable_roles=()
                    )
        for other in ("RF-T008", "RF-F003"):
            with self.assertRaises(ValueError):
                build(other)
        with self.assertRaises(ValueError):
            build("RF-T005",ic_fixed=((3,-1),))
        with self.assertRaises(ValueError):
            build("RF-T007",ic_fixed=((3,-1),))
        with self.assertRaises(ValueError):
            build("RF-T007",roles=("shunt_to_ground","bridge","shunt_to_ground"))
        with self.assertRaises(ValueError):
            build("RF-T007",kinds=("GJM01",)*2)

    def test_reject_out_of_range_caps_q_spd_and_nonadjacent_k(self):
        vec = np.asarray(json.loads(
            (RUNS / "EXP-055/checkpoints/cv1_input_tip_best.json").read_text()
        )["vector"], float)
        edges = exp055.capacitor_edges("cv1_input_tip")
        bound=build("RF-T007",fixed=edges[:4],var=edges[4:7],
                    kinds=("GJM01","GJM01","PCB_PATTERN_C","PCB_PATTERN_C"),
                    roles=("shunt_to_ground","bridge","bridge"))
        for at, invalid in ((0,.39),(0,27.01),(8,.101),(4,100.01),
                            (6,.201),(11,3.01)):
            bad=vec.copy()
            bad[at]=invalid
            with self.subTest(position=at), self.assertRaises(ValueError):
                bound.validate_candidate(bad)
        with self.assertRaises(ValueError):
            build("RF-T007",inductor_types=("LQP02",)*4)
        forbidden=build("RF-T007",fixed=edges[:4],var=edges[4:7],
                        kinds=("GJM01","GJM01","PCB_PATTERN_C","PCB_PATTERN_C"),
                        roles=("shunt_to_ground","bridge","bridge"),
                        k_slots=FOUR_K+((0,2),))
        v=np.r_[vec[:11],.03,vec[11:]]
        with self.assertRaises(ValueError):
            forbidden.validate_candidate(v)
        decoded = bound.schema.decode(vec)
        rows = list(decoded.capacitors_pf_by_setting)
        rows[1] = (rows[1][0]+.1,) + rows[1][1:]
        with self.assertRaises(ValueError):
            bound.validate_candidate(CircuitValues(
                decoded.inductances_nh,decoded.coupling_k,tuple(rows)
            ))


if __name__=="__main__":
    unittest.main()
