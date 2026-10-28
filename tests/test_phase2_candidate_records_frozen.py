"""S4B SHA-pinned fixture records; opt in via LPF_EVIDENCE_ROOT.

Fixtures are read only. Synthetic callback convergence is NOT historic solver
convergence; original manifests/status/results are never reclassified.
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
from lpf.phase2_models.candidate_records import CandidateRecord, record_candidate, recheck_record, pareto_report
from lpf.phase2_models.problem_seed import definition_fingerprint, vector_fingerprint
from lpf.phase2_models.sampled_epigraph import SampledEpigraph
from lpf.phase2_models.staged_optimization import run_c1_staged


FIXTURES = (
    ("RF-T005", "experiments/chatgpt_topology_search/runs/EXP-042/preliminary_js_5pt.json",
     "c1a1dcdb61cb49ed983256cc4a115425342d6fb60ed1e095c4fb5aaf5d750930"),
    ("RF-T007", "experiments/chatgpt_topology_search/runs/EXP-055/checkpoints/cv1_input_tip_best.json",
     "65d0d637e8a233c97e6a76b39dca2a15aaf90e46b2380ffaae1b6ea1689361cb"),
    ("RF-T008", "data/pareto_snapshots/rf_t008_exp058_area4p667_20261020.json",
     "f1a63cf5bcc95fc1b1f31f0bb7c20b2f52b035ac8084e89289ec76f794b6fca9"),
)


def frozen(root, trial, path, digest):
    raw = (root / path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("Frozen fixture SHA mismatch")
    doc = json.loads(raw)
    if trial == "RF-T005":
        v = doc["vector"]
        x = v["L_nH"] + v["fixed_C_pF"] + v["k_adjacent"] + np.asarray(v["variable_C_by_setting_pF"]).ravel().tolist()
        var = ((3, -1), (4, -1), (1, 2))
        kinds = ("GJM01", "GJM01", "GJM01", "PCB_PATTERN_C")
        roles = ("shunt_to_ground", "shunt_to_ground", "bridge")
    elif trial == "RF-T007":
        x = doc["vector"]
        var = ((3, -1), (0, 3), (1, 2))
        kinds = ("GJM01", "GJM01", "PCB_PATTERN_C", "PCB_PATTERN_C")
        roles = ("shunt_to_ground", "bridge", "bridge")
    else:
        x = doc["best"]["vector"]
        var = ((0, 3), (1, 2))
        kinds = ("GJM01", "PCB_PATTERN_C", "PCB_PATTERN_C", "PCB_PATTERN_C")
        roles = ("bridge", "bridge")
    d = CircuitDefinition(InductorTree(5, ((0, 1), (1, 3), (1, 4), (1, 2))),
        ("LQP02HV",)*4, (0, 1, 3, 2), ((0, 1), (1, 3), (3, 2)),
        CapacitorPlacement(5, ((0, 1), (4, -1), (1, 2), (0, 3)), var,
                           var if trial == "RF-T008" else ()), kinds, roles)
    return build_nominal_circuit(load_constraint(trial, allow_trial=True), d), x


@unittest.skipUnless(os.environ.get("LPF_EVIDENCE_ROOT"), "full evidence checkout not supplied")
class FrozenCandidateRecordTests(unittest.TestCase):
    def test_sha_pinned_complete_records_roundtrip_and_limited_audit_consistency(self):
        root = Path(os.environ["LPF_EVIDENCE_ROOT"])
        for trial, path, digest in FIXTURES:
            with self.subTest(trial=trial):
                c, x = frozen(root, trial, path, digest)
                record = record_candidate(trial, c, x, limited_points=2,
                    source_provenance={"kind": "frozen", "git_head": "831e9e56754e81d69b583893181c350396acc8f5",
                        "dirty_patch_sha256": hashlib.sha256(b"").hexdigest(),
                        "input_source_sha256": digest, "path": path})
                b = record.as_dict()
                self.assertEqual(b["vector"], x)
                self.assertEqual(b["numerical"]["state"], "not_run")
                self.assertEqual(b["validation"]["independent_mna"], "passed_limited")
                evidence = b["audit"]["limited_evidence"]
                self.assertEqual(b["rf"]["metrics"]["worst_il_db"], evidence["summary"]["pass_il"]["il_db"])
                self.assertEqual(b["rf"]["metrics"]["min_h2_db"], evidence["summary"]["H2"]["il_db"])
                self.assertLessEqual(evidence["max_forward_il_error_db"], 1e-9)
                self.assertLessEqual(evidence["max_abs_power_residual_w"], 1e-12)
                restored = CandidateRecord.from_json(record.to_json())
                self.assertEqual(restored.to_json(), record.to_json())
                self.assertEqual(recheck_record(restored).to_json(), record.to_json())
                self.assertIn("numerical_not_run", pareto_report([record])["candidates"][0]["reasons"])
                self.assertEqual(hashlib.sha256((root / path).read_bytes()).hexdigest(), digest)

    def test_equal_fixture_different_evidence_depth_never_merge(self):
        root = Path(os.environ["LPF_EVIDENCE_ROOT"])
        trial, path, digest = FIXTURES[0]
        c, x = frozen(root, trial, path, digest)
        p = SampledEpigraph(c, 1)
        initial = p.seed(x, policy_id=c.policy_id, policy_fingerprint=c.policy_fingerprint,
            definition_sha256=definition_fingerprint(c.definition),
            input_sha256=vector_fingerprint(x), seed=0)
        source = {"kind": "frozen", "optimizer_kind": "synthetic_callback",
                  "git_head": "831e9e56754e81d69b583893181c350396acc8f5",
                  "dirty_patch_sha256": hashlib.sha256(b"").hexdigest(), "input_source_sha256": digest}
        staged = run_c1_staged(c, initial, coarse_points=1, fine_points=2,
            optimize_stage=lambda p, v, m, t: (v, {"success": True, "status": 0,
                "message": "synthetic callback; not historical convergence", "nit": 0, "nfev": 0}),
            source_provenance=source)
        forward = record_candidate("forward", c, x, staged_record=staged, sampled_points=2)
        independent = record_candidate("independent", c, x, staged_record=staged, limited_points=2)
        report = pareto_report([forward, independent])
        self.assertEqual(len(report["groups"]), 2)
        self.assertTrue(all(g["count"] == 1 for g in report["groups"]))
        self.assertTrue(report["candidate_promotion_blocked"])


if __name__ == "__main__":
    unittest.main()
