"""Do not conflate recovered three-C trial ZIP with formal two-C RF-F002."""
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.verify_external_trial_zip import MANIFEST, verify_zip


class ExternalTrialZipTests(unittest.TestCase):
    def test_static_manifest_is_explicitly_trial_and_not_retained_in_repo(self):
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual("RF-T004", data["constraint_id"])
        self.assertEqual("RF-F002", data["base_constraint_id"])
        self.assertEqual(35, data["members_count"])
        self.assertEqual(475557, data["uncompressed_bytes"])
        self.assertEqual(118646, data["raw_bytes"])
        self.assertFalse(data["formal_exp017_30db_vector_recovered"])
        self.assertFalse(data["original_archive_held_in_github"])
        self.assertFalse(data["archive_retention_verified"])
        self.assertEqual(35, len({r["path"] for r in data["members"]}))

    def test_verifier_checks_content_without_extraction(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            zippath = root / "trial.zip"
            with zipfile.ZipFile(zippath, "w") as zipfileobj:
                zipfileobj.writestr("entry.txt", b"trial input")
            entry_bytes = b"trial input"
            with zipfile.ZipFile(zippath) as archive:
                crc = f"{archive.getinfo('entry.txt').CRC:08x}"
            manifest = {
                "constraint_id": "RF-T004",
                "formal_exp017_30db_vector_recovered": False,
                "original_archive_held_in_github": False,
                "archive_retention_verified": False,
                "raw_bytes": zippath.stat().st_size,
                "archive_sha256": hashlib.sha256(zippath.read_bytes()).hexdigest(),
                "members_count": 1,
                "uncompressed_bytes": len(entry_bytes),
                "members": [{
                    "path": "entry.txt", "bytes": len(entry_bytes),
                    "crc32": crc,
                    "sha256": hashlib.sha256(entry_bytes).hexdigest(),
                }],
            }
            mpath = root / "manifest.json"
            mpath.write_text(json.dumps(manifest), encoding="utf-8")
            report = verify_zip(zippath, mpath)
            self.assertTrue(report["member_sha256_pass"])
            self.assertFalse(report["formal_rf_f002_checkpoint_restored"])
            manifest["members"][0]["sha256"] = "0" * 64
            mpath.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_zip(zippath, mpath)
            manifest["members"][0]["path"] = "../entry.txt"
            mpath.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_zip(zippath, mpath)


if __name__ == "__main__":
    unittest.main()
