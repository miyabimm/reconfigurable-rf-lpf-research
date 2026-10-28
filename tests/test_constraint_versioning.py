"""Formal/trial constraint identity, immutable snapshots and cost Pareto guardrails."""
import json
import tempfile
import unittest
from pathlib import Path

from src.lpf.constraint_versions import load_constraint, constraint_fingerprint, _merge
from src.lpf.constraints import check_counts, chip_area

ROOT = Path(__file__).resolve().parents[1]


class VersionedConstraintsTests(unittest.TestCase):
    def test_formal_snapshot_matches_active_rf_file(self):
        active = load_constraint()
        registry = json.loads((ROOT / "rf/constraints/registry.json").read_text())
        snapshot_path = ROOT / "rf/constraints/formal" / (
            registry["active_formal_id"] + ".json")
        self.assertEqual(active, json.loads(snapshot_path.read_text()))
        self.assertEqual(active["active_constraint_id"], registry["active_formal_id"])
        self.assertEqual(active["active_constraint_status"], "formal")
        self.assertIsNone(active["area_budget"]["hard_cap"])
        self.assertEqual(len(constraint_fingerprint(active)), 64)

    def test_cost_is_not_an_rf_feasibility_limit(self):
        self.assertGreater(chip_area(n_lqp02=8), 6)
        self.assertTrue(check_counts(n_lqp02=8))
        self.assertFalse(check_counts(n_pcb=4))
        self.assertFalse(check_counts(n_var=3))

    def test_authorized_trial_is_explicit_and_resolved_from_fixed_formal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            directory = root / "rf/constraints/formal"
            directory.mkdir(parents=True)
            (directory / "RF-F001.json").write_text(
                (ROOT / "rf/constraints/formal/RF-F001.json").read_text())
            trial_dir = root / "rf/constraints/trial"
            trial_dir.mkdir(parents=True)
            trial = {
                "constraint_id": "RF-T001", "status": "trial",
                "base_constraint_id": "RF-F001", "study_authorized": True,
                "study_variable_c_layout": {"branch_count": 3,
                                            "shunt_to_ground": 3,
                                            "non_ground_bridge": 0},
                "overrides": {"components": {
                    "IC_VARIABLE_C": {"max_branches_principle": 3}}}
            }
            (trial_dir / "RF-T001.json").write_text(json.dumps(trial))
            registry = {
                "schema_version": 1, "active_formal_id": "RF-F001",
                "formal": {"RF-F001": {
                    "file": "data/constraints/formal/RF-F001.json", "state": "approved",
                    "effective_constraint_sha256": constraint_fingerprint(load_constraint("RF-F001"))}},
                "trial": {"RF-T001": {
                    "file": "data/constraints/trial/RF-T001.json",
                    "state": "study_authorized", "base_constraint_id": "RF-F001"}}
            }
            (root / "rf/constraints/registry.json").write_text(
                json.dumps(registry))
            with self.assertRaises(ValueError):
                load_constraint("RF-T001", root=root)
            formal = load_constraint(root=root)
            resolved = load_constraint("RF-T001", root=root, allow_trial=True)
            self.assertEqual(formal["components"]["IC_VARIABLE_C"]
                             ["max_branches_principle"], 2)
            self.assertEqual(resolved["components"]["IC_VARIABLE_C"]
                             ["max_branches_principle"], 3)
            self.assertEqual(resolved["active_constraint_status"], "trial")
            self.assertNotEqual(constraint_fingerprint(formal),
                                constraint_fingerprint(resolved))

    def test_trial_overrides_reject_bad_types_and_unknown_fields(self):
        baseline = load_constraint()
        valid = {"components": {"IC_VARIABLE_C": {
            "max_branches_principle": 3}}}
        self.assertEqual(_merge(baseline, valid)["components"]
                         ["IC_VARIABLE_C"]["max_branches_principle"], 3)
        bad_overrides = (
            {"components": {"IC_VARIABLE_C": {
                "max_branches_principle": "3"}}},
            {"components": {"IC_VARIABLE_C": {
                "max_branches_principle": True}}},
            {"components": {"IC_VARIABLE_C": {
                "positions_allowed_by_default": [3]}}},
            {"components": {"IC_VARIABLE_C": 3}},
            {"components": {"UNRECOGNIZED_PART": {"q": 20}}},
            {"phase3": False},
            {"components": []},
        )
        for bad in bad_overrides:
            with self.subTest(override=bad), self.assertRaises(ValueError):
                _merge(baseline, bad)

    def test_trials_are_not_automatically_adopted(self):
        with self.assertRaises(ValueError):
            load_constraint("RF-T001")
        self.assertEqual(load_constraint("RF-T001", allow_trial=True)["active_constraint_status"], "trial")
        self.assertEqual(load_constraint("RF-T002", allow_trial=True)["active_constraint_status"], "trial")
        with self.assertRaises(ValueError):
            load_constraint("RF-F000")
        self.assertEqual(load_constraint()["active_constraint_id"],
                         json.loads((ROOT / "rf/constraints/registry.json").read_text())["active_formal_id"])


if __name__ == "__main__":
    unittest.main()
