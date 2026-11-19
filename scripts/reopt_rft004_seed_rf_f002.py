#!/usr/bin/env python3
"""Resynthesize a two-variable-C RF-F002 circuit from an RF-T004 seed.

A selected third trial-tunable branch is frozen to one shared fixed GJM01
starting value (the mean of its six settings); the other two branches alone
remain variable. The full fixed circuit, both variable branches, and coupling
are then jointly reoptimized using RF-F002. Trial results are never relabeled.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time

import numpy as np
import psutil
import scipy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments" / "matching_limit"))

from full_lpf import FullLPFProblem
from lpf.constraint_versions import constraint_fingerprint, load_constraint


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _runtime_snapshot():
    memory = psutil.virtual_memory()
    model = None
    try:
        model = next((line.split(":", 1)[1].strip()
                      for line in Path("/proc/cpuinfo").read_text().splitlines()
                      if line.lower().startswith("model name")), None)
    except OSError:
        pass
    config = np.__config__.show(mode="dicts")
    dependencies = config.get("Build Dependencies", {}) if isinstance(config, dict) else {}
    blas_lapack = {}
    for name in ("blas", "lapack"):
        backend = dependencies.get(name, {}) if isinstance(dependencies, dict) else {}
        if isinstance(backend, dict):
            blas_lapack[name] = {key: backend[key] for key in ("name", "version", "has ilp64")
                                 if key in backend}
    return {
        "cpu_model": model,
        "logical_cpu_count": psutil.cpu_count(logical=True),
        "physical_cpu_count": psutil.cpu_count(logical=False),
        "memory_total_bytes": memory.total,
        "memory_available_bytes": memory.available,
        "blas_lapack": blas_lapack,
    }


def _git_status():
    try:
        return subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT,
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def _git_sha():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build_problem(payload, candidate_id, freeze_index, policy, points):
    if payload.get("constraint_id") != "RF-T004":
        raise ValueError("Seed source must be explicitly identified as RF-T004")
    candidates = {candidate["id"]: candidate for candidate in payload.get("candidates", [])}
    if candidate_id not in candidates:
        raise ValueError(f"RF-T004 seed candidate not found: {candidate_id}")
    candidate = candidates[candidate_id]
    variable_edges = payload.get("variable_C_edges", [])
    if len(variable_edges) != 3 or not 0 <= freeze_index < 3:
        raise ValueError("This converter requires an explicit three-C seed and valid freeze index")
    seed_values = candidate["variable_C_pf"]
    case_order = ("B71", "B12", "B28", "B13+B14", "B26", "B8")
    by_case = np.asarray([seed_values[case] for case in case_order], dtype=float)
    if by_case.shape != (6, 3) or np.any(~np.isfinite(by_case)):
        raise ValueError("RF-T004 tunable-C seed must contain six settings by three branches")
    limit = float(policy["components"]["IC_VARIABLE_C"]["max_total_variable_pf_per_branch"])
    if np.any(by_case < -1e-10) or np.any(by_case > limit + 1e-10):
        raise ValueError("RF-T004 seed C values lie outside the inherited RF-F002 range")

    kept_indices = [index for index in range(3) if index != freeze_index]
    fixed_edges = [tuple(map(int, edge)) for edge in candidate["C_fixed_edges"]]
    fixed_values = list(map(float, candidate["C_fixed_pf"]))
    frozen_edge = tuple(map(int, variable_edges[freeze_index]))
    frozen_value = float(np.mean(by_case[:, freeze_index]))
    # Same-Q fixed capacitors on the same edge are electrically equivalent;
    # merge them so the physical component and area accounting stay explicit.
    if frozen_edge in fixed_edges:
        index = fixed_edges.index(frozen_edge)
        fixed_values[index] += frozen_value
    else:
        fixed_edges.append(frozen_edge)
        fixed_values.append(frozen_value)

    inductor_edges = [tuple(map(int, edge)) for edge in payload["inductor_edges"]]
    inductor_types = list(candidate["L_series"])
    if any(kind != "LQP02HV" for kind in inductor_types):
        raise ValueError("This bounded resynthesis path is only for the documented HV seed family")
    graph_edges = [(a, b, kind) for (a, b), kind in zip(inductor_edges, inductor_types)]
    graph_edges.extend((a, b, "GJM01") for a, b in fixed_edges)
    graph = (max(max(a, b) for a, b, _ in graph_edges) + 1, tuple(graph_edges))
    layout = {
        "edges": tuple(tuple(map(int, variable_edges[index])) for index in kept_indices),
        "roles": tuple(None if variable_edges[index][1] == 0 else "bridge"
                        for index in kept_indices),
    }
    # Clip is not needed for the pinned B35/D35 seeds; explicit validation
    # prevents a future trial seed from silently exceeding formal bounds.
    caps = np.asarray([[by_case[case_index, index] for index in kept_indices]
                       for case_index in range(6)], dtype=float)
    fixed_values_all = list(map(float, candidate["L_nH"])) + fixed_values
    initial = np.asarray(fixed_values_all + caps.reshape(-1).tolist(), dtype=float)

    physical_row = list(payload["physical_chip_row"])
    # The candidate row labels L0..L3; component order matches inductor_edges.
    physical_order = [int(name[1:]) for name in physical_row]
    coupling = np.eye(len(inductor_edges))
    for position, value in enumerate(candidate["neighbor_k"]):
        a, b = physical_order[position], physical_order[position + 1]
        coupling[a, b] = coupling[b, a] = float(value)
    problem = FullLPFProblem(
        graph, layout, coupling, constraint_id="RF-F002",
        passband_points=points, stopband_points=points,
        physical_order=physical_order, resolved_policy=policy)
    initial_vector = problem.initial_vector(initial)
    transform = {
        "source_trial_id": "RF-T004",
        "source_trial_candidate_id": candidate_id,
        "source_trial_target_harmonic_db": candidate["target_harmonic_db"],
        "source_trial_three_variable_c_values_are_initialization_only": True,
        "frozen_variable_index": freeze_index,
        "frozen_variable_edge": list(frozen_edge),
        "frozen_branch_shared_fixed_start_pf_mean": frozen_value,
        "merged_into_existing_fixed_cap": frozen_edge in [
            tuple(map(int, edge)) for edge in candidate["C_fixed_edges"]],
        "remaining_formal_variable_cap_edges": [list(edge) for edge in layout["edges"]],
        "fixed_caps_initial_pf": fixed_values,
        "initial_variable_caps_pf": caps.tolist(),
        "initial_adjacent_k": list(map(float, candidate["neighbor_k"])),
        "seed_values_are_not_reported_as_rf_f002_metrics": True,
    }
    return problem, initial_vector, transform


def run(args):
    policy = load_constraint("RF-F002")
    resources_before = _runtime_snapshot()
    wall_started = time.monotonic()
    source = Path(args.seed_json)
    if not source.is_absolute():
        source = ROOT / source
    payload = json.loads(source.read_text(encoding="utf-8"))
    problem, initial, transform = build_problem(
        payload, args.candidate_id, args.freeze_index, policy, args.grid_points)
    result = problem.optimize(initial, harmonic_targets=(30.0, 35.0),
                              maxiter=args.maxiter, ftol=args.ftol)
    wall_elapsed = time.monotonic() - wall_started
    record = {
        "run_id": f"RF-F002-resynthesis-from-{args.candidate_id}-freeze{args.freeze_index}",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit_sha": _git_sha(),
        "git_worktree_status": _git_status(),
        "analysis_mode": "full_lpf",
        "constraint_id": "RF-F002",
        "effective_constraint_sha256": constraint_fingerprint(policy),
        "formal_snapshot_sha256": _sha256(ROOT / "data/constraints/formal/RF-F002.json"),
        "bands_csv_sha256": _sha256(ROOT / "data/bands.csv"),
        "seed_source_file_sha256": _sha256(source),
        "run_source_sha256": _sha256(Path(__file__)),
        "solver_source_sha256": _sha256(ROOT / "experiments/matching_limit/full_lpf.py"),
        "seed_source_commit": args.seed_source_commit,
        "seed_source_constraint_id": "RF-T004",
        "candidate_id_is_source_lineage_not_new_experiment_id": True,
        "seed": args.seed,
        "optimizer_settings": {
            "method": "SLSQP epigraph minimax",
            "harmonic_continuation_db": [30, 35],
            "maxiter_per_stage": args.maxiter,
            "ftol": args.ftol,
            "optimization_points_per_interval": args.grid_points,
            "independent_validation_points_per_interval": 21,
        },
        "numeric_environment": {
            "python": platform.python_version(),
            "numpy": importlib.metadata.version("numpy"),
            "scipy": importlib.metadata.version("scipy"),
            "numpy_blas_lapack": _runtime_snapshot()["blas_lapack"],
            "threads": {name: os.environ.get(name) for name in
                        ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")},
        },
        "resource_measurement": {
            "before": resources_before,
            "after": _runtime_snapshot(),
            "process_peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                                           * (1024 if platform.system() == "Linux" else 1)),
            "wall_elapsed_seconds": round(wall_elapsed, 6),
        },
        "topology_resynthesis": transform,
        "result": result,
    }
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    if output.exists() and not args.overwrite:
        raise FileExistsError(f"Refusing to overwrite {output}; pass --overwrite explicitly")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(record, indent=2, allow_nan=False) + "\n",
                          encoding="utf-8")
    os.replace(temporary, output)
    print(json.dumps({
        "output": str(output.relative_to(ROOT) if output.is_relative_to(ROOT) else output),
        "source_trial": args.candidate_id,
        "constraint_id": "RF-F002",
        "status": result["best_found_category"],
        "converged": result["converged"],
        "mandatory_30db_met": result["mandatory_30db_met_on_dense_grid"],
        "nominal_35db_met": result["nominal_35db_met_on_dense_grid"],
        "worst_il_db": result["worst_il_db"],
        "dense_grid_constraints_met": result["dense_grid_constraints_met"],
        "min_h2_db": result["min_h2_db"],
        "min_h3_db": result["min_h3_db"],
        "chip_area_cost": result["chip_area_cost"],
        "elapsed_seconds": result["elapsed_seconds"],
    }, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-json", required=True,
                        help="Pinned RF-T004 candidate collection; seed input only")
    parser.add_argument("--seed-source-commit", required=True,
                        help="Git commit containing the trial seed collection")
    parser.add_argument("--candidate-id", choices=("T004-B35", "T004-D35"), required=True)
    parser.add_argument("--freeze-index", type=int, default=2,
                        help="Third trial C branch to make fixed; only the other two remain tunable")
    parser.add_argument("--grid-points", type=int, default=9)
    parser.add_argument("--maxiter", type=int, default=120)
    parser.add_argument("--ftol", type=float, default=1e-8)
    parser.add_argument("--seed", type=int, default=20261014)
    parser.add_argument("--output", required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.grid_points < 2 or args.maxiter < 1:
        parser.error("grid-points must be >=2 and maxiter positive")
    run(args)


if __name__ == "__main__":
    main()
