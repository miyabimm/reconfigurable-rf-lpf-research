"""RF-F003 fixed parasitics and RF-T005/T006 explicit trial regression."""
import hashlib
import json
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np
from src.lpf.constraint_versions import (load_constraint, validate_registry,
                                         constraint_fingerprint,
                                         validate_variable_c_connections)
from src.lpf.port_parasitics import (get_two_port_s, external_cascade_abcd,
                                      external_transducer_gain, _load_verified)
from src.lpf.constraints import check_counts
from src.lpf.trial_stopband import (
    evaluate_trial_additional_stopband, summarize_full_lpf_trial_feasibility,
)

ROOT = Path(__file__).resolve().parents[1]


class RFF003T005Tests(unittest.TestCase):
    def test_formal_registry_and_compat(self):
        registry = validate_registry()
        self.assertEqual(registry["active_formal_id"], "RF-F003")
        formal = load_constraint()
        self.assertEqual(formal["active_constraint_id"], "RF-F003")
        self.assertEqual(formal, json.loads(
            (ROOT/"data/design_constraints.json").read_text("utf-8")))
        self.assertEqual(constraint_fingerprint(formal),
                         registry["formal"]["RF-F003"]["effective_constraint_sha256"])
        self.assertEqual(formal["components"]["IC_VARIABLE_C"]["max_branches_principle"], 2)
        self.assertEqual(formal["components"]["IC_VARIABLE_C"]["max_total_variable_pf_per_branch"], 3)
        self.assertEqual(formal["components"]["IC_VARIABLE_C"]["q"], 35)
        self.assertEqual(formal["coupling_limits"]["chip_chip_strong_adjacent_abs_k_max"], 0.1)
        self.assertEqual(formal["coupling_limits"]["pcb_pcb_abs_k_max_default"], 0.1)
        self.assertEqual(formal["chip_inductor_placement"]["strong_abs_k_max"], 0.1)

    def test_trial_changes_only_branch_count(self):
        with self.assertRaises(ValueError):
            load_constraint("RF-T005")
        formal = load_constraint("RF-F003")
        trial = load_constraint("RF-T005", allow_trial=True)
        copy = json.loads(json.dumps(formal))
        copy["components"]["IC_VARIABLE_C"]["max_branches_principle"] = 3
        for key in ("active_constraint_id","active_constraint_status"):
            trial.pop(key, None)
            copy.pop(key, None)
        for key in ("trial_base_constraint_id","trial_variable_c_layout"):
            trial.pop(key, None)
        self.assertEqual(trial, copy)
        self.assertFalse(check_counts(n_var=3))
        resolved = load_constraint("RF-T005", allow_trial=True)
        self.assertTrue(check_counts(n_var=3, resolved_policy=resolved))
        self.assertFalse(check_counts(n_var=4, resolved_policy=resolved))
        self.assertTrue(validate_variable_c_connections(
            [{"a":1,"b":0},{"a":1,"b":2,"role":"bridge"},{"a":2,"b":3,"role":"series"}],
            resolved))

    def test_t006_adds_only_mandatory_3_to_6ghz_stopband(self):
        formal = load_constraint("RF-F003")
        with self.assertRaises(ValueError):
            load_constraint("RF-T006")
        trial = load_constraint("RF-T006", allow_trial=True)
        self.assertEqual(trial["active_constraint_id"], "RF-T006")
        self.assertEqual(trial["trial_base_constraint_id"], "RF-F003")
        self.assertEqual(trial["active_constraint_status"], "trial")
        self.assertTrue(check_counts(n_var=2, resolved_policy=trial))
        self.assertFalse(check_counts(n_var=3, resolved_policy=trial))
        self.assertFalse(check_counts(n_var=3, resolved_policy=formal))
        extra = trial["trial_additional_stopband"]
        self.assertEqual((extra["low_hz"], extra["high_hz"], extra["sample_step_hz"]),
                         (3_000_000_000, 6_000_000_000, 1_000_000))
        self.assertEqual(extra["min_attenuation_db"], 20)
        self.assertEqual(len(extra["settings"]), 6)
        self.assertEqual(extra["reference_planes"], "external_input_to_external_output")
        resolved_without_metadata = json.loads(json.dumps(trial))
        for key in ("active_constraint_id", "active_constraint_status",
                    "trial_base_constraint_id", "trial_variable_c_layout",
                    "trial_additional_stopband"):
            resolved_without_metadata.pop(key)
        original_without_identity = json.loads(json.dumps(formal))
        for key in ("active_constraint_id", "active_constraint_status"):
            original_without_identity.pop(key)
        self.assertEqual(resolved_without_metadata, original_without_identity)
        self.assertNotEqual(constraint_fingerprint(trial), constraint_fingerprint(formal))
        self.assertNotIn("trial_additional_stopband", load_constraint("RF-T005", allow_trial=True))
        self.assertNotIn("trial_additional_stopband", load_constraint())

    def test_t006_wideband_sweep_and_full_lpf_gate(self):
        trial = load_constraint("RF-T006", allow_trial=True)
        eye = np.eye(2, dtype=complex)
        with patch("src.lpf.trial_stopband.external_transducer_gain", return_value=0.001) as gain:
            ok = evaluate_trial_additional_stopband(trial, lambda setting, f: eye)
        self.assertEqual(gain.call_count, 6 * 3001)
        self.assertEqual(ok["total_points"], 18006)
        self.assertTrue(ok["passes_minimum"])
        self.assertEqual(ok["worst"]["frequency_hz"], 3_000_000_000)
        with self.assertRaisesRegex(ValueError, "Complete RF-T006"):
            summarize_full_lpf_trial_feasibility(
                trial, worst_il_db=0.83, min_h2_db=30.05, min_h3_db=30.05)
        summary = summarize_full_lpf_trial_feasibility(
            trial, worst_il_db=0.83, min_h2_db=30.05, min_h3_db=30.05,
            additional_stopband=ok)
        self.assertTrue(summary["mandatory_finite_grid_pass"])
        self.assertFalse(summary["nominal_il_goal_pass"])
        current = [None]
        def callback(setting, f):
            current[0] = setting
            return eye
        def gain_at_one_failure(policy, frequency_hz, lpf_abcd):
            return 0.02 if current[0] == "B71" and frequency_hz == 3_000_000_000 else 0.001
        with patch("src.lpf.trial_stopband.external_transducer_gain",
                   side_effect=gain_at_one_failure):
            failed = evaluate_trial_additional_stopband(trial, callback)
        self.assertFalse(failed["passes_minimum"])
        self.assertEqual(failed["worst"]["setting"], "B71")
        self.assertEqual(failed["worst"]["frequency_hz"], 3_000_000_000)
        summary = summarize_full_lpf_trial_feasibility(
            trial, worst_il_db=0.83, min_h2_db=30.05, min_h3_db=30.05,
            additional_stopband=failed)
        self.assertFalse(summary["mandatory_finite_grid_pass"])
        with self.assertRaisesRegex(ValueError, "No authorized"):
            evaluate_trial_additional_stopband(load_constraint(), lambda c, f: eye)

    def test_legacy_RF_F002_stays_frozen(self):
        previous = load_constraint("RF-F002")
        self.assertEqual(previous["components"]["IC_VARIABLE_C"]["q"],50)
        self.assertEqual(previous["components"]["IC_VARIABLE_C"]["max_total_variable_pf_per_branch"],1.5)
        self.assertEqual(previous["coupling_limits"]["pcb_pcb_abs_k_max_default"],0.15)

    def test_s2p_files_and_cached_cascade(self):
        formal = load_constraint()
        cfg = formal["external_port_parasitics"]
        self.assertTrue(cfg["runtime"]["load_once_per_worker"])
        self.assertFalse(cfg["runtime"]["recompute_RLC_per_objective_call"])
        for role in ("input_parasitic","output_parasitic"):
            spec = cfg[role]
            path = ROOT/spec["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),spec["sha256"])
            self.assertEqual(len(path.read_text("ascii").splitlines()),6004)
            for f in (0.0,0.5e6,3e9,6e9):
                s = get_two_port_s(formal,role,f)
                self.assertEqual(s.shape,(2,2))
                self.assertTrue(np.all(np.isfinite(s)))
                self.assertAlmostEqual(abs(s[1,0]-s[0,1]),0,places=9)
                self.assertLessEqual(float(np.linalg.svd(s, compute_uv=False)[0]),1+1e-8)
            for f in (-1, 6e9+1):
                with self.assertRaises(ValueError):
                    get_two_port_s(formal,role,f)
        n_before = _load_verified.cache_info().hits
        get_two_port_s(formal,"input_parasitic",2e9)
        self.assertGreater(_load_verified.cache_info().hits,n_before)
        identity=np.eye(2,dtype=complex)
        for f in (0.,1e9,2.5e9,6e9):
            t=external_cascade_abcd(formal,f,identity)
            self.assertTrue(np.all(np.isfinite(t)))
            gain=external_transducer_gain(formal,f,identity)
            self.assertGreater(gain,0.0)
            self.assertLessEqual(gain,1+1e-8)


if __name__=="__main__":
    unittest.main()
