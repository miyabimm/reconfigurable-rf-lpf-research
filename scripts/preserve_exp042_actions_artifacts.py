#!/usr/bin/env python3
"""Read-only EXP-042 GitHub Actions artifact archive / restoration verifier.

capture: download fixed, already-observed artifact IDs with actions:read GitHub
token; validate ZIP CRCs and all members; optionally emit a byte-exact base64
Git-preservable snapshot as bounded CI-log chunks (no source mutation).
verify: validate stored original ZIP bytes, fixed metadata and member SHA256
without network, token, RF calculation, or untrusted ZIP extraction to disk.

This does NOT validate RF numerical results or claim independent MNA.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import datetime
import hashlib
import io
import json
import os
import posixpath
import subprocess
import sys
import urllib.error
import urllib.request
import urllib.parse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "data/repository_reviews/w4_exp042_actions_artifact_metadata_20261018.json"
ARCHIVE = ROOT / "data/repository_reviews/w4_exp042_actions_original_zip_b64_20261018.json"
SOURCE_BASE = "eced0bd838f62781f4c17be93241749afa0a21f9"
API = "https://api.github.com/repos/MasayaTakagi/reconfigurable-rf-lpf-research"
MAX_ZIP = 2_000_000
MAX_MEMBER = 5_000_000
MAX_ALL_UNPACKED = 15_000_000


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def assert_pristine_original_sources():
    assert git("rev-parse", SOURCE_BASE) == SOURCE_BASE
    diff = git("diff", "--name-only", SOURCE_BASE, "HEAD").splitlines()
    assert not any(p.startswith((
        "experiments/", "data/parasitics/", "data/constraints/", "data/validation/",
        "candidates/", "data/catalog/"
    )) or p in ("data/bands.csv", "data/design_constraints.json") for p in diff)
    assert not git("diff", "--diff-filter=D", "--name-only", SOURCE_BASE, "HEAD")


def expected_metadata():
    data = json.loads(META.read_text(encoding="utf-8"))
    assert data["phase"] == "Phase 2" and data["total_runs"] == 6
    assert data["artifacts_metadata_visible"] == 10
    items = []
    for run in data["runs"]:
        for a in run["artifacts"]:
            assert a["expired_at_observation"] is False
            assert a["expires_at"].startswith("2027-01-15T")
            items.append({
                "run_id": run["run_id"], "workflow": run["workflow"],
                "artifact_id": a["id"], "artifact_name": a["name"],
                "metadata_size_bytes": a["bytes"],
                "metadata_expires_at": a["expires_at"],
            })
    assert len(items) == len({x["artifact_id"] for x in items}) == 10
    return sorted(items, key=lambda x: x["artifact_id"])


def url_json(path, token):
    req = urllib.request.Request(API + path, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "phase2-exp042-read-only-artifact-preservation",
    })
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


class StripAuthorizationOnCrossHostRedirect(urllib.request.HTTPRedirectHandler):
    """Do not forward GitHub Bearer credential to signed Azure storage URL."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if (redirected is not None and
            urllib.parse.urlsplit(req.full_url).netloc !=
                urllib.parse.urlsplit(newurl).netloc):
            redirected.remove_header("Authorization")
        return redirected


def download_zip(artifact_id, token):
    url = API + "/actions/artifacts/" + str(artifact_id) + "/zip"
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "phase2-exp042-read-only-artifact-preservation",
    })
    opener = urllib.request.build_opener(StripAuthorizationOnCrossHostRedirect())
    with opener.open(req, timeout=45) as response:
        data = response.read(MAX_ZIP + 1)
    assert 0 < len(data) <= MAX_ZIP, (artifact_id, "unexpected size")
    assert zipfile.is_zipfile(io.BytesIO(data)), ("not ZIP", artifact_id)
    return data


def inspect_zip(raw):
    with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
        members = []
        total = 0
        seen = set()
        assert len(zf.infolist()) > 0 and len(zf.infolist()) <= 50
        assert zf.testzip() is None, "CRC failure"
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            normalized = posixpath.normpath(name)
            assert (not name.startswith("/") and not name.startswith("../")
                    and normalized not in (".", "..") and not normalized.startswith("../")
                    and ":" not in name.split("/")[0]
                    and "\x00" not in name
                    and not info.is_dir()
                    and info.file_size <= MAX_MEMBER
                    and normalized not in seen), "unsafe/oversized/duplicated ZIP member"
            seen.add(normalized)
            member_bytes = zf.read(info.filename)
            total += len(member_bytes)
            assert total <= MAX_ALL_UNPACKED
            members.append({
                "path": normalized, "bytes": len(member_bytes),
                "sha256": sha256(member_bytes),
                "is_utf8": _is_utf8(member_bytes),
            })
        return sorted(members, key=lambda x: x["path"])


