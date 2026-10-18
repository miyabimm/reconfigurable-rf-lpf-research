#!/usr/bin/env python3
"""Post-W5 Phase 2 read-only reconciliation: T-001..010, 46 workflows, 225 sources.

The dated W0/W4/W5 files are immutable observations and are never rewritten.
No original source, workflow or candidate files are deleted or changed.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import io
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "486a2761661cbd3da16be97041568e50b9547f00"
OUT = ROOT / "data/repository_reviews"
T_FIELDS = ("candidate_id","original_path","historical_ledger_state","baseline_original_blob_sha1",
            "main_at_W5_blob_sha1","baseline_changed_since_planning","current_evidence_test",
            "latest_review_disposition","outstanding","owner_permission_needed","original_history_preserved")
WF_FIELDS = ("workflow_path","original_20171017_workflow","api_registered_on_20171017",
             "api_visible_run_count_then","manual_dispatch_in_current_source",
             "write_or_mutating_operation_lexical","branch_or_provenance_pinning_lexical",
             "artifact_upload_or_download_lexical","role_and_retirement_gate",
             "current_source_sha1","decision","replay_verified","owner_delete_approval")
E_FIELDS = ("path","source_sha1","bytes","group","source_kind","baseline_static_ref_status",
            "known_whole_path_reference","manifest_path_hit","workflow_path_hit",
            "dynamic_path_usage_hint","fixed_s2p_dependency_hint","original_zip_or_checkpoint_role",
            "correction_provenance_if_known","decision","deletion_consent","replay_proven")


def git(*args):
    return subprocess.check_output(["git",*args],cwd=ROOT,text=True).strip()


def git_blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()


def records(path):
    with (ROOT/path).open(newline="",encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def get(path):
    return (ROOT/path).read_text(encoding="utf-8")


def text_reconciliation():
    old = records("data/repository_reviews/phase2_cleanup_deletion_candidates_20261017.csv")
    source={r["candidate_id"]:r for r in old if r["candidate_id"].startswith("T-")}
    assert len(source)==10
    checks = [
      ("T-001", ["RF-F003", "RF-T005", "Phase 2"], "current_entry_updated_keep_dated_history", "none"),
      ("T-002", ["RF-F003", "W5", "W4"], "current_roadmap_updated_dated_legacy_sections_retained", "none"),
      ("T-003", ["RF-F003", "RF-T005", "EXP-047"], "current_open_issue_correctly_labels_unknown", "none"),
      ("T-004", ["24候補", "RF-F003", "RF-T005"], "integrated_results_entry_present", "none"),
      ("T-005", ["24件", "RF-F003", "RF-T005"], "integrated_data_entry_present", "none"),
      ("T-006", ["24候補", "--catalog", "RF-F003"], "conditional_24_catalog_reporter_documented", "none"),
      ("T-007", ["EXP-047", "索引専用アダプター", "manifest"], "strict_vs_legacy_manifest_explained", "none"),
      ("T-008", ["lpf-target040.yml", "actions/workflows/"], "github_actions_route_not_local_repo_artifact", "none"),
      ("T-009", ["PR #71", "マージ済み", "当時"], "historical_plan_has_dated_postmerge_addendum", "dated_non_current_PR72_Draft_wording_keep_historical"),
      ("T-010", ["PR #71", "マージ済み", "マージ前"], "historical_validation_has_dated_merge_context", "keep_old_snapshot_test_run_separate_from_current"),
    ]
    results=[]
    for id, phrases, status, outstanding in checks:
        item=source[id];path=item["source_path_or_scope"]
        actual=get(path)
        assert all(x in actual for x in phrases), (id,phrases)
        sha=git("rev-parse",BASE+":"+path)
        assert sha==git_blob(git("show",BASE+":"+path).encode("utf-8"))
        if id=="T-008":
            assert (ROOT/".github/workflows/lpf-target040.yml").is_file()
            assert "../../../../actions/workflows/lpf-target040.yml" in actual
            assert "../../../../.github/workflows/lpf-target040.yml" in actual
        assert item["execution_state"]=="not_started_unapproved"
        results.append({
            "candidate_id":id,"original_path":path,"historical_ledger_state":item["execution_state"],
            "baseline_original_blob_sha1":item["source_git_blob_sha1_at_planning"],
            "main_at_W5_blob_sha1":sha,
            "baseline_changed_since_planning":str(sha!=item["source_git_blob_sha1_at_planning"]).lower(),
            "current_evidence_test":";".join(phrases),
            "latest_review_disposition":status,
            "outstanding":outstanding,
            "owner_permission_needed":"none_for_read_only_text_reconciliation",
            "original_history_preserved":"true",
        })
    assert len(results)==10 and sum(r["baseline_changed_since_planning"]=="true" for r in results)==9
    return results


def workflow_review():
    archived=records("data/repository_reviews/w4_workflow_runs_20261017.csv")
    by_path={x["workflow_path"]:x for x in archived}
    assert len(by_path)==39
    current=[p for p in git("ls-files",".github/workflows").splitlines()
             if p.endswith((".yml",".yaml")) and (ROOT/p).is_file()]
    assert len(current)==46, len(current)
    rows=[]
    for p in sorted(current):
        src=get(p)
        prior=by_path.get(p)
        words = {
          "write_mutation": bool(re.search(
                r"contents\s*:\s*write|pull-requests\s*:\s*write|"
                r"git\s+push|create-pull-request|gh\s+pr\s+create|gh\s+api\s+.*(?:POST|PATCH|DELETE)",
                src,flags=re.I)),
          "branch_pin":bool(re.search(
                r"ref\s*:\s*(?:[\"']?refs/heads/|[\"']?(?:main|master|[a-f0-9]{40})\b)|"
                r"(?:[a-f0-9]{40})|github\.head_ref|github\.event\.pull_request\.head",
                src,flags=re.I)),
          "artifacts":bool(re.search(
                r"upload-artifact|download-artifact|actions/download-artifact|actions/upload-artifact|"
                r"artifact-id|run_id|resume_run_id",src,flags=re.I)),
          "manual": "workflow_dispatch:" in src,
        }
        if p.endswith("reserve_experiment_number.yml"):
            role="mandatory_experiment_id_reservation"
        elif p.endswith("/audit.yml"):
            role="core_phase2_regression"
        elif "/phase2_" in p:
            role="existing_phase2_audit_or_protection_gate"
        elif "/exp042" in p or "/exp043" in p or "/exp044" in p:
            role="historic_experiment_replay_and_provenance"
        else:
            role="historic_experiment_or_runner_manual_replay"
        # Zero recorded runs is NOT proof the source is unused.
        rows.append({
            "workflow_path":p,
            "original_20171017_workflow":str(prior is not None).lower(),
            "api_registered_on_20171017":prior["api_registration_state"] if prior else "not_in_old_API_snapshot",
            "api_visible_run_count_then":prior["api_visible_run_count"] if prior else "not_observed_in_20171017_snapshot",
            "manual_dispatch_in_current_source":str(words["manual"]).lower(),
            "write_or_mutating_operation_lexical":str(words["write_mutation"]).lower(),
            "branch_or_provenance_pinning_lexical":str(words["branch_pin"]).lower(),
            "artifact_upload_or_download_lexical":str(words["artifacts"]).lower(),
            "role_and_retirement_gate":role,
            "current_source_sha1":git_blob((ROOT/p).read_bytes()),
            "decision":"retain_no_workflow_retirement_approved",
            "replay_verified":"false",
            "owner_delete_approval":"not_granted",
        })
    assert sum(x["original_20171017_workflow"]=="true" for x in rows)==39
    assert all(x["decision"]=="retain_no_workflow_retirement_approved" for x in rows)
    return rows


def evidence_review():
    base=records("data/repository_reviews/w4_unindexed_225_review_20261017.csv")
    replay=records("data/repository_reviews/w4_replay_dependency_225_20261018.csv")
    exp=records("data/repository_reviews/w4_exp046_exp047_131_20261018.csv")
    by_replay={x["source_path"]:x for x in replay}
    by_exp={x["path"]:x for x in exp}
    assert len(base)==225 and len(by_replay)==225 and len(by_exp)==131
    out=[]
    for x in base:
        p=x["path"]; r=by_replay[p]; f=ROOT/p
        assert f.is_file() and git_blob(f.read_bytes())==x["git_blob_sha1"]
        assert git_blob(f.read_bytes())==r["git_blob_sha1"]
        correction=by_exp[p]["correction_class"] if p in by_exp else "no_individually_verified_correction_class"
        out.append({
            "path":p,"source_sha1":x["git_blob_sha1"],"bytes":x["bytes"],
            "group":x["run_or_validation_group"],"source_kind":r["source_kind"],
            "baseline_static_ref_status":x["static_ref_status"],
            "known_whole_path_reference":str(int(x["full_path_text_ref_count"])>0).lower(),
            "manifest_path_hit":r["manifest_full_path_literal"],
            "workflow_path_hit":str(bool(r["workflow_exact_path_reference"])).lower(),
            "dynamic_path_usage_hint":r["source_mentions_dynamic_path_construct"],
            "fixed_s2p_dependency_hint":r["source_mentions_external_s2p"],
            "original_zip_or_checkpoint_role":"retain_original_run_source_provenance",
            "correction_provenance_if_known":correction,
            "decision":"retain_pending_per_item_replay_or_dependency_closure",
            "deletion_consent":"not_granted",
            "replay_proven":"false",
        })
    assert len(out)==225 and all(x["deletion_consent"]=="not_granted" for x in out)
    return out


def assert_no_original_mutation():
    assert git("rev-parse",BASE)==BASE
    assert not git("diff","--diff-filter=D","--name-only",BASE,"HEAD")
    changes=git("diff","--name-only",BASE,"HEAD").splitlines()
    original_dirs=("experiments/","candidates/","data/validation/","data/constraints/",
                   "data/parasitics/","data/pareto_snapshots/","data/catalog/",
                   ".github/workflows/")
    assert not any(
        (p.startswith(original_dirs) and
         p != ".github/workflows/phase2_w5_post_cleanup_disposition.yml") or
        p in ("data/design_constraints.json","data/bands.csv")
        for p in changes), changes
    for r in records("data/repository_reviews/step4_retention_46_20261017.csv"):
        assert git_blob((ROOT/r["path"]).read_bytes())==r["git_blob_sha1"]


def write_csv(rows,fields,path):
    buf=io.StringIO()
    w=csv.DictWriter(buf,fieldnames=fields,lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    path.write_text(buf.getvalue(),encoding="utf-8")
    return buf.getvalue()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--emit-chunks",action="store_true")
    args=parser.parse_args()
    assert_no_original_mutation()
    t=text_reconciliation()
    wf=workflow_review()
    e=evidence_review()
    s={
        "schema":1,"scope":"read-only post-W5 Phase 2 completion workstreams",
        "baseline_main":BASE,"checked_out_head":git("rev-parse","HEAD"),
        "historical_T_candidates_reconciled":len(t),
        "historical_T_unstarted_labels_preserved_as_dated_evidence":len(t),
        "original_T_source_changed_from_planning":sum(r["baseline_changed_since_planning"]=="true" for r in t),
        "T_require_new_content_changes":0,
        "T_special_GitHub_Actions_route_count":1,
        "workflow_current_total":len(wf),
        "workflow_legacy_20171017_total":sum(r["original_20171017_workflow"]=="true" for r in wf),
        "workflow_new_since_w4_snapshot":sum(r["original_20171017_workflow"]=="false" for r in wf),
        "workflow_manual_dispatch":sum(r["manual_dispatch_in_current_source"]=="true" for r in wf),
        "workflow_write_mutating_lexical_hints":sum(r["write_or_mutating_operation_lexical"]=="true" for r in wf),
        "workflow_artifact_replay_hints":sum(r["artifact_upload_or_download_lexical"]=="true" for r in wf),
        "workflow_approved_for_removal":0,
        "evidence_225_reviewed":len(e),
        "evidence_EXP046_EXP047_subset":sum(r["path"].startswith((
            "experiments/chatgpt_topology_search/runs/EXP-046/",
            "experiments/chatgpt_topology_search/runs/EXP-047/")) for r in e),
        "evidence_requires_retention":len(e),
        "protected_46_unchanged":46,
        "experiment_approvals_to_delete":0,
        "source_deletions":0,"workflow_deletions":0,
        "new_rf_recomputations":0,"phase":"Phase 2","phase3_started":False,
        "followup":[
            "Historic T ledger deliberately retained unchanged; this overlay is dated, not a rewrite of old evidence.",
            "All workflows require owner approval if future retirement is considered; lexical flags are triage hints, not dynamic execution proof.",
            "225 selected original sources are retained; the larger 747 source set was inventoried in W4, and this overlay does not pretend to replay 747 jobs.",
            "Current live API run history and actual workflow dispatch side effects are not exhaustively re-read here.",
            "EXP-046/047 Code Mode replay and RF-F003 independent circuit and physical reanalysis remain separate Phase 2 research issues.",
        ],
    }
    args.output_dir.mkdir(parents=True,exist_ok=True)
    outputs={
        "text":write_csv(t,T_FIELDS,args.output_dir/"w5_T001_T010_status.csv"),
        "workflows":write_csv(wf,WF_FIELDS,args.output_dir/"w5_workflow_46_decisions.csv"),
        "evidence":write_csv(e,E_FIELDS,args.output_dir/"w5_evidence_225_decisions.csv"),
        "summary":json.dumps(s,indent=2,ensure_ascii=False)+"\n"
    }
    (args.output_dir/"w5_followup_summary.json").write_text(outputs["summary"],encoding="utf-8")
    print("W5_FOLLOWUP_SUMMARY="+json.dumps(s,ensure_ascii=False,separators=(",",":")))
    if args.emit_chunks:
        for name,value in outputs.items():
            for offset in range(0,len(value),5200):
                print("W5_FOLLOWUP_CHUNK="+json.dumps({
                    "type":name,"seq":offset//5200,"content":value[offset:offset+5200]
                },ensure_ascii=False,separators=(",",":")))
    print("W5_POST_AUDIT_PASS: 10 text candidates, 46 workflows, 225 originals, 0 deletion")


if __name__=="__main__":
    main()
