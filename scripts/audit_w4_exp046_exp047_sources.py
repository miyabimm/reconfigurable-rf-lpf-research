#!/usr/bin/env python3
"""W4 Phase 2: provenance audit of original EXP-046 and EXP-047 evidence.

Checks original Git blob identities, correction vs historical flags and catalog
provenance, but deliberately does not run RF optimizers/MNA or delete evidence.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import io
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "abde1a1df3c768c479abcfd5941741a82b8c6483"
SOURCE = ROOT / "data/repository_reviews/w4_unindexed_225_review_20261017.csv"
PROTECTED = ROOT / "data/repository_reviews/step4_retention_46_20261017.csv"
CATALOG = ROOT / "data/catalog/phase2_candidate_catalog_20261017.csv"
PARETO = ROOT / "data/pareto_snapshots/rf_t005_rf_f003_20261017.json"
RUNS = ROOT / "experiments/chatgpt_topology_search/runs"
FIELDS = (
    "path","group","git_blob_sha1","bytes","kind","manifest_constraint",
    "source_original_git_blob_verified","purpose_from_source","correction_class",
    "performance_ranking_eligibility","referenced_by_historical_manifest",
    "referenced_by_current_candidate_catalog","referenced_by_saved_pareto",
    "source_runner_replay_status","owner_deletion_approval","retention",
)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def assess():
    assert git("rev-parse", BASE) == BASE
    assert not git("diff", "--diff-filter=D", "--name-only", BASE, "HEAD")
    touched = git("diff", "--name-only", BASE, "HEAD").splitlines()
    assert not any(x.startswith(("experiments/", "candidates/", "data/constraints/",
                                 "data/parasitics/", "data/catalog/",
                                 "data/pareto_snapshots/", "data/validation/"))
                   or x in ("data/bands.csv", "data/design_constraints.json")
                   for x in touched), "W4 audit must not change source evidence"
    items = [x for x in read_csv(SOURCE)
             if x["path"].startswith((
                 "experiments/chatgpt_topology_search/runs/EXP-046/",
                 "experiments/chatgpt_topology_search/runs/EXP-047/"
             ))]
    assert len(items) == 131, len(items)
    assert collections.Counter(x["run_or_validation_group"] for x in items) == {
        "EXP-046": 35, "EXP-047": 96
    }
    protected = {x["path"]:x["git_blob_sha1"] for x in read_csv(PROTECTED)}
    assert len(protected) == 46
    assert not any(x["path"] in protected for x in items)
    assert all(blob((ROOT / p).read_bytes()) == sha for p,sha in protected.items())
    exp46 = json.loads((RUNS / "EXP-046/manifest.json").read_text())
    exp47 = json.loads((RUNS / "EXP-047/manifest.json").read_text())
    assert exp46["constraints"]["constraint_id"] == "RF-T005"
    assert exp46["code"]["working_tree_dirty"] is True
    assert exp46["random_seed"] is None and exp46["environment"] is None
    assert exp47["constraint_id"] == "RF-F003"
    assert exp47["execution"]["github_actions_search_executed"] is False
    adapter = json.loads((ROOT / "data/validation/exp047_legacy_manifest_adapter_20261017.json").read_text())
    assert adapter["source_manifest_git_blob_sha1"] == blob((RUNS / "EXP-047/manifest.json").read_bytes())
    assert set(adapter["unknown_not_inferred"]) >= {
        "original_optimizer_git_commit","original_random_seed",
        "original_environment","original_worktree_cleanliness"
    }
    q_wrong = set(exp47["execution"]["q_bug_excluded_files"])
    assert len(q_wrong) == 5
    source47 = set(exp47["execution"]["sources"])
    assert len(source47) == 5
    assert all((RUNS / "EXP-047" / x).is_file() for x in q_wrong | source47)
    source46 = {Path(x).name for x in exp46["search_scope"]["source_files"]}
    assert len(source46) == 4
    assert all((RUNS / "EXP-046" / x).is_file() for x in source46)
    cat = read_csv(CATALOG)
    formal = [x for x in cat if x["experiment_id"] == "EXP-047" and
              x["constraint_id"] == "RF-F003"]
    assert len(formal) == 4
    assert not any(x["experiment_id"] == "EXP-046" for x in cat)
    assert all(x["checkpoint_path"] == x["verification_path"] for x in formal)
    assert all(x["experiment_execution_status"] == "partial" for x in formal)
    assert all(x["solver_convergence_status"] == "not_stated_in_snapshot" for x in formal)
    para = json.loads(PARETO.read_text())
    formal_pareto = next(x["candidates"] for x in para["conditions"]
                         if x["constraint_id"] == "RF-F003")
    assert len(formal_pareto) == 4
    assert {x["source"]["complete_parameter_vector"]["path"] for x in formal_pareto} == {
        x["checkpoint_path"] for x in formal
    }
    registered = {x["checkpoint_path"]:x for x in formal}
    for x in formal_pareto:
        path = x["source"]["complete_parameter_vector"]["path"]
        orig = ROOT / path
        assert blob(orig.read_bytes()) == x["source"]["complete_parameter_vector"]["blob_sha"]
        assert blob(orig.read_bytes()) == registered[path]["checkpoint_git_blob_sha1"]
        assert x["verification"]["independent_coupled_L_MNA_probe_points"] == 84
        assert x["verification"]["points_per_interval"] == 1001

    verified_src = {Path(x["reference"]).name for x in exp47["validated_candidates"]}
    assert all((RUNS / "EXP-047" / p).is_file() for p in verified_src)
    result46 = Path(exp46["search_scope"]["result_record"]).name
    assert (RUNS / "EXP-046" / result46).is_file()

    rows = []
    for x in sorted(items, key=lambda t:t["path"]):
        path=x["path"]
        original=ROOT / path
        raw=original.read_bytes()
        assert blob(raw) == x["git_blob_sha1"] and len(raw) == int(x["bytes"])
        assert git("rev-parse", BASE+":"+path) == x["git_blob_sha1"]
        group=x["run_or_validation_group"]
        name=original.name
        suffix=original.suffix.lower()
        if suffix==".js":
            purpose="archived_in_chat_source_code"
        elif name == "README.md":
            purpose="chronological_source_interpretation"
        elif suffix == ".json":
            purpose="archived_numeric_or_diagnostic_data"
        else:
            purpose="original_other_source"
        is46=group=="EXP-046"
        manifest=exp46 if is46 else exp47
        if is46:
            if name=="independent_verified_1001.json":
                correction="superseded_capacitor_power_accounting_only"
                eligibility="exclude_power_diagnostic_use_corrected"
            elif name=="independent_verified_1001_corrected.json":
                correction="corrected_capacitor_power_accounting"
                eligibility="source_report_eligible_if_other_gates_satisfied"
            else:
                correction="not_a_correction_source"
                eligibility="screening_only_not_catalog_promoted"
        else:
            if name in q_wrong:
                correction="Q_index_bug_pre_correction_historial_exclusion"
                eligibility="exclude_from_RF_F003_compliant_performance"
            elif name.startswith(("round2_corrected_cf1_Q80","round3_corrected_Q80","round4_corrected_Q80")) or "4GJM" in name or name.startswith(("area4p667","area5p333")):
                correction="post_or_alternative_Q80_source_needs_scoped_review"
                eligibility="eligible_only_if_registered_and_independently_attested"
            else:
                correction="no_specific_Q_bug_waiver"
                eligibility="requires_source_specific_validation"
        listed = path in registered or any(path==c["verification_path"] for c in formal)
        selected_pareto=any(path==c["source"]["complete_parameter_vector"]["path"]
                            for c in formal_pareto)
        referenced=(name in q_wrong or name in source47 or name in verified_src) if not is46 else (
            name in source46 or name==result46
        )
        rows.append({
            "path":path,
            "group":group,
            "git_blob_sha1":x["git_blob_sha1"],
            "bytes":x["bytes"],
            "kind":purpose,
            "manifest_constraint": "RF-T005" if is46 else "RF-F003",
            "source_original_git_blob_verified":"true",
            "purpose_from_source":purpose,
            "correction_class":correction,
            "performance_ranking_eligibility":eligibility,
            "referenced_by_historical_manifest":str(referenced).lower(),
            "referenced_by_current_candidate_catalog":str(listed).lower(),
            "referenced_by_saved_pareto":str(selected_pareto).lower(),
            "source_runner_replay_status":"not_replayed_or_independently_verified_in_W4",
            "owner_deletion_approval":"not_granted",
            "retention":"retain_provenance_or_reproducibility_source",
        })

    summary={
        "kind":"Phase 2 W4 EXP-046/047 immutable original source audit",
        "baseline_main":BASE,
        "checkout":git("rev-parse","HEAD"),
        "source_total":len(rows),
        "by_experiment":dict(sorted(collections.Counter(r["group"] for r in rows).items())),
        "by_kind":dict(sorted(collections.Counter(r["kind"] for r in rows).items())),
        "verified_original_blob_count":len(rows),
        "protected_other_46_sha_match":len(protected),
        "exp046": {
            "constraint_id":"RF-T005",
            "archive_sha": exp46["code"]["execution_sha"],
            "archive_sha_is_verified_execution_sha":False,
            "source_worktree_dirty":exp46["code"]["working_tree_dirty"],
            "original_seed":exp46["random_seed"],
            "original_environment":exp46["environment"],
            "corrected_power_accounting_source":"independent_verified_1001_corrected.json",
            "superseded_power_diagnostic_source":"independent_verified_1001.json",
            "numerical_result_replayed":False,
            "new_candidate_promotion":0,
        },
        "exp047": {
            "constraint_id":"RF-F003",
            "original_manifest_blob_sha1":adapter["source_manifest_git_blob_sha1"],
            "index_adapter_is_strict_replay_manifest":False,
            "original_optimizer_commit":adapter["unknown_not_inferred"]["original_optimizer_git_commit"],
            "original_random_seed":adapter["unknown_not_inferred"]["original_random_seed"],
            "original_environment":adapter["unknown_not_inferred"]["original_environment"],
            "actions_search_executed":exp47["execution"]["github_actions_search_executed"],
            "pre_correction_Q_index_bug_excluded_records":sorted(q_wrong),
            "verified_candidate_record_count":len(verified_src),
            "registered_formal_pareto_candidate_count":len(formal_pareto),
            "formal_pareto_git_sha_verified":len(formal_pareto),
            "numerical_result_replayed":False,
        },
        "owner_experiment_source_deletion_approvals":0,
        "original_experiment_deletions":0,
        "new_optimizer_runs":0,
        "new_independent_MNA_runs":0,
        "w5_read_only_inventory_can_proceed":True,
        "w4_evidence_removal_authorized":False,
        "limitations":[
            "Manifest path names are only historical lineage references; file hashes do not verify runtime execution.",
            "Q assignment classification is from manifest and saved documentation, not a fresh RF numeric re-evaluation.",
            "EXP-046 capacitor power correction must not be confused with EXP-047 Q-index bug.",
            "The 4 RF-F003 formal candidates are compared to their saved catalog/pareto evidence, not re-optimized.",
            "Source-level replay dependencies, dynamic Code Mode connections, external S2Ps and exact Python/JS environment not independently reconstructed.",
            "Read-only W5 audit may proceed, but no E/W deletion, Phase 3 gate or W4 completion is authorized."
        ]
    }
    return rows,summary


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output-dir",type=Path,required=True)
    p.add_argument("--emit-csv-chunks",action="store_true")
    a=p.parse_args()
    rows,summary=assess()
    out=a.output_dir
    out.mkdir(parents=True,exist_ok=True)
    buf=io.StringIO()
    w=csv.DictWriter(buf,fieldnames=FIELDS,lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    original=buf.getvalue()
    (out/"w4_exp046_exp047_131_provenance.csv").write_text(original,encoding="utf-8")
    (out/"w4_exp046_exp047_provenance_summary.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"
    )
    print("W4_EXP46_47_SUMMARY="+json.dumps(summary,ensure_ascii=False,separators=(",",":")))
    if a.emit_csv_chunks:
        for i in range(0,len(original),5000):
            print("W4_EXP46_47_CSV_CHUNK="+json.dumps({
                "seq":i//5000,"text":original[i:i+5000]
            },ensure_ascii=False,separators=(",",":")))
    print("W4_EXP46_47_PASS: 131 originals kept, all SHA verified, no deletion or RF reruns")


if __name__=="__main__":
    main()