def _is_utf8(data):
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def capture(log_chunks=False):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required for real artifact retrieval")
    records = []
    for expected in expected_metadata():
        ident = expected["artifact_id"]
        live = url_json("/actions/artifacts/" + str(ident), token)
        assert live.get("id") == ident
        assert live.get("name") == expected["artifact_name"]
        assert not live.get("expired"), "Previously visible artifact now expired"
        assert live.get("workflow_run", {}).get("id") == expected["run_id"]
        raw = download_zip(ident, token)
        members = inspect_zip(raw)
        entry = {
            **expected, "archive_zip_byte_count": len(raw),
            "archive_zip_sha256": sha256(raw),
            "archive_zip_base64": base64.b64encode(raw).decode("ascii"),
            "members": members,
        }
        records.append(entry)
        print("W4_ARTIFACT_VERIFIED=" + json.dumps({
            k: entry[k] for k in
            ("run_id", "artifact_id", "artifact_name",
             "archive_zip_byte_count", "archive_zip_sha256", "members")
        }, separators=(",", ":"), ensure_ascii=False))
    archive = {
        "schema_version": 1, "phase": "Phase 2",
        "purpose": "byte-exact original GitHub Actions artifact ZIP retention",
        "source_main_sha": SOURCE_BASE,
        "captured_date_utc": datetime.datetime.now(
            datetime.timezone.utc).date().isoformat(),
        "capture_note": "Artifact ZIP bytes retrieved through authenticated read-only GitHub Actions API; copied as base64 in Git for lossless restoration. ZIP SHA256 verifies the saved archive, and member SHA256 verifies each member. No RF re-execution.",
        "source_metadata_path": str(META.relative_to(ROOT)),
        "entries": records,
        "artifact_count": len(records),
        "zip_members_count": sum(len(r["members"]) for r in records),
        "solver_executions": 0, "deleted_source_files": 0,
        "provenance_class": "original_Actions_artifact_bytes_from_2026_10_17_runs",
    }
    validate(archive)
    payload = json.dumps(archive, ensure_ascii=False, indent=2) + "\n"
    print("W4_ARTIFACT_CAPTURE_SUMMARY=" + json.dumps({
        "artifact_count": archive["artifact_count"],
        "member_count": archive["zip_members_count"],
        "archive_bytes": sum(e["archive_zip_byte_count"] for e in records),
        "payload_characters": len(payload),
        "source_main_sha": SOURCE_BASE,
        "solver_executions": 0,
    }, separators=(",", ":")))
    if log_chunks:
        # Serialize JSON characters inside each individual log line safely.
        for i in range(0, len(payload), 5000):
            print("W4_ARTIFACT_CAPTURE_CHUNK=" + json.dumps(
                {"seq": i // 5000, "text": payload[i:i + 5000]},
                ensure_ascii=False, separators=(",", ":")))
    print("W4_ARTIFACT_CAPTURE_PASS: original ZIP and CRC verified; no RF recomputation or deletion")


def validate(data):
    expected = expected_metadata()
    entries = data["entries"]
    assert data["schema_version"] == 1 and data["phase"] == "Phase 2"
    assert data["source_main_sha"] == SOURCE_BASE
    assert data["solver_executions"] == 0 and data["deleted_source_files"] == 0
    assert data["artifact_count"] == len(entries) == len(expected)
    assert [x["artifact_id"] for x in entries] == [x["artifact_id"] for x in expected]
    n_members = 0
    for entry, exp in zip(entries, expected):
        for k, val in exp.items():
            assert entry[k] == val, ("source metadata changed", k, val)
        raw = base64.b64decode(entry["archive_zip_base64"], validate=True)
        assert len(raw) == entry["archive_zip_byte_count"]
        assert sha256(raw) == entry["archive_zip_sha256"]
        assert inspect_zip(raw) == entry["members"], "ZIP member details differ"
        n_members += len(entry["members"])
    assert n_members == data["zip_members_count"]
    print("W4_ARTIFACT_ARCHIVE_PASS: " + str(len(entries))
          + " ZIP archives byte-exact restorable with SHA256/CRC verified; "
          + str(n_members) + " members; zero new RF calculation")
    return n_members


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--capture", action="store_true")
    p.add_argument("--log-chunks", action="store_true")
    p.add_argument("--verify-repository", action="store_true")
    a = p.parse_args()
    assert a.capture != a.verify_repository
    assert_pristine_original_sources()
    if a.capture:
        capture(log_chunks=a.log_chunks)
    else:
        data = json.loads(ARCHIVE.read_text(encoding="utf-8"))
        validate(data)


if __name__ == "__main__":
    main()
