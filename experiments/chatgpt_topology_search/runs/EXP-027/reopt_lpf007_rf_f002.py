#!/usr/bin/env python3
"""Reoptimize LPF-007 topology under formal RF-F002 with the full_lpf solver.

Historical LPF-007 values are clipped only to form an initialization; all
component values, variable-C settings, and adjacent k values are reoptimized.
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
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
            stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def make_problem(candidate, policy, passband_points, stopband_points):
    topology = candidate["topology"]
    inductor_rows = topology["inductors"]
    fixed_cap_rows = topology["fixed_caps"]
    variable_rows = topology["variable_caps"]
    edges = []
    start_values = []
    inductor_index = {}
    for index, row in enumerate(inductor_rows):
        series = "LQP02HV"  # LPF-007's historical Q25 assumption maps to HV.
        edges.append((row["a"], row["b"], series))
        start_values.append(float(row["L_nH"]))
        inductor_index[row["id"]] = index
    for row in fixed_cap_rows:
        edges.append((row["a"], row["b"], "GJM01"))
        start_values.append(float(row["C_pF"]))
    graph = (int(topology["n_nodes"]) + 1, tuple(edges))
    layout = {
        "edges": tuple((int(row["a"]), int(row["b"])) for row in variable_rows),
        "roles": (None,) * len(variable_rows),
    }
    cap_limit = float(policy["components"]["IC_VARIABLE_C"]["max_total_variable_pf_per_branch"])
    values_by_case = candidate["ic_variable_C_pf_by_setting"]
    caps = np.asarray([
        [min(cap_limit, max(0.0, float(value))) for value in values_by_case[case]]
        for case in ("B71", "B12", "B28", "B13+B14", "B26", "B8")
    ])
    if caps.shape != (6, len(variable_rows)):
        raise ValueError("LPF-007 variable-C table does not match its branch count")
    initial = np.asarray(start_values + caps.reshape(-1).tolist(), dtype=float)

    physical_order = [inductor_index[name] for name in candidate["chip_physical_order"]]
    coupling = np.eye(len(inductor_rows))
    for (left, right), coefficient in zip(
            candidate["strong_neighbor_pairs"], candidate["neighbor_k_values"]):
        left_id, right_id = f"L{left}", f"L{right}"
        # The saved LPF-007 pairs name inductor IDs in its original ordering.
        a, b = inductor_index[left_id], inductor_index[right_id]
        limit = float(policy["coupling_limits"]["chip_chip_strong_adjacent_abs_k_max"])
        clipped = float(np.clip(float(coefficient), -limit, limit))
        coupling[a, b] = coupling[b, a] = clipped

    problem = FullLPFProblem(
        graph, layout, coupling, constraint_id="RF-F002",
        passband_points=passband_points, stopband_points=stopband_points,
        physical_order=physical_order, resolved_policy=policy)
    k_start = problem.initial_coefficients.copy()
    initial_vector = problem.initial_vector(initial, coupling_values=k_start)
    transforms = {
        "historical_candidate_id": candidate["candidate_id"],
        "historical_constraint_id": "RF-F001",
        "historical_worst_il_db_not_reused_as_rf_f002_result":
            candidate["performance"]["worst_IL_db"],
        "historical_variable_caps_clipped_to_formal_1p5_pf_max": True,
        "historical_neighbor_k_clipped_to_formal_0p15_max": True,
        "historical_values_are_initialization_only": True,
        "variable_cap_initial_pf": caps.tolist(),
        "initial_adjacent_k": k_start.tolist(),
        "fixed_element_initial_values": initial[:len(start_values)].tolist(),
    }
    return problem, initial_vector, transforms


def run(args):
    policy = load_constraint("RF-F002")
    resources_before = _runtime_snapshot()
    wall_started = time.monotonic()
    source = ROOT / "candidates" / "LPF-007.json"
    candidate = json.loads(source.read_text(encoding="utf-8"))
    problem, initial, transforms = make_problem(
        candidate, policy, args.passband_points, args.stopband_points)
    optimized = problem.optimize(
        initial, harmonic_targets=(30.0, 35.0), maxiter=args.maxiter,
        ftol=args.ftol)
    wall_elapsed = time.monotonic() - wall_started
    result = {
        "run_id": "RF-F002-LPF007-reoptimization",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit_sha": _git_sha(),
        "git_worktree_status": _git_status(),
        "constraint_id": "RF-F002",
        "effective_constraint_sha256": constraint_fingerprint(policy),
        "constraint_snapshot_sha256": _sha256(ROOT / "data/constraints/formal/RF-F002.json"),
        "bands_csv_sha256": _sha256(ROOT / "data/bands.csv"),
        "source_candidate_sha256": _sha256(source),
        "source_code_sha256": _sha256(Path(__file__)),
        "solver_code_sha256": _sha256(ROOT / "experiments/matching_limit/full_lpf.py"),
        "runtime_source_sha256": _sha256(Path(__file__)),
        "seed": args.seed,
        "optimizer_settings": {
            "method": "SLSQP epigraph minimax",
            "harmonic_continuation_db": [30, 35],
            "maxiter_per_stage": args.maxiter,
            "ftol": args.ftol,
            "passband_points_per_segment": args.passband_points,
            "stopband_points_per_segment": args.stopband_points,
            "independent_validation_points_per_segment": 21,
        },
        "numeric_environment": {
            "python": platform.python_version(),
            "numpy": importlib.metadata.version("numpy"),
            "scipy": importlib.metadata.version("scipy"),
            "numpy_blas_lapack": _runtime_snapshot()["blas_lapack"],
            "blas_threads": {name: os.environ.get(name) for name in
                             ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")},
        },
        "resource_measurement": {
            "before": resources_before,
            "after": _runtime_snapshot(),
            "process_peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                                           * (1024 if platform.system() == "Linux" else 1)),
            "wall_elapsed_seconds": round(wall_elapsed, 6),
        },
        "initialization_transform": transforms,
        "result": optimized,
    }
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    if output.exists() and not args.overwrite:
        raise FileExistsError(f"Refusing to overwrite {output}; use --overwrite explicitly")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n",
                          encoding="utf-8")
    os.replace(temporary, output)
    print(json.dumps({
        "output": str(output.relative_to(ROOT) if output.is_relative_to(ROOT) else output),
        "analysis_mode": optimized["analysis_mode"],
        "status": optimized["best_found_category"],
        "converged": optimized["converged"],
        "mandatory_30db_met": optimized["mandatory_30db_met_on_dense_grid"],
        "nominal_35db_met": optimized["nominal_35db_met_on_dense_grid"],
        "worst_il_db": optimized["worst_il_db"],
        "dense_grid_constraints_met": optimized["dense_grid_constraints_met"],
        "min_h2_db": optimized["min_h2_db"],
        "min_h3_db": optimized["min_h3_db"],
        "chip_area_cost": optimized["chip_area_cost"],
        "elapsed_seconds": optimized["elapsed_seconds"],
        "max_independent_gain_mismatch": optimized["max_independent_gain_mismatch"],
        "max_power_residual_w": optimized["max_power_residual_w"],
    }, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="results/full-lpf/rf-f002-lpf007.json")
    parser.add_argument("--passband-points", type=int, default=9)
    parser.add_argument("--stopband-points", type=int, default=9)
    parser.add_argument("--maxiter", type=int, default=120)
    parser.add_argument("--ftol", type=float, default=1e-8)
    parser.add_argument("--seed", type=int, default=20261014,
                        help="Recorded provenance seed; this single-start continuation is deterministic")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.passband_points < 2 or args.stopband_points < 2 or args.maxiter < 1:
        parser.error("point counts must be >=2 and maxiter must be positive")
    run(args)


if __name__ == "__main__":
    main()
