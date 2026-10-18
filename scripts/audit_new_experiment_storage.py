#!/usr/bin/env python3
"""Phase 2 Git-only evidence gate for NEW EXP-048+ runs.

This is a provenance/completeness audit, not an RF solver or independent MNA.
Historical EXP-001..047 are immutable and outside this new storage schema.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.experiment_id_registry import PATH as LEDGER_PATH, read_ledger  # noqa: E402
from src.lpf.experiment_manifest import validate_manifest  # noqa: E402

POLICY = "phase2-git-only-v1"
RUNS = ("experiments/chatgpt_topology_search/runs", "experiments/matching_limit/runs")
CASES = {"B71", "B12", "B28", "B13+B14", "B26", "B8"}
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
EXP = re.compile(r"EXP-(\d{3,})\Z")
STAGES = {"planned", "running", "preservation_incomplete", "complete"}
REASONS = {"best", "pareto", "30db_boundary", "35db_boundary",
           "topology_diversity", "representative_failure", "other"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"),
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError("non-finite " + v)))


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.PIPE)


def tracked_file(root, name, *, committed):
    """Reject absolute, traversing or symlink-escaping evidence references."""
    require(isinstance(name, str) and name and "\\" not in name, "invalid evidence path")
    pp = PurePosixPath(name)
    require(not pp.is_absolute() and pp.as_posix() == name
            and all(x not in (".", "..") for x in name.split("/")),
            "unsafe evidence path: " + name)
    root = Path(root).resolve()
    path = (root / name).resolve()
    require(path.is_relative_to(root) and path.is_file(), "missing/escaping file: " + name)
    raw = path.read_bytes()
    if committed:
        try:
            from_head = git(root, "show", "HEAD:" + name)
        except subprocess.CalledProcessError as exc:
            raise ValueError("evidence not committed at HEAD: " + name) from exc
        require(raw == from_head, "working file differs from committed evidence: " + name)
    return raw


def evidence_check(root, item, *, committed, max_file_bytes, exception):
    require(isinstance(item, dict), "evidence entry must be an object")
    require(isinstance(item.get("path"), str) and SHA256.fullmatch(str(item.get("sha256", ""))),
            "evidence needs path and sha256")
    raw = tracked_file(root, item["path"], committed=committed)
    require(hashlib.sha256(raw).hexdigest() == item["sha256"],
            "evidence SHA-256 mismatch: " + item["path"])
    require(len(raw) <= max_file_bytes or exception,
            "file exceeds 1MiB without approved exception: " + item["path"])
    return len(raw)


def validate_checkpoint(payload, candidate_id):
    """Structural completeness only. Numerical truth is a separate verification."""
    require(isinstance(payload, dict), "checkpoint JSON must be an object")
    require(payload.get("candidate_id") == candidate_id, "checkpoint candidate ID mismatch")
    require(isinstance(payload.get("topology"), dict) and payload["topology"],
            "checkpoint missing topology/connectivity")
    require(isinstance(payload.get("components"), list) and payload["components"],
            "checkpoint missing complete components")
    require(isinstance(payload.get("couplings"), list), "checkpoint missing coupling list")
    require(isinstance(payload.get("chip_row"), list), "checkpoint missing chip physical order")
    settings = payload.get("ic_variable_C_pf_by_setting")
    require(isinstance(settings, dict) and set(settings) == CASES,
            "checkpoint must have all 6 variable-C settings")
    counts = {len(v) for v in settings.values() if isinstance(v, list)}
    require(len(counts) == 1 and len(settings) == 6 and all(
        isinstance(v, list) and all(type(c) in (float, int) and 0 <= c <= 3 for c in v)
        for v in settings.values()), "variable C arrays/value range invalid")
    # A numeric checkpoint is complete enough to inspect, not automatically RF-compliant.
    require(isinstance(payload.get("fixed_values"), dict),
            "checkpoint missing fixed L/C and Q/series parameters")


def validate_selection(selection):
    require(isinstance(selection, dict), "selection plan required")
    require(type(selection.get("top_k")) is int and selection["top_k"] >= 0,
            "selection.top_k must be >= 0")
    reasons = selection.get("retain")
    require(isinstance(reasons, list) and reasons and
            all(r in REASONS for r in reasons) and len(set(reasons)) == len(reasons),
            "invalid retention categories")
    require(isinstance(selection.get("rule"), str) and selection["rule"].strip(),
            "explicit selection rule required before searching")
    require(type(selection.get("estimated_curated_bytes")) is int
            and selection["estimated_curated_bytes"] >= 0,
            "pre-run Git size estimate is required")


def validate_summary(summary, experiment_id, checkpoint_count):
    require(isinstance(summary, dict) and summary.get("experiment_id") == experiment_id,
            "run summary identity mismatch")
    counts = summary.get("attempts")
    keys = {"planned", "attempted", "converged", "nonconverged", "failed", "not_started"}
    require(isinstance(counts, dict) and set(counts) == keys and
            all(type(n) is int and n >= 0 for n in counts.values()),
            "run summary requires nonnegative attempt counts")
    require(counts["converged"] + counts["nonconverged"] + counts["failed"]
            == counts["attempted"], "attempt outcomes do not sum")
    require(counts["attempted"] + counts["not_started"] == counts["planned"],
            "planned/attempted/unstarted mismatch")
    require(summary.get("selected_candidate_count") == checkpoint_count,
            "selected checkpoint count mismatch")
    require(isinstance(summary.get("limitations"), list), "summary limitations required")
    if checkpoint_count == 0:
        require(isinstance(summary.get("no_candidate_reason"), str) and
                summary["no_candidate_reason"].strip(), "missing no-candidate explanation")


def find_run(root, experiment_id):
    for base in RUNS:
        directory = Path(root) / base / experiment_id
        if directory.is_dir():
            return directory
    raise ValueError("run directory not found: " + experiment_id)


def reservation_on_main(root, experiment_id, *, main_ref, starting):
    try:
        ledger = git(root, "show", f"{main_ref}:{LEDGER_PATH}").decode("utf-8")
    except subprocess.CalledProcessError as exc:
        raise ValueError("main reservation ledger unavailable; fetch main before running") from exc
    rows = read_ledger(ledger)
    found = [r for r in rows if r["experiment_id"] == experiment_id]
    require(len(found) == 1, "EXP ID is not reserved on main: " + experiment_id)
    require(found[0]["state"] in (
        {"reserved", "active"} if starting else {"reserved", "active", "completed", "cancelled"}
    ), "invalid main reservation state: " + experiment_id)
    return found[0]


def validate_run(root, experiment_id, *, mode="audit", main_ref="origin/main"):
    require(EXP.fullmatch(experiment_id) and int(experiment_id[4:]) >= 48,
            "policy gate applies to EXP-048+")
    root = Path(root).resolve()
    run = find_run(root, experiment_id)
    record = read_json(run / "storage_record.json")
    manifest = read_json(run / "manifest.json")
    require(record.get("schema_version") == 1 and record.get("policy") == POLICY
            and record.get("experiment_id") == experiment_id
            and record.get("phase") == "Phase 2", "storage record identity/policy mismatch")
    require(manifest.get("experiment_id") == experiment_id, "manifest identity mismatch")
    validate_manifest(manifest, root=root)
    row = reservation_on_main(root, experiment_id, main_ref=main_ref,
                              starting=mode == "preflight")
    require(manifest["constraints"]["constraint_id"] == row["constraint_id"],
            "main reservation and manifest RF conditions disagree")
    stage = record.get("stage")
    require(stage in STAGES, "invalid preservation stage")
    validate_selection(record.get("selection"))
    if mode == "preflight":
        require(stage in {"planned", "running"}, "preflight expects planned/running stage")
        require(manifest["execution"]["status"] in {"planned", "running"},
                "manifest is not in a preflight execution state")
    if stage == "complete":
        require(manifest["execution"]["status"] not in {"planned", "running", "not_run"},
                "cannot finalize a run that has not executed")
    if stage in {"planned", "running"}:
        require(mode != "finalize", "run not finalized")
    require(isinstance(record.get("limitations"), list), "limitations field required")

    budget = read_json(root / "data/phase2_git_storage_budget.json")["thresholds"]
    exception = record.get("size_exception")
    if exception is not None:
        require(isinstance(exception, dict) and all(
            isinstance(exception.get(k), str) and exception[k].strip()
            for k in ("approved_by", "approval_url", "reason")),
            "size exception needs documented owner approval URL and reason")
    committed = stage == "complete" or mode == "finalize"
    total, paths, selected = 0, set(), set()
    evidence_in_manifest = {e["path"]: e["sha256"] for e in manifest["evidence"]}
    checkpoints = record.get("checkpoints")
    validations = record.get("validation_overlays")
    require(isinstance(checkpoints, list) and isinstance(validations, list),
            "checkpoint/validation lists required")

    for item in checkpoints:
        require(isinstance(item, dict) and
                isinstance(item.get("candidate_id"), str) and item["candidate_id"].strip(),
                "candidate_id required")
        require(item.get("selection_reason") in REASONS, "unknown candidate selection reason")
        require(item["candidate_id"] not in selected, "duplicate candidate")
        selected.add(item["candidate_id"])
        name = item.get("path")
        require(isinstance(name, str) and name.startswith(run.relative_to(root).as_posix() + "/"),
                "checkpoints must be under their EXP directory")
        require(name not in paths, "duplicate evidence path")
        paths.add(name)
        total += evidence_check(root, item, committed=committed,
                                max_file_bytes=budget["individual_new_file_hard_bytes"],
                                exception=exception is not None)
        require(evidence_in_manifest.get(name) == item["sha256"],
                "checkpoint absent/mismatched in manifest evidence")
        validate_checkpoint(json.loads((root / name).read_text(encoding="utf-8")), item["candidate_id"])

    for item in validations:
        require(isinstance(item, dict) and item.get("method") in
                {"independent_mna", "grid", "spd", "power_balance", "other"} and
                item.get("status") in {"passed", "failed", "not_run"},
                "invalid validation overlay label")
        name = item.get("path")
        require(name not in paths, "duplicate evidence path")
        paths.add(name)
        total += evidence_check(root, item, committed=committed,
                                max_file_bytes=budget["individual_new_file_hard_bytes"],
                                exception=exception is not None)
        require(evidence_in_manifest.get(name) == item["sha256"],
                "validation overlay absent/mismatched in manifest evidence")

    summary_ref = record.get("summary")
    if stage in {"complete", "preservation_incomplete"}:
        require(isinstance(summary_ref, dict), "final/partial run requires a summary reference")
    if summary_ref is not None:
        name = summary_ref.get("path")
        require(name not in paths, "summary also used as checkpoint/validation")
        total += evidence_check(root, summary_ref, committed=committed,
                                max_file_bytes=budget["individual_new_file_hard_bytes"],
                                exception=exception is not None)
        require(evidence_in_manifest.get(name) == summary_ref["sha256"],
                "run summary absent/mismatched in manifest evidence")
        validate_summary(read_json(root / name), experiment_id, len(checkpoints))

    if mode == "finalize":
        require(stage == "complete", "preservation is not complete; do not delete raw data")
    if stage == "complete":
        require(summary_ref is not None, "complete run requires a summary")
        require(record.get("git_readback") == "passed", "no HEAD readback confirmation")
        require(total <= budget["new_experiment_curated_soft_bytes"] or exception is not None,
                "curated run exceeds 512KiB without documented owner exception")
    return {"experiment_id": experiment_id, "stage": stage,
            "checkpoints": len(checkpoints), "validation_records": len(validations),
            "curated_bytes": total, "committed_readback": committed,
            "numerical_validation": manifest["validation"]["numerical"],
            "independent_validation": manifest["validation"]["independent"]}


def audit_all(root, *, main_ref):
    results = []
    for base in RUNS:
        for directory in sorted((Path(root) / base).glob("EXP-*")):
            m = EXP.fullmatch(directory.name)
            if m and int(m.group(1)) >= 48:
                results.append(validate_run(root, directory.name, main_ref=main_ref))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("audit", "preflight", "finalize"))
    parser.add_argument("experiment_id", nargs="?")
    parser.add_argument("--main-ref", default="origin/main")
    args = parser.parse_args()
    if args.mode == "audit":
        require(args.experiment_id is None, "audit scans all new runs")
        output = audit_all(ROOT, main_ref=args.main_ref)
    else:
        require(args.experiment_id is not None, "experiment ID is required")
        output = validate_run(ROOT, args.experiment_id, mode=args.mode,
                              main_ref=args.main_ref)
    print(json.dumps({"policy": POLICY, "result": output}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        raise SystemExit("FAIL new experiment storage: " + str(exc))
