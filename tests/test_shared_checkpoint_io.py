"""Shared checkpoint primitives must not depend on legacy P4-A schemas."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments/matching_limit"))

from lpf import checkpoint_io
from p4_sharding import atomic_write_json, canonical_config_hash


class SharedCheckpointIOTests(unittest.TestCase):
    def test_legacy_imports_forward_without_altering_function_identity(self):
        self.assertIs(atomic_write_json, checkpoint_io.atomic_write_json)
        self.assertIs(canonical_config_hash, checkpoint_io.canonical_config_hash)

    def test_hash_is_deterministic_unicode_safe_and_order_independent(self):
        a = {"a": {"x": 1, "y": "回路"}, "b": [1, 2]}
        b = {"b": [1, 2], "a": {"y": "回路", "x": 1}}
        self.assertEqual(checkpoint_io.canonical_config_hash(a),
                         checkpoint_io.canonical_config_hash(b))
        self.assertEqual(64, len(checkpoint_io.canonical_config_hash(a)))

    def test_atomic_json_preserves_data_and_leaves_no_temporary_files(self):
        payload = {"run_id": "Phase 2", "status": "nonconverged",
                   "attempts": [{"vector": [0.1, 0.2], "label": "試験"}]}
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "nested" / "run.json"
            checkpoint_io.atomic_write_json(target, payload)
            self.assertEqual(payload, json.loads(target.read_text(encoding="utf-8")))
            self.assertEqual([], list(target.parent.glob(".*.tmp")))
            self.assertEqual(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                target.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
