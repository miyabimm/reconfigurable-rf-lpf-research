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
from lpf.rf_core.port_parasitics import (
    _load_verified, get_two_port_s, s_to_abcd,
)
from lpf.rf_core._grid import CASES, validated_band_segments
from lpf.search.performance import compile_requirements, build_evaluation_grid
from test_issue323_dependencies import make


class Phase2S2PCacheAndGridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_constraint("RF-T008", allow_trial=True)

    def test_s2p_kernel_origin_default_root_and_interpolation(self):
        from lpf.rf_core import port_parasitics as s2p
        self.assertEqual(Path(s2p.__file__).resolve(), ROOT / 'src/lpf/rf_core/port_parasitics.py')
        self.assertFalse((ROOT / 'src/lpf/port_parasitics.py').exists())
        self.assertEqual(s2p.ROOT, ROOT)
        for role in ('input_parasitic', 'output_parasitic'):
            lo = s2p.get_two_port_s(self.policy, role, 810e6)
            hi = s2p.get_two_port_s(self.policy, role, 811e6)
            mid = s2p.get_two_port_s(self.policy, role, 810.5e6)
            np.testing.assert_array_equal(mid, 0.5 * lo + 0.5 * hi)
            np.testing.assert_array_equal(mid, s2p.get_two_port_s(self.policy, role, 810.5e6, root=ROOT))
            for f in (0., 6e9):
                np.testing.assert_array_equal(s2p.get_two_port_s(self.policy, role, f),
                                              s2p.get_two_port_s(self.policy, role, f, root=ROOT))

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
        with (ROOT / "rf/bands.csv").open(newline="", encoding="utf-8") as file:
            bands = list(csv.DictReader(file))
        req = compile_requirements(self.policy, bands)
        grid = build_evaluation_grid(req, 3)
        self.assertEqual(len(bands), 28)
        self.assertEqual(len(CASES), 6)
        self.assertEqual(grid.frequency_hz.shape, (84,))
        self.assertEqual(set(grid.setting.tolist()), set(range(6)))
        for i, row in enumerate(bands):
            self.assertEqual(grid.segment[i*3:i*3+3].tolist(), [i]*3)
            self.assertEqual(CASES[grid.setting[i*3]], row['case'])
            self.assertEqual(float(grid.frequency_hz[i*3]), float(row['low_mhz'])*1e6)
            self.assertEqual(float(grid.frequency_hz[i*3+2]), float(row['high_mhz'])*1e6)
        _, _, model, _, _ = make('RF-T008')
        a, b = model.evaluator(grid), model.evaluator(grid)
        for name in ('pre', 'post'):
            self.assertFalse(np.shares_memory(getattr(a, name), getattr(b, name)))
            self.assertTrue(np.all(np.isfinite(getattr(a, name))))
            with self.assertRaises(ValueError):
                getattr(a, name).setflags(write=True)

    def test_band_csv_validation_fails_closed_instead_of_reclassifying_h3(self):
        with (ROOT / "rf/bands.csv").open(newline="", encoding="utf-8") as file:
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
        with self.assertRaises(ValueError):
            validated_band_segments(rows)

    def test_band_coverage_rejects_missing_or_duplicated_regions_subbands(self):
        with (ROOT / "rf/bands.csv").open(newline="", encoding="utf-8") as file:
            original = list(csv.DictReader(file))
        self.assertEqual(len(validated_band_segments(original)), 28)
        scenarios = (
            # 28 rows and all six cases still present, but B71 H2 vanished.
            ({"case": "B71", "region": "H2"}, {"region": "UL", "type": "pass"}),
            # B13 and B14 must each have an H3 interval.
            ({"case": "B13+B14", "region": "H3", "note": "B14"},
             {"note": "B13"}),
            # Unknown subband labels must not silently become valid.
            ({"case": "B13+B14", "region": "DL", "note": "B14"},
             {"note": "B15"}),
            # Single-band entries must not acquire an ambiguous subband.
            ({"case": "B8", "region": "UL"}, {"note": "B8"}),
        )
        for match, updates in scenarios:
            rows = [dict(row) for row in original]
            found = next(i for i, row in enumerate(rows)
                         if all(row[key] == value for key, value in match.items()))
            rows[found].update(updates)
            self.assertEqual(len(rows), 28)
            self.assertEqual({row["case"] for row in rows}, set(CASES))
            with self.subTest(match=match, updates=updates):
                with self.assertRaisesRegex(ValueError, "subband"):
                    validated_band_segments(rows)

    def test_invalid_integer_grid_counts_are_rejected(self):
        req = compile_requirements(self.policy, ROOT / 'rf/bands.csv')
        for points in (0, -1, 1, 1.5, 3.0, True, None):
            with self.subTest(points=points), self.assertRaises(ValueError):
                build_evaluation_grid(req, points)


if __name__ == "__main__":
    unittest.main()
