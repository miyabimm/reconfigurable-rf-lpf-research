#!/usr/bin/env python3
"""W4 Phase 2: recover six exact original EXP-042 Actions JSON members.

Read-only, not a solver: original bytes from ten SHA256-validated ZIP archives.
Restore historical *raw source copies*, NOT synthetic curated checkpoints.
No changes to original run/experiment, RF conditions, catalog or Pareto register.
"""
from __future__ import annotations

import argparse
import base64
import collections
import csv
import hashlib
import io
import json
import math
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from preserve_exp042_actions_artifacts import validate  # noqa: E402

BASE = "c1b874c1e240ac3fedfeaa67064783f0918ed9a2"
ARCHIVE = ROOT / "data/repository_reviews/w4_exp042_actions_original_zip_b64_20261018.json"
CROSSWALK = ROOT / "data/repository_reviews/w4_exp042_member_crosswalk_20261018.csv"
GIT_COPY_DIR = ROOT / "data/repository_reviews/w4_exp042_recovered_original_members_20261018"
TARGETS = {
    "exp042-area-cf2": ("area_cf2.json", "area_cf2_independent.json"),
    "exp042-area-both": ("area_both.json", "area_both_independent.json"),
    "exp042-pcb-pcb_cf2": ("area_pcb_cf2.json", "area_pcb_cf2_independent.json"),
}
CHECKPOINT_ROOT = ROOT / "experiments/chatgpt_topology_search/runs/EXP-042/checkpoints"
REPORT_NAME = "w4_exp042_missing_variant_source_review_20261018.json"


def git(*args):
    return subprocess.check_output(["git", *args], text=True, cwd=ROOT).strip()


def sha256(buf):
    return hashlib.sha256(buf).hexdigest()


def validate_origin():
    assert git("rev-parse", BASE) == BASE
    diff = git("diff", "--name-only", BASE, "HEAD").splitlines()
    assert not git("diff", "--diff-filter=D", "--name-only", BASE, "HEAD"), (
        "W4 source restoration may not delete files"
    )
    assert not any(p.startswith((
        "experiments/", "candidates/", "data/catalog/", "data/pareto_snapshots/",
        "data/parasitics/", "data/validation/", "data/constraints/"
    )) or p in ("data/bands.csv", "data/design_constraints.json") for p in diff), (
        "W4 must not change original studies, catalogs, constraints or S2Ps"
    )
    for p in ("experiments/chatgpt_topology_search/runs/EXP-042/manifest.json",
              "experiments/chatgpt_topology_search/runs/EXP-042/selected_checkpoints_rft005.json",
              "data/repository_reviews/w4_exp042_actions_original_zip_b64_20261018.json"):
        original_sha = git("rev-parse", BASE + ":" + p)
        actual_sha = git("hash-object", p)
        assert original_sha == actual_sha, "Original source changed: " + p


def numeric(value, context):
    val = float(value)
    assert math.isfinite(val), "nonfinite number " + context
    return val


def load_zip_originals():
    d = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    validate(d)
    items = {}
    ids = {}
    for e in d["entries"]:
        name = e["artifact_name"]
        if name not in TARGETS:
            continue
        raw_zip = base64.b64decode(e["archive_zip_base64"], validate=True)
        with zipfile.ZipFile(io.BytesIO(raw_zip)) as z:
            for fname in TARGETS[name]:
                raw = z.read(fname)
                given = next(m for m in e["members"] if m["path"] == fname)
                assert sha256(raw) == given["sha256"] and len(raw) == given["bytes"]
                key = (name, fname)
                assert key not in items
                items[key] = raw
                ids[key] = (e["artifact_id"], e["run_id"], e["archive_zip_sha256"])
    assert len(items) == 6 and len(ids) == 6
    return items, ids


def crosswalk_invariants(items):
    with CROSSWALK.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 19
    refs = {(r["artifact_name"], r["member_path"]): r for r in rows}
    for key, raw in items.items():
        r = refs[key]
        assert r["member_sha256"] == sha256(raw)
        assert r["comparison_gate"] == "only_archived_actions_artifact_provenance"
        assert r["curated_git_blob_sha1"] == ""
        assert not (ROOT / r["curated_git_path"]).exists()
    return refs


