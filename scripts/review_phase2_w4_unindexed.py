#!/usr/bin/env python3
"""W4 Phase 2: per-file, static-source forensics for 225 previously unindexed files.

Does NOT determine semantic redundancy or authorize deletions.
"""
from __future__ import annotations

import collections
import csv
import io
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_reference_inventory import create_inventory  # noqa: E402
from triage_unlinked_evidence import (  # noqa: E402
    TEXT_EXTENSIONS, _ref_hits, _safe_read_text, _source_summary,
    resolved_markdown_references,
)

BASE = "26cacd179146bda5f5ca1cdcf0096dd61eb4faae"
ROOTS = ("data/validation/", "experiments/chatgpt_topology_search/runs/")
FIELDS = (
    "path", "git_blob_sha1", "bytes", "run_or_validation_group",
    "source_content_kind", "source_schema_sample",
    "full_path_text_ref_count", "full_path_text_ref_sources",
    "resolved_markdown_ref_count", "resolved_markdown_ref_sources",
    "workflow_full_path_ref_sources", "workflow_basename_mentions_unverified",
    "static_ref_status", "evidence_role_gate", "owner_approval", "delete_status",
)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def classify_gate(path, kind, workflow_refs, markdown_refs):
    if path == "data/validation/exp047_legacy_manifest_adapter_20261017.json":
        return "retain_exp047_legacy_source_overlay"
    if workflow_refs:
        return "retain_direct_workflow_execution_dependency"
    if "/checkpoints/" in path or "checkpoint" in Path(path).name.lower():
        return "retain_candidate_checkpoint_or_vector_pending_replay"
    if kind in ("source_code", "source_code_js", "configuration"):
        return "retain_runner_or_verifier_source_pending_run_lineage"
    if kind in ("structured_json", "structured_json_array", "tabular_csv"):
        return "retain_numeric_or_metadata_source_pending_run_lineage"
    if kind == "narrative_or_text" or markdown_refs or "README" in path:
        return "retain_historical_interpretation_and_provenance"
    if kind == "runtime_or_diagnostic_record":
        return "retain_diagnostic_until_restart_role_verified"
    return "retain_unknown_role_pending_semantic_review"


