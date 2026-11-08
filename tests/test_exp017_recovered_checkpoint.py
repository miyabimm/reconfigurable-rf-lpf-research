"""Recovered formal EXP-017 near-miss is genuine and separately replayed.

Never modifies the original EXP-017 manifest or promotes a 3-C RF-T004 trial.
"""
import json
import math
import unittest
from pathlib import Path

from scripts.verify_exp017_recovered_mna import replay, CANDIDATE, ROOT


class RecoveredFormalCheckpointTests(unittest.TestCase):
    def test_checkpoint_is_complete_and_not_a_trial_substitute(self):
        candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))
        self.assertEqual("EXP-017", candidate["experiment_id"])
        self.assertEqual("RF-F002", candidate["constraint_id"])
        self.assertEqual("formal", candidate["constraint_class"])
        self.assertEqual(30, candidate["requirement_db"])
        self.assertEqual(23, len(candidate["x_logL_logC_k_6x2Cv_epi"]))
        self.assertEqual(6, len(candidate["topology"]["variable_setting_order"]))
        self.assertEqual(2, len(candidate["topology"]["variable_capacitor_edges"]))
        self.assertEqual(4, len(candidate["topology"]["inductor_series"]))
        self.assertEqual(157492, candidate["source"]["zip_size_bytes"])
        self.assertEqual("e685e918a4592a9ec53ffb8221c8b4d59fdf8604dd9119cf3cabbf42174a0daf",
                         candidate["source"]["zip_sha256"])
        self.assertFalse(candidate["source"]["raw_original_zip_git_committed"])
        self.assertFalse(candidate["status"]["nominal_IL_le_0p30"])
        self.assertTrue(candidate["status"]["source_vector_recovered"])

    def test_independent_full_six_setting_mna_replay(self):
        r = replay(1001)
        self.assertTrue(r["strict_finite_grid_30db"])
        self.assertFalse(r["il_le_0p30db"])
        self.assertEqual(6, len(r["per_setting"]))
        self.assertEqual(28028, r["evaluated_frequency_samples"])
        self.assertAlmostEqual(0.3012482451489075, r["worst_il_db"], places=7)
        self.assertAlmostEqual(30.004999999986865, r["min_h2_db"], places=5)
        self.assertAlmostEqual(30.004641701571376, r["min_h3_db"], places=5)
        self.assertGreater(r["k_min_eigenvalue"], 0.8)
        self.assertLess(r["max_mna_nodal_il_difference_db"], 1e-7)
        self.assertLess(r["max_power_balance_residual_W"], 1e-12)


if __name__ == "__main__":
    unittest.main()
