#!/usr/bin/env python3
"""Run and record exactly one frozen Issue #439 seed, with no retry/resume."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
PRE = ROOT / "project/diagnostics/issue439/preflight.json"
INITIAL = ROOT / "project/diagnostics/issue439/initial_evaluations.json"
LOG = ROOT / "project/diagnostics/issue439/execution.json"
MAIN = "79789f2f3a4b8a9feece9a4cc9a212b4c086f1ed"
UV_ENV = Path("/tmp/issue439-uv-env")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    os.replace(temporary, path)


def load_log():
    if LOG.exists():
        return json.loads(LOG.read_text())
    initial = json.loads(INITIAL.read_text())
    return dict(issue=439, phase="running", source_head=MAIN,
                preflight_sha256=digest(PRE), initial_evaluations_sha256=digest(INITIAL),
                primary_samples_initial=initial["primary_requested_completed_samples"],
                rows=[])


def parse_time(path: Path):
    text = path.read_text(errors="replace") if path.exists() else ""
    out = {"raw_path": str(path), "raw": text}
    labels = {
        "User time (seconds)": "user_seconds",
        "System time (seconds)": "system_seconds",
        "Maximum resident set size (kbytes)": "max_rss_kib",
        "Exit status": "gnu_time_exit_status",
    }
    for line in text.splitlines():
        for label, key in labels.items():
            if line.startswith(label + ":"):
                value = line.split(":", 1)[1].strip()
                out[key] = int(value) if key in ("max_rss_kib", "gnu_time_exit_status") else float(value)
        if line.startswith("Elapsed (wall clock) time"):
            out["elapsed_wall"] = line.split(":", 1)[1].strip()
    return out


def validate_completed(preflight, seed, output: Path, rc: int):
    inp_path, result_path = output / "input.json", output / "result.json"
    if not inp_path.is_file():
        raise RuntimeError("Worker did not persist input.json; reservation/unknown must be retained")
    inp = json.loads(inp_path.read_text())
    expected = preflight["per_seed"][str(seed)]
    if (inp.get("kind") != "development_worker_input_v1" or inp.get("seed") != seed
            or inp.get("source", {}).get("head") != MAIN
            or inp.get("source") != preflight["source_identity"]
            or inp.get("policy_id") != "RF-T008"
            or inp.get("policy_fingerprint") != preflight["rf"]["effective_sha256"]
            or inp.get("plan_sha256") != expected["plan_sha256"]
            or inp.get("start", {}).get("vector_sha256") != expected["vector_sha256"]
            or inp.get("max_search_forwards") != 150000
            or inp.get("search_bounds_mode") != "physical_full"
            or inp.get("spot_checks") != {"terminal": [0, 111]}):
        raise RuntimeError("Worker input differs from frozen source/RF/seed/plan/spot contract")
    if not result_path.is_file():
        raise RuntimeError("No result.json; preserve raw and STOP without retry/resume")
    result = json.loads(result_path.read_text())
    if rc not in (0, 4):
        raise RuntimeError(f"Worker exit {rc} is not a completed solver state")
    if result.get("status") != ("converged" if rc == 0 else "not_converged"):
        raise RuntimeError("CLI exit code and recorded solver status disagree")
    step = result["steps"][0]
    costs = result["costs"]
    if (step["solver"] != "hybrid" or step["solver_result"]["nfev"] != step["forward_count"]
            or not 0 <= step["forward_count"] <= 150000
            or costs["search_forwards"] != step["forward_count"]
            or costs["search_requested_samples"] != step["forward_count"] * 70
            or costs["search_requested_samples"] > 10_500_000
            or result["forward_count"] != costs["search_forwards"] +
               costs["selection_requested_samples"] // 84 + costs["terminal_requested_samples"] // 476
            or costs["selection_requested_samples"] not in (0, 84)
            or costs["terminal_requested_samples"] not in (0, 476)):
        raise RuntimeError("Worker sample/forward accounting mismatch")
    if (len(result["selection"]["ranked"]) != 1 or len(result["terminal"]["candidates"]) != 1
            or result["selection"]["forward_count"] != 1 or result["terminal"]["forward_count"] != 1):
        raise RuntimeError("Expected exactly one best-J candidate through selection and terminal")
    best = step["rf_best"]
    selected = result["selection"]["ranked"][0]
    terminal = result["terminal"]["candidates"][0]
    if not (best["vector_sha256"] == selected["vector_sha256"] == terminal["vector_sha256"]):
        raise RuntimeError("Search best, selection, and terminal vector SHA mismatch")
    if len(best["vector"]) != 25 or terminal["independent"].get("status") != "pass":
        raise RuntimeError("Incomplete vector or terminal independent spot failure")
    checkpoints = sorted((output / "checkpoints").glob("*.json"))
    if not checkpoints:
        raise RuntimeError("No checkpoints persisted")
    checkpoint_records = []
    previous_forward = -1
    for path in checkpoints:
        payload = json.loads(path.read_text())
        if payload.get("plan_sha256") != expected["plan_sha256"] or payload.get("seed") != seed:
            raise RuntimeError(f"Checkpoint identity mismatch: {path.name}")
        if payload["forward_count"] < previous_forward:
            raise RuntimeError("Checkpoint forward counts are not monotone")
        previous_forward = payload["forward_count"]
        checkpoint_records.append(dict(name=path.name, sha256=digest(path),
                                       forward_count=payload["forward_count"],
                                       best_vector_sha256=payload["best"]["vector_sha256"]))
    if checkpoint_records[-1]["best_vector_sha256"] != best["vector_sha256"]:
        raise RuntimeError("Final checkpoint differs from best-J result")
    return dict(input_sha256=digest(inp_path), result_sha256=digest(result_path),
                plan_sha256=inp["plan_sha256"], status=result["status"], exit_code=rc,
                stop_reason=step["stop_reason"], nfev=step["solver_result"]["nfev"],
                nit=step["solver_result"]["runs"][0]["nit"],
                converged=step["converged"], search_requested_samples=costs["search_requested_samples"],
                selection_requested_samples=costs["selection_requested_samples"],
                terminal_requested_samples=costs["terminal_requested_samples"],
                forward_count_total=result["forward_count"], best_vector_sha256=best["vector_sha256"],
                best_objective_j=best["objective_j"], terminal_strict=terminal["assessment"]["strict_feasible"],
                terminal_worst_il_db=terminal["assessment"]["worst_il_db"],
                terminal_independent=terminal["independent"], checkpoints=checkpoint_records)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--checkout", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--logs", type=Path, default=Path("/tmp/issue439-process-logs"))
    args = parser.parse_args()
    seed = args.seed
    preflight = json.loads(PRE.read_text())
    initial = json.loads(INITIAL.read_text())
    if preflight["source_head"] != MAIN or preflight["per_seed"][str(seed)]["status"] != "legal":
        raise SystemExit("STOP: seed/source is not in the frozen legal preflight")
    log = load_log()
    expected_next = next((row["seed"] for row in preflight["starts"]
                          if row["status"] == "legal" and
                          not any(existing["seed"] == row["seed"] for existing in log["rows"])), None)
    if expected_next != seed:
        raise SystemExit(f"STOP: fixed sequential order requires seed {expected_next}, not {seed}")
    checkout = args.checkout.resolve()
    output = args.output.resolve()
    if output.exists() or not output.parent.is_dir():
        raise SystemExit("STOP: output must be a fresh path with existing parent")
    head = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if head != MAIN:
        raise SystemExit(f"STOP: job checkout is not pinned main {MAIN}: {head}")
    dirty = subprocess.check_output(["git", "-C", str(checkout), "status", "--porcelain=v1", "--", "src", "pyproject.toml", "uv.lock", "scripts/run_rf_search.py"], text=True)
    if dirty:
        raise SystemExit(f"STOP: job source is dirty: {dirty}")

    source_root = ROOT / "project/diagnostics/issue439/inputs"
    job_input_dir = checkout / "project/diagnostics/issue439/inputs"
    job_input_dir.mkdir(parents=True, exist_ok=True)
    for name in (f"seed-{seed}.yaml", f"seed-{seed}-starts.json"):
        src, dst = source_root / name, job_input_dir / name
        expected_sha = (preflight["per_seed"][str(seed)]["config_sha256"] if name.endswith(".yaml")
                        else preflight["per_seed"][str(seed)]["starts_sha256"])
        if digest(src) != expected_sha:
            raise SystemExit(f"STOP: frozen input changed: {src}")
        if dst.exists():
            raise SystemExit(f"STOP: refusing to overwrite existing checkout input: {dst}")
        shutil.copyfile(src, dst)
        if digest(dst) != expected_sha:
            raise SystemExit(f"STOP: copied input byte mismatch: {dst}")

    # Preserve an explicit running marker before the process can spend any RF samples.
    row = dict(seed=seed, status="running", checkout=str(checkout), output=str(output),
               checkout_head=head, config_sha256=preflight["per_seed"][str(seed)]["config_sha256"],
               starts_sha256=preflight["per_seed"][str(seed)]["starts_sha256"],
               vector_sha256=preflight["per_seed"][str(seed)]["vector_sha256"],
               max_search_forwards=150000, max_search_samples=10_500_000,
               started_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    log["rows"].append(row)
    log["phase"] = "running"
    atomic_json(LOG, log)

    args.logs.mkdir(parents=True, exist_ok=True)
    stdout_path = args.logs / f"seed-{seed}.stdout.txt"
    time_path = args.logs / f"seed-{seed}.time.txt"
    env = os.environ.copy()
    env.update(OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
               UV_PROJECT_ENVIRONMENT=str(UV_ENV))
    config = f"project/diagnostics/issue439/inputs/seed-{seed}.yaml"
    starts = f"project/diagnostics/issue439/inputs/seed-{seed}-starts.json"
    command = ["/usr/bin/time", "-v", "-o", str(time_path), "uv", "run", "--frozen", "python",
               "scripts/run_development_worker.py", "--objective-mode", "weighted_violation",
               "--max-search-forwards", "150000", "--seed", str(seed), "--arm", "hybrid",
               "--config", config, "--starts", starts, "--checkpoint-interval", "100",
               "--spot-checks", '{"terminal":[0,111]}', "--output", str(output)]
    start = time.monotonic()
    with stdout_path.open("wb") as stream:
        completed = subprocess.run(command, cwd=checkout, env=env, stdout=stream,
                                   stderr=subprocess.STDOUT, check=False)
    wall = time.monotonic() - start
    resources = parse_time(time_path)
    try:
        summary = validate_completed(preflight, seed, output, completed.returncode)
        status = "complete"
        validation_error = None
    except Exception as exc:
        summary = None
        status = "stop_unknown"
        validation_error = f"{type(exc).__name__}: {exc}"
    row.update(status=status, process_exit_code=completed.returncode,
               stdout_path=str(stdout_path), stdout_sha256=digest(stdout_path),
               resources=resources, measured_wall_seconds=wall,
               resources_sha256=digest(time_path) if time_path.exists() else None,
               summary=summary, validation_error=validation_error,
               completed_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    log["primary_samples_jobs"] = sum(
        r.get("summary", {}).get("search_requested_samples", 0) +
        r.get("summary", {}).get("selection_requested_samples", 0) +
        r.get("summary", {}).get("terminal_requested_samples", 0)
        for r in log["rows"])
    log["search_forwards_completed"] = sum(r.get("summary", {}).get("nfev", 0) for r in log["rows"])
    log["primary_samples_accounted_so_far"] = initial["primary_requested_completed_samples"] + log["primary_samples_jobs"]
    log["primary_samples_cap_with_max_5_dense_reserved"] = log["primary_samples_accounted_so_far"] + 5 * (28028 + 84)
    log["search_forward_cap"] = 3_000_000
    log["primary_samples_cap"] = 211_000_000
    if log["search_forwards_completed"] > log["search_forward_cap"] or log["primary_samples_cap_with_max_5_dense_reserved"] > log["primary_samples_cap"]:
        status = row["status"] = "stop_unknown"
        row["validation_error"] = "Accounted/reserved samples exceed Issue #439 cap"
    atomic_json(LOG, log)
    print(json.dumps(dict(seed=seed, status=status, exit_code=completed.returncode,
                          summary=summary, resources=resources,
                          validation_error=row["validation_error"]), indent=2, allow_nan=False))
    if status != "complete":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