def build():
    assert git("rev-parse", BASE) == BASE
    changes = git("diff", "--name-only", BASE, "HEAD").splitlines()
    forbidden = [p for p in changes if p.startswith(ROOTS) or p.startswith((
        "data/constraints/", "data/parasitics/", "data/catalog/", "data/pareto_snapshots/",
        "candidates/"
    )) or p in ("data/bands.csv", "data/design_constraints.json")]
    assert not forbidden, "W4 follow-up must not change original evidence: " + repr(forbidden)
    assert not git("diff", "--diff-filter=D", "--name-only", BASE, "HEAD"), (
        "W4 follow-up must not delete files"
    )
    tracked = set(git("ls-files").splitlines())
    inventory, _ = create_inventory(root=ROOT, tracked=tracked)
    with (ROOT / "data/repository_reviews/step4_retention_46_20261017.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        protected = {row["path"] for row in csv.DictReader(stream)}
    assert len(protected) == 46
    candidates = sorted(
        [r for r in inventory if r["path"].startswith(ROOTS)
         and r["review_decision"] == "review_only_no_deletion"
         and r["path"] not in protected],
        key=lambda r: r["path"],
    )
    assert len(candidates) == 225, (
        "Source-only W4 snapshot changed; review diff rather than silently reclassifying",
        len(candidates)
    )
    texts = {}
    for rel in sorted(tracked):
        if Path(rel).suffix.lower() not in TEXT_EXTENSIONS or rel.startswith((
            "data/repository_reviews/", "data/repository_audits/"
        )) or rel in {
            "docs/phase2_cleanup_w4_forensics_20261017.md",
            "docs/phase2_w4_exp042_artifact_checkpoint_crosswalk_20261018.md",
            "scripts/review_phase2_w4_unindexed.py",
            "scripts/review_phase2_w4_action_runs.py",
            "scripts/audit_w4_exp042_missing_variants.py",
            "scripts/audit_w4_exp046_exp047_sources.py",
            "docs/phase2_w4_exp046_exp047_source_review_20261018.md",
            "scripts/verify_phase2_w5_closure.py",
            "docs/phase2_w5_readonly_closure_20261018.md",
            "docs/phase2_w4_exp042_missing_variant_recovery_20261018.md",
        }:
            continue
        body = _safe_read_text(ROOT / rel)
        if body is not None:
            texts[rel] = body
    links = resolved_markdown_references(texts, tracked)
    workflows = {p: text for p, text in texts.items()
                 if p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml"))}
    records = []
    for item in candidates:
        path = item["path"]
        kind, schema = _source_summary(path, ROOT / path)
        if Path(path).suffix.lower() == ".js":
            kind, schema = "source_code_js", "historical_javascript_analysis_source"
        exact = sorted(t for t, body in texts.items()
                       if t != path and path in body and _ref_hits(body, path))
        md = sorted(links.get(path, []))
        wf_exact = sorted(p for p, body in workflows.items() if path in body and _ref_hits(body, path))
        base = Path(path).name
        wf_basename = sorted(p for p, body in workflows.items()
                             if p not in wf_exact and base in body and _ref_hits(body, base))
        group = (path[len(ROOTS[0]):].split("/", 1)[0] if path.startswith(ROOTS[0])
                 else path[len(ROOTS[1]):].split("/", 1)[0])
        status = ("exact_source_path_found" if exact or md else
                  "basename_only_unverified" if wf_basename else
                  "no_static_path_hit_not_proof_unused")
        records.append({
            "path": path,
            "git_blob_sha1": item["git_blob_sha1"],
            "bytes": item["bytes"],
            "run_or_validation_group": group,
            "source_content_kind": kind,
            "source_schema_sample": schema[:130],
            "full_path_text_ref_count": len(exact),
            "full_path_text_ref_sources": ";".join(exact[:12]),
            "resolved_markdown_ref_count": len(md),
            "resolved_markdown_ref_sources": ";".join(md[:12]),
            "workflow_full_path_ref_sources": ";".join(wf_exact),
            "workflow_basename_mentions_unverified": ";".join(wf_basename),
            "static_ref_status": status,
            "evidence_role_gate": classify_gate(path, kind, wf_exact, md),
            "owner_approval": "not_granted",
            "delete_status": "retained_no_deletion_authorized",
        })
    groups = collections.defaultdict(list)
    for row in records:
        groups[row["run_or_validation_group"]].append(row)
    by_group = []
    for group, rows in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        by_group.append({
            "group": group, "file_count": len(rows),
            "bytes": sum(int(r["bytes"]) for r in rows),
            "with_exact_path_hits": sum(int(r["full_path_text_ref_count"]) > 0 or
                                        int(r["resolved_markdown_ref_count"]) > 0 for r in rows),
            "workflow_full_path_references": sum(bool(r["workflow_full_path_ref_sources"]) for r in rows),
            "without_static_path_hit": sum(
                r["static_ref_status"] == "no_static_path_hit_not_proof_unused"
                for r in rows),
            "owner_approval": "not_granted",
        })
    summary = {
        "scope": "W4 current tracked 225 unindexed experiment/validation sources",
        "based_on_main": BASE,
        "checked_out_commit": git("rev-parse", "HEAD"),
        "unindexed_count": len(records),
        "unindexed_bytes": sum(int(r["bytes"]) for r in records),
        "groups": len(groups),
        "by_content_kind": dict(sorted(collections.Counter(
            r["source_content_kind"] for r in records).items())),
        "by_evidence_role_gate": dict(sorted(collections.Counter(
            r["evidence_role_gate"] for r in records).items())),
        "with_exact_path_hits": sum(bool(int(r["full_path_text_ref_count"]) or
                                        int(r["resolved_markdown_ref_count"])) for r in records),
        "with_workflow_full_path_reference": sum(bool(
            r["workflow_full_path_ref_sources"]) for r in records),
        "with_workflow_basename_only_hint": sum(bool(
            r["workflow_basename_mentions_unverified"]) for r in records),
        "no_static_path_hit": sum(r["static_ref_status"] ==
                                  "no_static_path_hit_not_proof_unused"
                                  for r in records),
        "top_groups": by_group[:15],
        "approved_deletions": 0,
        "performed_deletions": 0,
        "new_rf_numeric_runs": 0,
        "limitations": [
            "Source path search is lexical, not semantic dependency proof.",
            "W4 follow-up self-generated documentation and scan scripts are excluded as reference sources.",
            "Dynamically built code paths, off-repository dependencies and unpublished runs are not indexed.",
            "No static path hit is not an assertion that a file is redundant.",
            "Original experiment file contents and 46 protected blobs are unchanged.",
        ],
    }
    return records, by_group, summary


def csv_text(rows, fields):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--emit-review-csv-chunks", action="store_true")
    args = parser.parse_args()
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    rows, groups, summary = build()
    content = csv_text(rows, FIELDS)
    (output / "w4_unindexed_225_review.csv").write_text(content, encoding="utf-8")
    (output / "w4_unindexed_groups.csv").write_text(
        csv_text(groups, ("group", "file_count", "bytes", "with_exact_path_hits",
                          "workflow_full_path_references", "without_static_path_hit",
                          "owner_approval")), encoding="utf-8"
    )
    (output / "w4_unindexed_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("W4_UNINDEXED_SUMMARY=" + json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    if args.emit_review_csv_chunks:
        for i in range(0, len(content), 5000):
            print("W4_UNINDEXED_CHUNK=" + json.dumps({
                "seq": i // 5000, "text": content[i:i + 5000]
            }, ensure_ascii=False, separators=(",", ":")))
    print("W4_UNINDEXED_PASS: all 225 original evidence sources retained, no deletion")


if __name__ == "__main__":
    main()
