#!/usr/bin/env python3
"""W4 Phase 2: crosswalk original EXP-042 Actions ZIP members to Git checkpoints.

Runs read-only; recomputes ZIP SHA256/CRC, verifies unchanged historical files,
compares saved numeric *records* and full parameter vectors. Does NOT rerun RF
solvers or authorize removal of any original checkpoint or ZIP.
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
from preserve_exp042_actions_artifacts import validate, inspect_zip  # noqa: E402

BASE = "87717a55673cb1cff43474a77d00088106b04c0c"
ARCHIVE = ROOT / "data/repository_reviews/w4_exp042_actions_original_zip_b64_20261018.json"
RUN = ROOT / "experiments/chatgpt_topology_search/runs/EXP-042"
SOURCES = {
    "rft005-target-30": "selected_checkpoints_rft005.json",
    "rft005-target-35": "selected_checkpoints_rft005.json",
    "rft005-independent-7001": "verified_7001.json",
    "area-cf1": "checkpoints/cf1.json",
    "area-cf2": "checkpoints/cf2.json",
    "area-both": "checkpoints/both.json",
    "pcb-pcb_cf1": "checkpoints/pcb_cf1.json",
    "pcb-pcb_cf2": "checkpoints/pcb_cf2.json",
    "pcb-pcb_both": "checkpoints/pcb_both.json",
    "4L-passband-magnetic-Q": "passband_magnetic_q_probe.json",
}
FIELDS = [
    "artifact_id", "artifact_name", "run_id", "member_path", "member_bytes",
    "member_sha256", "byte_identical_git_paths",
    "curated_git_path", "curated_git_blob_sha1", "json_record_comparison",
    "candidate_or_variant", "artifact_solver_success",
    "curated_solver_success", "full_vector_max_abs_delta",
    "metric_max_abs_delta", "metric_fields_compared", "comparison_gate",
    "retention", "owner_delete_approval",
]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def max_delta(a, b):
    if len(a) != len(b) or not a:
        return None
    try:
        values = [abs(float(x) - float(y)) for x, y in zip(a, b)]
        return max(values) if all(math.isfinite(v) for v in values) else None
    except (ValueError, TypeError):
        return None


def compare_metric(a, b, mapping):
    deltas = []
    compared = []
    for x, y in mapping:
        if x in a and y in b:
            v = abs(float(a[x]) - float(b[y]))
            if not math.isfinite(v):
                raise AssertionError("Nonfinite metric: " + x)
            deltas.append(v)
            compared.append(x + "->" + y)
    return (max(deltas) if deltas else None, ";".join(compared))


def check_context():
    assert git("rev-parse", BASE) == BASE
    changed = git("diff", "--name-only", BASE, "HEAD").splitlines()
    assert not any(p.startswith((
        "experiments/", "data/parasitics/", "data/constraints/",
        "data/validation/", "data/catalog/", "data/pareto_snapshots/",
        "candidates/",
    )) or p in ("data/bands.csv", "data/design_constraints.json") for p in changed)
    assert not git("diff", "--diff-filter=D", "--name-only", BASE, "HEAD")
    # W3 old 46 source guard is separately checked by regression.
    for rel in ("manifest.json", "selected_checkpoints_rft005.json",
                "verified_7001.json"):
        path = RUN / rel
        assert path.is_file()
        assert git("rev-parse", BASE + ":" + str(path.relative_to(ROOT))) == git_blob(path.read_bytes())


def archive_members():
    data = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    validate(data)  # original ten ZIP hashes + all 19 member SHA + CRC
    out = []
    for entry in data["entries"]:
        raw = base64.b64decode(entry["archive_zip_base64"], validate=True)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for member in z.namelist():
                b = z.read(member)
                member_info = next(x for x in entry["members"] if x["path"] == member)
                assert sha256(b) == member_info["sha256"]
                out.append((entry, member, b))
    assert len(out) == 19
    return out


def exact_git_sha_index():
    # All Git tracked present files, not just known curated checkpoints.
    # Metadata, diagnostics, and source scripts are eligible for exact match.
    names = [x for x in git("ls-files", "-z").split("\0") if x]
    indices = collections.defaultdict(list)
    for rel in names:
        f = ROOT / rel
        if f.is_file() and not f.is_symlink():
            indices[sha256(f.read_bytes())].append(rel)
    return indices


def compare_one(entry, member, data, curated):
    """Return factual relation; stage mismatches are not data inconsistencies."""
    name = entry["artifact_name"]
    if not member.endswith(".json"):
        return "non_json_log_or_exit_code", "", "", "", None, None, "", "preserve_source_log"
    art = json.loads(data)
    if "independent" in member and member != "verification_7001.json":
        variant = str(art.get("variant", ""))
        ckpt = curated if "verification" in curated else {}
        numbers = [
            ("maximum_IL_difference_db", "max_IL_difference_db"),
            ("max_power_balance_residual_W", "max_power_balance_residual_W"),
            ("min_L_eigenvalue_nH", "M_min_eig_nH"),
        ]
        metric, keys = compare_metric(art, ckpt.get("verification", {}), numbers)
        return "independent_MNA_metadata_crosscheck", variant, "", "", None, metric, keys, "retain_original_and_checkpoint"
    if member.startswith("area_") and "independent" not in member:
        variant = art.get("variant", "")
        metrics, keys = compare_metric(art["dense"], curated["verification"], [
            ("worst_il_db", "worst_IL_db"),
            ("min_h2_db", "min_H2_db"),
            ("min_h3_db", "min_H3_db"),
            ("M_min_eig_nH", "M_min_eig_nH"),
        ])
        delta = max_delta(art["selected"]["vector"], curated["vector"])
        if delta is None:
            raise AssertionError("Cannot compare 29-vector " + member)
        stage = "same_selected_vector" if delta <= 1e-10 and metrics is not None and metrics <= 1e-8 else "different_selected_vector_or_metrics"
        return ("area_variant", variant, str(art["selected"].get("solver_success", "")),
                "", delta, metrics, keys, stage)
    if member.startswith("target_"):
        cid = "EXP042-30m005" if "30" in member else "EXP042-35m005"
        cand = next(x for x in curated["candidates"] if x["id"] == cid)
        metrics, keys = compare_metric(art["verification"], cand["full_band_1001"], [
            ("worst_il_db", "worst_il_db"),
            ("min_h2_db", "min_h2_db"),
            ("min_h3_db", "min_h3_db"),
        ])
        vec = cand["params"]["flattened_vector"]
        delta = max_delta(art["selected"]["vector"], vec)
        if delta is None:
            raise AssertionError("Cannot compare target selected 29-vector: " + member)
        stage = ("same_selected_vector" if delta <= 1e-10 and metrics is not None and metrics <= 1e-8 and
                 bool(art["selected"]["solver_success"]) == bool(cand["solver_success"])
                 else "different_optimizer_stage_not_duplicate_candidate")
        return ("SLSQP_stage", cid, str(art["selected"]["solver_success"]),
                str(cand["solver_success"]), delta, metrics, keys, stage)
    if member == "verification_7001.json":
        deltas = []
        for measured in art["verification"]:
            known = next(x for x in curated["checks"] if x["id"] == measured["id"])
            assert measured["segments"] == known["segments"] == 28
            assert measured["grid_points_per_segment"] == known["grid_points_per_segment"] == 7001
            assert measured["independent_MNA_points"] == known["independent_MNA_points"] == 84
            met, fields = compare_metric(measured["dense"], known["dense"], [
                ("worst_il_db", "worst_il_db"),
                ("min_h2_db", "min_h2_db"),
                ("min_h3_db", "min_h3_db"),
            ])
            assert met is not None
            deltas.append(met)
        delta = max(deltas)
        return ("7001_point_independent_report", "EXP042-30m005;EXP042-35m005",
                "", "", None, delta, "dense_IL;min_H2;min_H3_for_both_candidates",
                "same_recorded_finite_grid_metrics" if delta <= 1e-8 else "reported_metrics_differ")
    if member == "driven_passband_magnetic_q.json":
        return ("passband_q_source_record", "pcb_cf1", "", "", None, None,
                "source_checkpoint;variant", "retained_distinct_diagnostic_not_a_checkpoint_duplicate")
    return ("unclassified_json", "", "", "", None, None, "", "retain_semantic_role_unresolved")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--emit-csv-chunks", action="store_true")
    args = ap.parse_args()
    check_context()
    mapping = exact_git_sha_index()
    archive = archive_members()
    curated_cache = {}
    rows = []
    for entry, member, data in archive:
        name = entry["artifact_name"]
        key = name[len("exp042-"):]
        assert key in SOURCES, ("unmapped artifact name", name)
        counterpart = RUN / SOURCES[key]
        counterpart_rel = str(counterpart.relative_to(ROOT))
        if counterpart.is_file():
            if counterpart_rel not in curated_cache:
                curated_cache[counterpart_rel] = json.loads(counterpart.read_text(encoding="utf-8"))
            related = curated_cache[counterpart_rel]
            (record, variant, art_success, curated_success,
             vecdiff, metdiff, fields, gate) = compare_one(entry, member, data, related)
            counterpart_sha = git_blob(counterpart.read_bytes())
        else:
            # The original Actions ZIP is preserved. Do not invent an
            # equivalent curated checkpoint path when one does not exist.
            record = "no_corresponding_curated_git_checkpoint"
            variant = key
            art_success = ""
            curated_success = ""
            vecdiff = metdiff = None
            fields = ""
            gate = "only_archived_actions_artifact_provenance"
            counterpart_sha = ""
        rows.append({
            "artifact_id": entry["artifact_id"],
            "artifact_name": name,
            "run_id": entry["run_id"],
            "member_path": member,
            "member_bytes": len(data),
            "member_sha256": sha256(data),
            "byte_identical_git_paths": ";".join(sorted(mapping.get(sha256(data), []))),
            "curated_git_path": counterpart_rel,
            "curated_git_blob_sha1": counterpart_sha,
            "json_record_comparison": record,
            "candidate_or_variant": variant,
            "artifact_solver_success": art_success,
            "curated_solver_success": curated_success,
            "full_vector_max_abs_delta": "" if vecdiff is None else format(vecdiff, ".17g"),
            "metric_max_abs_delta": "" if metdiff is None else format(metdiff, ".17g"),
            "metric_fields_compared": fields,
            "comparison_gate": gate,
            "retention": "retain_original_actions_zip_and_git_checkpoint",
            "owner_delete_approval": "not_granted",
        })
    assert len(rows) == 19
    by_gate = collections.Counter(r["comparison_gate"] for r in rows)
    complete = {
        "original_zip_count": 10,
        "member_count": len(rows),
        "members_byte_identical_to_existing_tracked_git_files": sum(bool(r["byte_identical_git_paths"]) for r in rows),
        "variants_with_identical_selected_29_vector_and_metrics": sum(
            r["json_record_comparison"] == "area_variant" and r["comparison_gate"] == "same_selected_vector"
            for r in rows),
        "target_30_stage": next(r["comparison_gate"] for r in rows if r["member_path"] == "target_30.json"),
        "target_35_stage": next(r["comparison_gate"] for r in rows if r["member_path"] == "target_35.json"),
        "dense_7001_finite_grid_record_relation": next(r["comparison_gate"] for r in rows if r["member_path"] == "verification_7001.json"),
        "by_comparison_gate": dict(sorted(by_gate.items())),
        "unrepresented_curated_checkpoint_member_count": sum(
            r["comparison_gate"] == "only_archived_actions_artifact_provenance" for r in rows),
        "unrepresented_curated_checkpoint_member_paths": [
            r["artifact_name"] + ":" + r["member_path"] for r in rows
            if r["comparison_gate"] == "only_archived_actions_artifact_provenance"
        ],
        "owner_approved_removals": 0,
        "files_deleted": 0,
        "rf_optimization_runs": 0,
        "new_independent_mna_runs": 0,
        "limitations": [
            "Byte matching uses SHA256 over tracked Git file content.",
            "Semantic comparison is only on explicitly mapped recorded checkpoint metrics and 29-vectors.",
            "Different stage is not corruption; never merge distinct optimizer stages automatically.",
            "Independent record comparison does not recompute RF network response or prove global minima.",
            "Raw Actions ZIP and Git curated checkpoints must both be retained pending owner approval.",
        ],
    }
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    with (out / "exp042_zip_member_to_git_crosswalk.csv").open("w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    (out / "exp042_crosswalk_summary.json").write_text(
        json.dumps(complete, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("W4_CROSSWALK_SUMMARY=" + json.dumps(complete, separators=(",", ":")))
    if args.emit_csv_chunks:
        csv_content=(out / "exp042_zip_member_to_git_crosswalk.csv").read_text(encoding="utf-8")
        for i in range(0,len(csv_content),4500):
            print("W4_CROSSWALK_CHUNK=" + json.dumps({
                "seq":i//4500,"text":csv_content[i:i+4500]
            },separators=(",",":")))
    print("W4_CROSSWALK_PASS: 19 verified ZIP members and curated Git checkpoints reviewed; 0 deletions or RF runs")


if __name__ == "__main__":
    main()
