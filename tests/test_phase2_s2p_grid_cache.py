"""Stage-1 fixed S2P and sampled-grid boundaries (no new RF experiment).

The canonical port_parasitics cache verifies SHA-256 and 50-ohm RI S2P;
this test ensures new forward evaluators reuse it without aliasing mutable
matrix data across different circuit instances. It is a finite-grid test.
"""
import copy
import csv
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lpf.constraint_versions import load_constraint
from lpf.port_parasitics import (
    _load_verified, get_two_port_s, s_to_abcd,
)
from lpf.phase2_models._grid import CASES, SampledExternalEvaluator, validated_band_segments


class Phase2S2PCacheAndGridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_constraint("RF-T008", allow_trial=True)

    def test_frozen_s2p_returned_matrices_do_not_alias_cached_data(self):
        p = self.policy
        q = "input_parasitic"
        f = 810.5e6  # inside 0..6GHz, between frozen 1MHz samples
        a = get_two_port_s(p, q, f, root=ROOT)
        b = get_two_port_s(p, q, f, root=ROOT)
        self.assertFalse(np.shares_memory(a, b))
        np.testing.assert_array_equal(a, b)
        before = b.copy()
        a[0, 0] = complex(999, 999)
        np.testing.assert_array_equal(
            get_two_port_s(p, q, f, root=ROOT), before
        )
        info = _load_verified.cache_info()
        self.assertGreaterEqual(info.hits, 1)
        self.assertLessEqual(info.currsize, info.maxsize)

    def test_sha_and_network_identity_fail_closed(self):
        p = copy.deepcopy(self.policy)
        p["external_port_parasitics"]["input_parasitic"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            get_two_port_s(p, "input_parasitic", 800e6, root=ROOT)
        with self.assertRaises(ValueError):
            get_two_port_s(self.policy, "unknown", 800e6, root=ROOT)
        for f in (float("nan"), float("inf"), -1., 6e9 + 1):
            with self.subTest(f=f), self.assertRaises(ValueError):
                get_two_port_s(self.policy, "input_parasitic", f, root=ROOT)
        with self.assertRaises(ValueError):
            s_to_abcd(np.eye(2, dtype=complex))  # S21 = 0

    def test_28_segments_six_settings_and_frequency_endpoints(self):
        grid = SampledExternalEvaluator(self.policy, 3)
        with (ROOT / "data/bands.csv").open(newline="", encoding="utf-8") as file:
            bands = list(csv.DictReader(file))
        self.assertEqual(len(bands), 28)
        self.assertEqual(len(CASES), 6)
        self.assertEqual(grid.f.shape, (28*3,))
        self.assertEqual(grid.pre.shape, (84, 2, 2))
        self.assertEqual(grid.post.shape, (84, 2, 2))
        self.assertEqual(set(grid.setting.tolist()), set(range(6)))
        self.assertEqual(set(grid.role.tolist()), {0, 1, 2})
        for i, row in enumerate(bands):
            self.assertEqual(grid.segment[i*3:i*3+3].tolist(), [i]*3)
            self.assertEqual(CASES[grid.setting[i*3]], row["case"])
            self.assertEqual(float(grid.f[i*3]), float(row["low_mhz"]))
            self.assertEqual(float(grid.f[i*3+2]), float(row["high_mhz"]))
        a = SampledExternalEvaluator(self.policy, 3)
        self.assertFalse(np.shares_memory(a.pre, grid.pre))
        self.assertFalse(np.shares_memory(a.post, grid.post))
        prev = a.pre[0].copy()
        grid.pre[0, 0, 0] = 999j
        np.testing.assert_array_equal(a.pre[0], prev)
        self.assertTrue(np.all(np.isfinite(a.pre)))
        self.assertTrue(np.all(np.isfinite(a.post)))

    def test_band_csv_validation_fails_closed_instead_of_reclassifying_h3(self):
        with (ROOT / "data/bands.csv").open(newline="", encoding="utf-8") as file:
            original = list(csv.DictReader(file))
        segments = validated_band_segments(original)
        self.assertEqual(len(segments), 28)
        self.assertEqual({row[0] for row in segments}, set(range(6)))
        self.assertEqual({row[1] for row in segments}, {0, 1, 2})
        for updates in (
            {"type": "stpo"},
            {"region": "H4"},
            {"type": "pass", "region": "H2"},
            {"type": "stop", "region": "UL"},
            {"case": "B999"},
            {"low_mhz": "nan"},
            {"high_mhz": "inf"},
            {"low_mhz": "-5"},
            {"low_mhz": "1400", "high_mhz": "1300"},
            {"low_mhz": ""},
        ):
            rows = [dict(row) for row in original]
            rows[2].update(updates)
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                validated_band_segments(rows)
        with self.assertRaises(ValueError):
            validated_band_segments(original[:-1])
        rows = [dict(row) for row in original]
        for item in rows:
            item["case"] = "B71"
        with self.assertRaisesRegex(ValueError, "Six band"):
            validated_band_segments(rows)

    def test_invalid_integer_grid_counts_are_rejected(self):
        for points in (0, -1, 1.5, 3.0, True, None):
            with self.subTest(points=points), self.assertRaises(ValueError):
                SampledExternalEvaluator(self.policy, points)


if __name__ == "__main__":
    unittest.main()
