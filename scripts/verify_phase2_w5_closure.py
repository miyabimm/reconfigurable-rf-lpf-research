#!/usr/bin/env python3
"""Phase 2 W5 non-destructive closure and retention completeness gate.

Checks exact historical Git evidence and current read-only source presence.
'Review completed' is not 'deletion authorized', nor an RF solver rerun.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "bda522d6e8dc3f5d4667c46507b7d1005c93b20e"
BEFORE_W3 = "88562135dae2edf8ba7763aa529181c05f7c1ded"
REVIEWS = ROOT / "data/repository_reviews"
sys.path.insert(0, str(ROOT / "scripts"))
from preserve_exp042_actions_artifacts import validate as validate_zip  # noqa: E402

GATE_FIELDS = ("gate_id","workstream","observation","evidence","status",
               "closure_meaning","deletion_approval","action_needed")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def read_rows(name):
    with (REVIEWS / name).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def checked_path(path, expected_sha=None, byte_count=None):
    p = ROOT / path
    assert p.is_file() and not p.is_symlink(), "source missing: " + path
    raw = p.read_bytes()
    if expected_sha:
        assert blob(raw) == expected_sha, "source Git blob changed: " + path
    if byte_count is not None:
        assert len(raw) == int(byte_count), "source size changed: " + path
    return raw


def add_gates():
    return [
      dict(gate_id="W0",workstream="baseline_and_review_candidates",
           observation="candidate ledger retained; historic text-cleanup states are dated, not current work assertions",
           evidence="data/repository_reviews/phase2_cleanup_deletion_candidates_20261017.csv",
           status="review_tracked_historical_ledger",
           closure_meaning="historical inventory traceability, not all T status items resolved",
           deletion_approval="not_granted_for_new_files",action_needed="reconcile T-001..010 against current docs in separate no-deletion task"),
      dict(gate_id="W1",workstream="current_document_links",
           observation="CI link-integrity check required; historical snapshots are time-scoped",
           evidence="scripts/verify_phase2_cleanup_w1_links.py",
           status="ci_gate_required",
           closure_meaning="link checking only, not stale semantic proof",
           deletion_approval="not_applicable",action_needed="keep CI link check green on each documentation PR"),
      dict(gate_id="W2",workstream="catalog_and_topology_index",
           observation="24 curated catalog entries; formal 4 and trial 6 non-dominated finite-grid record sets",
           evidence="data/catalog/phase2_candidate_catalog_20261017.csv;data/pareto_snapshots/rf_t005_rf_f003_20261017.json",
           status="curated_source_snapshot_verified",
           closure_meaning="source/catalog consistency only, not global optimality",
           deletion_approval="not_applicable",action_needed="derive missing historical topology only when source-confirmed"),
      dict(gate_id="W3_REMOVED",workstream="approved_document_retirement",
           observation="D-001..004 gone from current tree but recoverable at pinned pre-deletion Git revision",
           evidence="data/repository_reviews/w3_document_disposition_20261017.csv;docs/archive/w3_consolidated_documents_20261017.md",
           status="four_owner_approved_documents_retired",
           closure_meaning="approved secondary document deletion completed",
           deletion_approval="granted_only_D_001_to_004",action_needed="preserve original Git history and consolidation"),
      dict(gate_id="W3_HELD",workstream="historical_documents_retained",
           observation="D-005..007 present with unchanged original blob SHA",
           evidence="data/repository_reviews/w3_document_disposition_20261017.csv",
           status="three_historical_documents_retained",
           closure_meaning="not a pending automatic cleanup deletion",
           deletion_approval="not_granted",action_needed="maintain historically unique numeric and methodological records"),
      dict(gate_id="W4_OLD46",workstream="protected_historical_sources",
           observation="all 46 unchanged original Git blobs",
           evidence="data/repository_reviews/step4_retention_46_20261017.csv",
           status="sha_verified_keep",closure_meaning="retained rather than removed",
           deletion_approval="not_granted",action_needed="no deletion without individual owner approval"),
      dict(gate_id="W4_225",workstream="historical_unindexed_run_sources",
           observation="225 unchanged sources, 7 original evidence groups; source syntax is not numerical replay",
           evidence="data/repository_reviews/w4_unindexed_225_review_20261017.csv;data/repository_reviews/w4_replay_dependency_225_20261018.csv",
           status="sha_verified_keep",closure_meaning="baseline source presence, not deletion eligibility",
           deletion_approval="not_granted",action_needed="resolve dynamic run dependencies and numerical replay separately"),
      dict(gate_id="W4_131",workstream="exp046_exp047_originals",
           observation="EXP-046 35 trial sources and EXP-047 96 formal sources unchanged; corrected provenance distinguished",
           evidence="data/repository_reviews/w4_exp046_exp047_131_20261018.csv",
           status="sha_verified_keep",closure_meaning="original provenance evidence protected, no fresh MNA",
           deletion_approval="not_granted",action_needed="retain corrections and unknown execution environment"),
      dict(gate_id="W4_39WF",workstream="historical_workflow_inventory",
           observation="39 baseline workflows still tracked; dated REST execution counts are not proof of future non-use",
           evidence="data/repository_reviews/w4_workflow_runs_20261017.csv",
           status="historical_inventory_preserved",closure_meaning="does not prove any workflow may be retired",
           deletion_approval="not_granted",action_needed="assess manual dispatch/branch pinning and dynamic paths before removal"),
      dict(gate_id="W4_ORIGINAL_ARTIFACTS",workstream="exp042_original_artifacts",
           observation="10 original Actions ZIPs, 19 member files remain offline restorable via verified SHA256/CRC",
           evidence="data/repository_reviews/w4_exp042_actions_original_zip_b64_20261018.json",
           status="original_zip_bytes_preserved",closure_meaning="byte recovery, not recomputed RF or independent MNA",
           deletion_approval="not_granted",action_needed="retain original run metadata and local Git ZIP archive"),
      dict(gate_id="W4_RESTORED_SIX",workstream="exp042_uncurated_variant_restoration",
           observation="6 original JSON member bytes for 3 variants, source SHA and run IDs retained",
           evidence="data/repository_reviews/w4_exp042_missing_variant_source_review_20261018.json",
           status="source_bytes_verified_keep",closure_meaning="no curated checkpoint promotion or new Pareto points",
           deletion_approval="not_granted",action_needed="keep original six with historic RF-T005 scope"),
      dict(gate_id="W4_APPROVAL",workstream="experiment_and_workflow_retirement",
           observation="E-001,E-002,W-001,W-OTHER have no owner approval; no physical removals in W4",
           evidence="data/repository_reviews/w4_cleanup_decision_gates_20261017.csv",
           status="not_authorized_unfinished",closure_meaning="W4 source deletion and workflow retirement incomplete",
           deletion_approval="not_granted",action_needed="do not delete without per-item approval and replay/use analysis"),
      dict(gate_id="RF_RESEARCH",workstream="rf_f003_and_rf_t005_numerical_design",
           observation="formal RF-F003 and trial RF-T005 separated; archive finite grids do not prove continuum/physical performance",
           evidence="data/constraints/registry.json;data/pareto_snapshots/rf_t005_rf_f003_20261017.json",
           status="phase2_research_open",closure_meaning="no shared RF-F003 replay pipeline/physical proof confirmed here",
           deletion_approval="not_applicable",action_needed="independent common-grid MNA, Q(f)/SRF/EM, tolerance and RF-F003 pipeline"),
      dict(gate_id="W5",workstream="read_only_cleanup_closure",
           observation="W0-W4 evidence / decision gates rechecked without changing study originals",
           evidence="scripts/verify_phase2_w5_closure.py;docs/phase2_w5_readonly_closure_20261018.md",
           status="read_only_audit_only",closure_meaning="not permission to delete W4 files or start Phase 3",
           deletion_approval="not_granted",action_needed="owner review of outstanding W4 and research actions"),
    ]


def assess():
    assert git("rev-parse", BASE) == BASE
    assert not git("diff", "--diff-filter=D", "--name-only", BASE, "HEAD"), "W5 PR must not delete anything"
    changes = git("diff", "--name-only", BASE, "HEAD").splitlines()
    forbidden = ("experiments/", "candidates/", "data/constraints/", "data/parasitics/",
                 "data/validation/", "data/catalog/", "data/pareto_snapshots/")
    assert not any(p.startswith(forbidden) or p in ("data/bands.csv","data/design_constraints.json") for p in changes)
    historic_d = read_rows("w3_document_disposition_20261017.csv")
    assert len(historic_d) == 7
    deleted = []
    kept = []
    for d in historic_d:
        source = d["source_path"]
        if d["candidate_id"] in ("D-001","D-002","D-003","D-004"):
            assert not (ROOT / source).exists()
            assert d["owner_delete_approval"].startswith("granted_")
            assert d["tree_state"] == "removed_from_current_revision"
            assert git("rev-parse", BEFORE_W3 + ":" + source) == d["git_blob_sha1"]
            deleted.append(d["candidate_id"])
        else:
            assert d["owner_delete_approval"] == "not_granted"
            checked_path(source, d["git_blob_sha1"])
            kept.append(d["candidate_id"])
    assert deleted == ["D-001","D-002","D-003","D-004"]
    assert kept == ["D-005","D-006","D-007"]
    consolidation = checked_path("docs/archive/w3_consolidated_documents_20261017.md").decode("utf-8")
    assert all(k in consolidation for k in deleted)
    approvals = read_rows("phase2_cleanup_deletion_candidates_20261017.csv")
    assert len(approvals) == 23
    assert [x["candidate_id"] for x in approvals if x["workstream"] == "text_cleanup"] == [
        "T-"+str(i).zfill(3) for i in range(1,11)
    ]
    assert all(x["execution_state"] == "not_started_unapproved"
               for x in approvals if x["workstream"] == "text_cleanup"), "historic T statuses changed unexpectedly"
    assert sum(x["execution_state"].startswith("removed_after_owner_approval") for x in approvals) == 4
    protected = read_rows("step4_retention_46_20261017.csv")
    assert len(protected) == 46
    for x in protected:
        checked_path(x["path"],x["git_blob_sha1"],x["bytes"])
        assert x["owner_approval_to_remove"] == "not_granted" and x["moved_or_deleted"] == "false"
    baseline = read_rows("w4_unindexed_225_review_20261017.csv")
    replay = read_rows("w4_replay_dependency_225_20261018.csv")
    assert len(baseline) == len(replay) == 225
    assert {x["path"] for x in baseline} == {x["source_path"] for x in replay}
    replay_by_path = {x["source_path"]:x for x in replay}
    for x in baseline:
        checked_path(x["path"],x["git_blob_sha1"],x["bytes"])
        assert replay_by_path[x["path"]]["git_blob_sha1"] == x["git_blob_sha1"]
        assert x["owner_approval"] == "not_granted"
        assert x["delete_status"] == "retained_no_deletion_authorized"
    exp_review = read_rows("w4_exp046_exp047_131_20261018.csv")
    assert len(exp_review) == 131
    assert collections.Counter(x["group"] for x in exp_review) == {"EXP-046":35,"EXP-047":96}
    assert all(x["path"] in replay_by_path and
               x["git_blob_sha1"] == replay_by_path[x["path"]]["git_blob_sha1"]
               for x in exp_review)
    wf = read_rows("w4_workflow_runs_20261017.csv")
    assert len(wf) == 39
    assert len({x["workflow_path"] for x in wf}) == 39
    for x in wf:
        assert x["owner_delete_approval"] == "not_granted"
        assert x["deletion_executed"] == "false"
        checked_path(x["workflow_path"])
    current_wf = [p for p in git("ls-files", ".github/workflows").splitlines()
                  if p.endswith((".yml",".yaml")) and (ROOT/p).is_file()]
    assert len(current_wf) >= 39
    w4_gates = read_rows("w4_cleanup_decision_gates_20261017.csv")
    assert {x["candidate_id"] for x in w4_gates} == {"E-001","E-002","W-001","W-OTHER"}
    assert all(x["owner_remove_approval"]=="not_granted" and x["deleted_in_w4"]=="false" for x in w4_gates)

    archive=json.loads(checked_path("data/repository_reviews/w4_exp042_actions_original_zip_b64_20261018.json"))
    validate_zip(archive)
    assert archive["artifact_count"] == 10 and archive["zip_members_count"] == 19
    restored=json.loads(checked_path("data/repository_reviews/w4_exp042_missing_variant_source_review_20261018.json"))
    assert restored["recovered_original_member_count"] == 6
    assert restored["recorded_variants"] == 3
    for x in restored["records"]:
        assert x["source_constraint_scope"].startswith("RF-T005")
        import hashlib
        for k in ("main","independent"):
            raw=checked_path(x["recovered_"+k+"_repo_path"])
            assert hashlib.sha256(raw).hexdigest() == x[k+"_json_sha256"]
        assert not (ROOT/x["curated_checkpoint_path_absent"]).exists()
        assert x["two_axis_source_screening"]["observation"] == "not_better_than_existing_same_area_observed_candidate"
    original_131=json.loads(checked_path("data/repository_reviews/w4_exp046_exp047_summary_20261018.json"))
    assert original_131["source_total"]==131
    assert original_131["original_experiment_deletions"]==0
    assert original_131["new_independent_MNA_runs"]==0
    assert original_131["exp047"]["registered_formal_pareto_candidate_count"]==4
    assert original_131["exp047"]["actions_search_executed"] is False
    reg = json.loads(checked_path("data/constraints/registry.json"))
    assert reg["active_formal_id"]=="RF-F003" if "active_formal_id" in reg else reg.get("active_formal_constraint_id") == "RF-F003"
    pareto=json.loads(checked_path("data/pareto_snapshots/rf_t005_rf_f003_20261017.json"))
    cond={x["constraint_id"]:x for x in pareto["conditions"]}
    assert set(cond)=={"RF-F003","RF-T005"}
    assert len(cond["RF-F003"]["candidates"])==4
    assert len(cond["RF-T005"]["candidates"])==6
    cat=read_rows_catalog()
    assert len(cat)==24
    assert sum(x["constraint_id"]=="RF-F003" for x in cat)==4
    assert sum(x["constraint_id"]=="RF-T005" for x in cat)==6
    summary={
        "schema_version":1,
        "purpose":"W5 Phase 2 non-destructive repository cleanup closure audit",
        "baseline_main": BASE,
        "executed_head":git("rev-parse","HEAD"),
        "w3_retired_documents":deleted,
        "w3_retained_documents":kept,
        "historical_text_cleanup_ledger_rows_not_proof_of_current_state":10,
        "protected_originals_SHA_verified":len(protected),
        "w4_historical_225_originals_SHA_verified":len(baseline),
        "w4_exp046_exp047_originals_with_matching_225_SHA":len(exp_review),
        "baseline_workflows_still_tracked":len(wf),
        "current_tracked_yaml_workflows":len(current_wf),
        "baseline_workflows_api_counts_are_dated":True,
        "w4_decision_scopes_unapproved":sorted(x["candidate_id"] for x in w4_gates),
        "exp042_original_zip_count":archive["artifact_count"],
        "exp042_archive_member_count":archive["zip_members_count"],
        "exp042_original_members_recovered_and_SHA_verified":restored["recovered_original_member_count"],
        "formal_RFF003_pareto_candidates":len(cond["RF-F003"]["candidates"]),
        "trial_RFT005_pareto_candidates":len(cond["RF-T005"]["candidates"]),
        "unified_catalog_historical_and_current_rows":len(cat),
        "owner_new_experiment_delete_approvals":0,
        "new_file_deletions":0,
        "rf_optimizer_executions":0,
        "independent_MNA_new_executions":0,
        "phase":"Phase 2",
        "phase3_authorized":False,
        "W5_read_only_closure_eligible":True,
        "W4_source_and_workflow_deletion_closed":False,
        "unresolved":[
            "Historic T-001..T-010 W0 ledger not reconciled to current tree: do not equate dated not_started flags to present outstanding edits.",
            "W4 experiment and workflow deletion requires per-item owner consent and verified dependency/resume impact.",
            "EXP-046/047 in-chat Code Mode execution commit, seed, environment and external source dependencies not reconstructed.",
            "Formal RF-F003 common-runner independent matched-grid numerical replay not performed by W5.",
            "Continuous extrema, SRF, Q(f), EM, manufacturer S parameters, simultaneous k, thermal/tolerance and measurement outstanding.",
        ],
    }
    return summary,add_gates()


def read_rows_catalog():
    path=ROOT/"data/catalog/phase2_candidate_catalog_20261017.csv"
    with path.open(newline="",encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output-dir",type=Path,required=True)
    ap.add_argument("--emit-chunks",action="store_true")
    args=ap.parse_args()
    summary,gates=assess()
    out=args.output_dir
    out.mkdir(parents=True,exist_ok=True)
    content=json.dumps(summary,ensure_ascii=False,indent=2)+"\n"
    (out/"w5_readonly_closure_summary.json").write_text(content,encoding="utf-8")
    buf=io.StringIO()
    writer=csv.DictWriter(buf,fieldnames=GATE_FIELDS,lineterminator="\n")
    writer.writeheader()
    writer.writerows(gates)
    lines=buf.getvalue()
    (out/"w5_readonly_gate_matrix.csv").write_text(lines,encoding="utf-8")
    print("W5_SUMMARY="+json.dumps(summary,ensure_ascii=False,separators=(",",":")))
    print("W5_MATRIX_ROWS="+str(len(gates)))
    if args.emit_chunks:
        for name,data in (("summary",content),("gates",lines)):
            for k in range(0,len(data),5000):
                print("W5_SNAPSHOT_CHUNK="+json.dumps({
                    "name":name,"seq":k//5000,"text":data[k:k+5000]
                },ensure_ascii=False,separators=(",",":")))
    print("W5_READ_ONLY_PASS: Git SHA and source/approval gates checked; no deletion or RF replay")


if __name__=="__main__":
    main()
