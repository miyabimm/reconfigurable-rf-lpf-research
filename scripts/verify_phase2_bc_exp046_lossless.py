#!/usr/bin/env python3
"""Phase 2 B/C wave 1: reversible, source-byte-exact archive of EXP-046 batches.

NO originals are modified/removed. ZIP-like envelope uses explicit per-source
zlib streams and base64 so every source path can be reconstructed verbatim.
The envelope is a Git review artifact, not a new solver or verified RF result.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import subprocess
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "c83952a74c63c204265daf225edd252dc62d14e7"
OUTFILE = "data/repository_reviews/phase2_bc_exp046_bridge_lossless_archive_20261018.json"
SOURCES = [
    f"experiments/chatgpt_topology_search/runs/EXP-046/bridge_cap_relocation_batch{k}_results.json"
    for k in (0, 1, 2)
]
EXPECTED = ((3, 130481), (3, 124259), (4, 169493))


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def git_sha1(raw: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def checked_originals() -> list[tuple[str, bytes, dict]]:
    assert git("rev-parse", BASE) == BASE
    assert git("diff", "--diff-filter=D", "--name-only", BASE, "HEAD") == ""
    changed = git("diff", "--name-only", BASE, "HEAD").splitlines()
    assert not any(
        s.startswith((".github/workflows/phase2_cleanup_w2",
                      ".github/workflows/phase2_cleanup_w3",
                      ".github/workflows/phase2_w4_exp042",
                      ".github/workflows/phase2_w4_exp046",
                      "experiments/", "candidates/", "data/constraints/",
                      "data/parasitics/", "data/validation/", "data/catalog/",
                      "data/pareto_snapshots/"))
        or s in ("data/bands.csv", "data/design_constraints.json")
        for s in changed
    ), "Wave 1 may only add review tools; originals and old workflows unchanged"
    out = []
    names: set[str] = set()
    for index, path in enumerate(SOURCES):
        raw = (ROOT / path).read_bytes()
        assert git_sha1(raw) == git("rev-parse", f"{BASE}:{path}")
        doc = json.loads(raw)
        assert doc["experiment_id"] == "EXP-046" and doc["constraint_id"] == "RF-T005"
        assert len(doc["results"]) == EXPECTED[index][0]
        assert int(doc["eval_count"]) == EXPECTED[index][1]
        assert "Independent MNA and 28x1001 for changed layouts pending" in doc["description"]
        for row in doc["results"]:
            assert len(row["vector"]) == 30
            assert all(isinstance(v, (int, float)) and
                       not isinstance(v, bool) and math.isfinite(v)
                       for v in row["vector"])
            assert row["variant"] not in names, "Original source variant collision"
            names.add(row["variant"])
        out.append((path, raw, doc))
    assert len(names) == 10
    assert sum(int(j["eval_count"]) for _, _, j in out) == 424233
    return out


def build() -> tuple[dict, dict]:
    raws = checked_originals()
    entries = []
    for path, raw, doc in raws:
        compressed = zlib.compress(raw, level=9)
        # Immediately verify bitwise reconstruction, not just JSON semantics.
        assert zlib.decompress(compressed) == raw
        entries.append({
            "source_path": path,
            "source_git_blob_sha1": git_sha1(raw),
            "source_sha256": sha256(raw),
            "source_bytes": len(raw),
            "zlib_bytes": len(compressed),
            "reported_eval_count": int(doc["eval_count"]),
            "variants": [
                {"name": r["variant"], "vector_size": len(r["vector"])}
                for r in doc["results"]
            ],
            "zlib_base64": base64.b64encode(compressed).decode("ascii"),
        })
    envelope = {
        "format": "phase2-bc-exp046-original-json-bytes-zlib-base64-v1",
        "constraint_id": "RF-T005",
        "experiment_id": "EXP-046",
        "source_main": BASE,
        "method": "per-source raw byte zlib level9 stream, base64; no JSON normalization",
        "entries": entries,
        "source_total_bytes": sum(e["source_bytes"] for e in entries),
        "compressed_binary_total_bytes": sum(e["zlib_bytes"] for e in entries),
        "original_variants": sum(len(e["variants"]) for e in entries),
        "recorded_evaluations_sum": sum(e["reported_eval_count"] for e in entries),
        "source_declared_grid": "28x5 optimization, 28x31 screening",
        "independent_mna_and_28x1001_changed_layouts": "pending_in_original_source",
        "new_independent_mna_runs": 0,
        "new_rf_optimizer_runs": 0,
        "original_deletions": 0,
        "original_workflow_disables": 0,
        "owner_deletion_approval": "not_granted",
    }
    summary = {
        "kind": "lossless_compressed_copy_for_review_no_original_retirement",
        "source_count": len(entries),
        "variant_count": envelope["original_variants"],
        "source_bytes": envelope["source_total_bytes"],
        "compressed_binary_bytes": envelope["compressed_binary_total_bytes"],
        "evaluations_reported": envelope["recorded_evaluations_sum"],
        "sources": [
            {k: e[k] for k in ("source_path", "source_git_blob_sha1",
                              "source_sha256", "source_bytes", "zlib_bytes",
                              "reported_eval_count", "variants")}
            for e in entries
        ],
        "deletions": 0,
        "rf_reruns": 0,
        "independent_mna_reruns": 0,
        "physical_validation": False,
    }
    assert summary["variant_count"] == 10
    return envelope, summary


def verify(envelope: dict, reference: dict) -> None:
    assert envelope["format"] == reference["format"]
    assert len(envelope["entries"]) == 3
    recovered: dict[str, bytes] = {}
    for member in envelope["entries"]:
        encoded = member["zlib_base64"]
        compressed = base64.b64decode(encoded, validate=True)
        assert len(compressed) == member["zlib_bytes"]
        raw = zlib.decompress(compressed)
        assert len(raw) == member["source_bytes"]
        assert sha256(raw) == member["source_sha256"]
        assert git_sha1(raw) == member["source_git_blob_sha1"]
        assert raw == (ROOT / member["source_path"]).read_bytes(), (
            "Lossless original byte mismatch " + member["source_path"]
        )
        assert member["source_path"] not in recovered
        recovered[member["source_path"]] = raw
    assert set(recovered) == set(SOURCES)
    assert envelope == reference, "Pinned consolidated source changed"


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("--output-dir", type=Path, required=True)
    cli.add_argument("--emit-envelope-chunks", action="store_true")
    cli.add_argument("--verify-committed", action="store_true")
    args = cli.parse_args()
    envelope, summary = build()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(envelope, ensure_ascii=False, indent=2) + "\n"
    artifact = args.output_dir / "exp046_bridge_raw_roundtrip.json"
    artifact.write_text(raw, encoding="utf-8")
    (args.output_dir / "exp046_bridge_roundtrip_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.verify_committed:
        target = ROOT / OUTFILE
        assert target.is_file()
        pinned = json.loads(target.read_text(encoding="utf-8"))
        verify(pinned, envelope)
        print("EXP046_LOSSLESS_COMMITTED_PASS: restored 3 source files byte-exact from pinned archive")
    if args.emit_envelope_chunks:
        for n in range(0, len(raw), 4200):
            print("EXP046_LOSSLESS_CHUNK=" + json.dumps({
                "seq": n // 4200, "text": raw[n:n+4200]
            }, ensure_ascii=False, separators=(",", ":")))
    print("EXP046_LOSSLESS_SUMMARY=" +
          json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    print("EXP046_LOSSLESS_PASS: 3 sources, 10 vectors, originals untouched; no new RF validation")


if __name__ == "__main__":
    main()