def area_details(main):
    assert isinstance(main.get("selected", {}).get("vector"), list)
    vector = main["selected"]["vector"]
    assert len(vector) == 29, ("expected complete 29-vector", len(vector))
    vect = [numeric(v, "vector") for v in vector]
    dense = main.get("dense", {})
    metrics = {f: numeric(dense[f], f) for f in (
        "worst_il_db", "min_h2_db", "min_h3_db", "M_min_eig_nH"
    )}
    reported = main.get("selected", {}).get("solver_success")
    assert isinstance(reported, bool)
    # Classification is of *reported* finite sampled data, not a new RF analysis.
    reported_h30 = min(metrics["min_h2_db"], metrics["min_h3_db"]) >= 30.0
    return {
        "vector_29": vect,
        "selected_solver_success_reported": reported,
        "source_dense_metrics_reported": metrics,
        "h2_h3_30dB_pass_on_reported_mesh": reported_h30,
        "source_declared_variant": main.get("variant"),
        "source_declared_run_or_config": {
            k: main[k] for k in ("constraint_id", "experiment_id", "run_id", "grid_points_per_segment",
                                "segments", "chip_area_units", "objective")
            if k in main
        },
        "source_top_level_keys": sorted(main),
        "selected_keys": sorted(main["selected"]),
    }


