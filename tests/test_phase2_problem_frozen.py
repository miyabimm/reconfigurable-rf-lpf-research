"""Read-only historic fixtures; opt in with LPF_EVIDENCE_ROOT full checkout.

No historical execution module or optimizer is imported. File SHA-256 values
pin the fixture bytes at main 831e9e56754e81d69b583893181c350396acc8f5.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from lpf.constraint_versions import load_constraint
from lpf.phase2_models.api import CircuitDefinition, build_nominal_circuit
from lpf.phase2_models.circuit_layout import CapacitorPlacement, InductorTree
from lpf.phase2_models.problem_seed import definition_fingerprint, vector_fingerprint
from lpf.phase2_models.sampled_epigraph import SampledEpigraph


def fixture(root, path, sha):
    raw = (root / path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError("Frozen source SHA mismatch: " + path)
    return json.loads(raw)


@unittest.skipUnless(os.environ.get("LPF_EVIDENCE_ROOT"), "full evidence checkout not supplied")
class FrozenProblemTests(unittest.TestCase):
    def test_approved_trials_read_only_fixture(self):
        root = Path(os.environ["LPF_EVIDENCE_ROOT"])
        data = [
            ("RF-T005", "experiments/chatgpt_topology_search/runs/EXP-042/preliminary_js_5pt.json",
             "c1a1dcdb61cb49ed983256cc4a115425342d6fb60ed1e095c4fb5aaf5d750930"),
            ("RF-T007", "experiments/chatgpt_topology_search/runs/EXP-055/checkpoints/cv1_input_tip_best.json",
             "65d0d637e8a233c97e6a76b39dca2a15aaf90e46b2380ffaae1b6ea1689361cb"),
            ("RF-T008", "data/pareto_snapshots/rf_t008_exp058_area4p667_20261020.json",
             "f1a63cf5bcc95fc1b1f31f0bb7c20b2f52b035ac8084e89289ec76f794b6fca9"),
        ]
        fixed = ((0, 1), (4, -1), (1, 2), (0, 3))
        for policy, path, sha in data:
            with self.subTest(policy=policy):
                doc = fixture(root, path, sha)
                if policy == "RF-T005":
                    v = doc["vector"]
                    x = np.array(v["L_nH"] + v["fixed_C_pF"] + v["k_adjacent"]
                                 + np.asarray(v["variable_C_by_setting_pF"]).ravel().tolist())
                    var = ((3, -1), (4, -1), (1, 2))
                    kinds = ("GJM01", "GJM01", "GJM01", "PCB_PATTERN_C")
                    roles = ("shunt_to_ground", "shunt_to_ground", "bridge")
                elif policy == "RF-T007":
                    x = np.array(doc["vector"])
                    var = ((3, -1), (0, 3), (1, 2))
                    kinds = ("GJM01", "GJM01", "PCB_PATTERN_C", "PCB_PATTERN_C")
                    roles = ("shunt_to_ground", "bridge", "bridge")
                else:
                    x = np.array(doc["best"]["vector"])
                    var = ((0, 3), (1, 2))
                    kinds = ("GJM01", "PCB_PATTERN_C", "PCB_PATTERN_C", "PCB_PATTERN_C")
                    roles = ("bridge", "bridge")
                d = CircuitDefinition(InductorTree(5, ((0, 1), (1, 3), (1, 4), (1, 2))),
                    ("LQP02HV",)*4, (0, 1, 3, 2), ((0, 1), (1, 3), (3, 2)),
                    CapacitorPlacement(5, fixed, var, var if policy == "RF-T008" else ()),
                    kinds, roles)
                c = build_nominal_circuit(load_constraint(policy, allow_trial=True), d)
                p = SampledEpigraph(c, 2)
                result = p.seed(x, policy_id=policy, policy_fingerprint=c.policy_fingerprint,
                    definition_sha256=definition_fingerprint(d), input_sha256=vector_fingerprint(x), seed=0)
                self.assertEqual(result["changes"], ())
                np.testing.assert_array_equal(result["vector"][:-1], x)
                np.testing.assert_array_equal(c.encode(c.decode(x)), x)
                self.assertEqual(len(p.residuals(result["vector"])), 56)
                self.assertTrue(c.validate_components(x)["candidate_promotion_blocked"])

    def test_t008_three_l_frozen_vectors(self):
        root = Path(os.environ["LPF_EVIDENCE_ROOT"])
        doc = fixture(root, "data/pareto_snapshots/rf_t008_exp058_area3_to_3p667_20261020.json",
                      "21dc10094dab9687e2c0e0877a37a6f595fe00199a929d750321fbe25a90aaf5")
        var = ((3, -1), (1, 2))
        for row in doc["observed_nondominated"]:
            kinds = ("GJM01" if row["GJM_count"] else "PCB_PATTERN_C",
                     "PCB_PATTERN_C", "PCB_PATTERN_C")
            d = CircuitDefinition(InductorTree(4, ((0, 1), (1, 2), (1, 3))),
                ("LQP02HV",)*3, (0, 2, 1), ((0, 2), (2, 1)),
                CapacitorPlacement(4, ((0, 1), (1, 2), (3, -1)), var, var),
                kinds, ("shunt_to_ground", "bridge"))
            c = build_nominal_circuit(load_constraint("RF-T008", allow_trial=True), d)
            p = SampledEpigraph(c, 1)
            x = np.asarray(row["vector"], float)
            result = p.seed(x, policy_id=c.policy_id, policy_fingerprint=c.policy_fingerprint,
                            definition_sha256=definition_fingerprint(d),
                            input_sha256=vector_fingerprint(x), seed=0)
            np.testing.assert_array_equal(result["vector"][:-1], x)
            self.assertEqual(result["changes"], ())
            self.assertEqual(len(p.residuals(result["vector"])), 28)


if __name__ == "__main__":
    unittest.main()
