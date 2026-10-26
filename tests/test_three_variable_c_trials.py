"""Approved Phase 2 trial variants must remain distinct from the RF-F001 default."""
import json
import unittest
from pathlib import Path

from src.lpf.constraint_versions import (
    constraint_fingerprint, load_constraint, validate_registry, validate_variable_c_connections,
)
from src.lpf.constraints import check_counts
from src.lpf.experiment_manifest import new_manifest, validate_manifest

ROOT = Path(__file__).resolve().parents[1]


class TrialThreeVariableCTests(unittest.TestCase):
    def test_registered_trial_scopes_and_formal_immutability(self):
        registry = validate_registry()
        self.assertEqual(registry["active_formal_id"], "RF-F003")
        self.assertTrue({"RF-T001", "RF-T002", "RF-T003", "RF-T004", "RF-T005"}.issubset(registry["trial"]))
        self.assertIn("RF-T008", registry["trial"])
        base = load_constraint("RF-F001")
        self.assertEqual(load_constraint(), json.loads((ROOT / "data/design_constraints.json").read_text()))
        self.assertEqual(base["components"]["IC_VARIABLE_C"]["max_branches_principle"], 2)
        self.assertFalse(check_counts(n_var=3))  # default check remains formal
        trials = [load_constraint(cid, allow_trial=True) for cid in ("RF-T001", "RF-T002")]
        self.assertEqual([(t["trial_variable_c_layout"]["shunt_to_ground"],
                           t["trial_variable_c_layout"]["non_ground_bridge"]) for t in trials],
                         [(3, 0), (2, 1)])
        for trial in trials:
            self.assertEqual(trial["active_constraint_status"], "trial")
            self.assertEqual(trial["trial_base_constraint_id"], "RF-F001")
            self.assertEqual(trial["components"]["IC_VARIABLE_C"]["q"], 80)
            self.assertEqual(trial["evaluation"], base["evaluation"])
            self.assertEqual(trial["area_budget"], base["area_budget"])
            self.assertEqual(trial["coupling_limits"], base["coupling_limits"])
            self.assertEqual(trial["phase3"], base["phase3"])
            self.assertNotEqual(constraint_fingerprint(trial), constraint_fingerprint(base))
        self.assertNotEqual(constraint_fingerprint(trials[0]), constraint_fingerprint(trials[1]))

    def test_explicit_opt_in_is_required(self):
        for cid in ("RF-T001", "RF-T002"):
            with self.subTest(cid=cid), self.assertRaises(ValueError):
                load_constraint(cid)
        self.assertEqual(load_constraint()["active_constraint_status"], "formal")

    def test_connection_layout_exact_three(self):
        f, t1, t2 = (load_constraint(), load_constraint("RF-T001", allow_trial=True),
                      load_constraint("RF-T002", allow_trial=True))
        shunts = [{"a": 1, "b": 0}, {"a": 3, "b": 0}, {"a": 2, "b": 0}]
        mixed = [{"a": 1, "b": 0}, {"a": 2, "b": 0},
                 {"a": 3, "b": 4, "role": "bridge"}]
        self.assertTrue(validate_variable_c_connections(shunts[:2], f))
        for branches, rule in ((shunts, f), (mixed, f), (mixed, t1), (shunts, t2),
                               (shunts[:2], t1), (shunts[:2], t2)):
            with self.subTest(branches=branches, policy=rule["active_constraint_id"]), self.assertRaises(ValueError):
                validate_variable_c_connections(branches, rule)
        self.assertTrue(validate_variable_c_connections(shunts, t1))
        self.assertTrue(validate_variable_c_connections(mixed, t2))
        for branch in ({"a": 3, "b": 4}, {"a": 3, "b": 4, "role": "series"}):
            with self.assertRaises(ValueError):
                validate_variable_c_connections(mixed[:2] + [branch], t2)

    def test_trial_manifests_are_distinct_and_not_run(self):
        for cid in ("RF-T001", "RF-T002"):
            with self.subTest(cid=cid):
                with self.assertRaises(ValueError):
                    new_manifest("EXP-016", "Three-C comparison", {"variable_c_count": 3},
                                 objective="full_lpf", seed=20261012, constraint_id=cid)
                trial = new_manifest("EXP-016", "Three-C comparison", {"variable_c_count": 3},
                                     objective="full_lpf", seed=20261012,
                                     constraint_id=cid, allow_trial=True)
                validate_manifest(trial)
                self.assertEqual(trial["execution"]["status"], "planned")
                self.assertEqual(trial["validation"]["independent"], "not_run")
                self.assertEqual(trial["constraints"]["class"], "trial")


if __name__ == "__main__":
    unittest.main()