def inspect():
    validate_origin()
    originals, source_ids = load_zip_originals()
    cross = crosswalk_invariants(originals)
    records = []
    for artifact in sorted(TARGETS):
        original = TARGETS[artifact]
        main = json.loads(originals[(artifact, original[0])])
        independent = json.loads(originals[(artifact, original[1])])
        details = area_details(main)
        artifact_id, run_id, zip_sha = source_ids[(artifact, original[0])]
        assert source_ids[(artifact, original[1])] == (artifact_id, run_id, zip_sha)
        target_source = str(CHECKPOINT_ROOT / artifact.removeprefix("exp042-") + ".json") if False else ""
        # The three missing historical selected-checkpoint paths are explicit.
        variant = artifact.removeprefix("exp042-").removeprefix("area-").removeprefix("pcb-")
        selected_path = CHECKPOINT_ROOT / (variant + ".json")
        assert not selected_path.exists(), "Assumed missing curated source now present: " + str(selected_path)
        records.append({
            "artifact_name": artifact,
            "variant": variant,
            "source_constraint_scope": "RF-T005 (trial based on RF-F003) — EXP-042",
            "original_actions_run_id": run_id,
            "original_actions_artifact_id": artifact_id,
            "archive_zip_sha256": zip_sha,
            "main_json": original[0],
            "main_json_bytes": len(originals[(artifact, original[0])]),
            "main_json_sha256": sha256(originals[(artifact, original[0])]),
            "independent_json": original[1],
            "independent_json_bytes": len(originals[(artifact, original[1])]),
            "independent_json_sha256": sha256(originals[(artifact, original[1])]),
            "recovered_main_repo_path": str((GIT_COPY_DIR / original[0]).relative_to(ROOT)),
            "recovered_independent_repo_path": str((GIT_COPY_DIR / original[1]).relative_to(ROOT)),
            "curated_checkpoint_path_absent": str(selected_path.relative_to(ROOT)),
            "recorded_run_details": details,
            "independent_report_top_level_keys": sorted(independent),
            "independent_report_raw_fields": independent,
            "independent_report_not_recomputed": True,
            "candidate_register_unchanged": True,
            "replay_executed": False,
            "owner_delete_approval": "not_granted",
            "disposition": "retain_source_exact_originals_not_curated_candidate",
        })
    return originals, records


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--emit-original-chunks", action="store_true")
    p.add_argument("--verify-committed-recovery", action="store_true")
    args = p.parse_args()
    originals, records = inspect()
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)

    # Never generate replacements under experiments/.../checkpoints.
    for (name, member), raw in originals.items():
        (out / member).write_bytes(raw)
    result = {
        "schema_version": 1,
        "study_phase": "Phase 2",
        "source_main_commit": BASE,
        "checked_out_sha": git("rev-parse", "HEAD"),
        "status": "read_only_historical_artifact_source_extraction_no_new_rf_run",
        "source_actions_zip_count": 3,
        "recovered_original_member_count": 6,
        "recorded_variants": len(records),
        "records": records,
        "new_solver_runs": 0,
        "independent_network_validation_new_runs": 0,
        "new_curated_checkpoint_claims": 0,
        "owner_approved_deletions": 0,
        "performed_deletions": 0,
        "adoption_limits": [
            "These are exact recorded historical Actions bytes; not independently re-optimized.",
            "H2/H3 pass uses JSON's reported sampled metrics only; do not assert new verification.",
            "Selected solver_success and independent-MNA metadata are historical reports, not re-run proof.",
            "No candidate added to governed catalog/Pareto snapshot without dedicated evaluation.",
            "Do not replace older curated results or overwrite missing checkpoints.",
        ],
    }
    (out / REPORT_NAME).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.verify_committed_recovery:
        for (_, member), raw in originals.items():
            dest = GIT_COPY_DIR / member
            assert dest.is_file(), "Recovery copy absent: " + str(dest)
            assert dest.read_bytes() == raw, "Exact original member byte mismatch: " + member
        # Source report's observed commit is time-variable; compare data fields.
        fixed = json.loads((ROOT / ("data/repository_reviews/" + REPORT_NAME)).read_text(encoding="utf-8"))
        for key in ("source_actions_zip_count", "recovered_original_member_count", "records",
                    "new_solver_runs", "new_curated_checkpoint_claims", "performed_deletions"):
            assert fixed[key] == result[key], "Fixed W4 recovery report mismatch: " + key
        print("W4_SOURCE_RESTORE_PASS: six original members recovered byte-identically, no solver/candidate mutation")
    print("W4_SOURCE_RECOVERY_SUMMARY=" + json.dumps({
        "members": len(originals), "variants": len(records),
        "reported_metrics": [{
            "variant": r["variant"],
            "artifact_id": r["original_actions_artifact_id"],
            "run_id": r["original_actions_run_id"],
            "metrics": r["recorded_run_details"]["source_dense_metrics_reported"],
            "selected_solver_success": r["recorded_run_details"]["selected_solver_success_reported"],
            "h30_reported_mesh_pass": r["recorded_run_details"]["h2_h3_30dB_pass_on_reported_mesh"],
            "independent_keys": r["independent_report_top_level_keys"],
        } for r in records],
        "original_member_bytes": sum(len(v) for v in originals.values()),
        "new_rf_runs": 0, "deleted": 0,
    }, ensure_ascii=False, separators=(",", ":")))
    if args.emit_original_chunks:
        # CI log output intended only for capturing exact bytes into fixed
        # Git files; no secrets or untrusted executable code executed here.
        for (_name, member), raw in sorted(originals.items()):
            b64 = base64.b64encode(raw).decode("ascii")
            for j in range(0, len(b64), 4000):
                print("W4_RECOVER_RAW_B64_CHUNK=" + json.dumps({
                    "member": member, "part": j // 4000,
                    "sha256": sha256(raw), "bytes": len(raw), "base64": b64[j:j+4000]
                }, separators=(",", ":")))
        snapshot = (out / REPORT_NAME).read_text(encoding="utf-8")
        for i in range(0, len(snapshot), 4000):
            print("W4_RECOVER_REPORT_CHUNK=" + json.dumps({
                "seq": i // 4000, "text": snapshot[i:i+4000]
            }, ensure_ascii=False, separators=(",", ":")))
    print("W4_SOURCE_AUDIT_PASS: three missing curated variants inspectable in original ZIP, all originals retained")


if __name__ == "__main__":
    main()
