"""Stage-3 C2: C1 problem / v2 budget boundary and in-memory audit record.

Calling this module is not authorization to run a scientific experiment. It
never writes historical evidence or performs dense / independent validation.
Each stage's optimizer is injectable; the v2 controller is the sole retry
policy. Numerical convergence, sampled RF observations, component checks and
candidate promotion are explicitly separate.
"""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import math
import platform
import sys
import time

import numpy as np
import scipy
from scipy.optimize import minimize

from lpf.slsqp_budget import (run_termination_aware_slsqp, TERMINATION_AWARE_POLICY_ID,
                              STANDARD_SLSQP_BUDGET)
from lpf.constraint_versions import rf_input_file
from ._grid import ROOT
from .problem_seed import definition_fingerprint, vector_fingerprint
from .sampled_epigraph import SampledEpigraph


def scipy_slsqp_stage(problem, vector, maxiter, target):
    """Single C1 constrained stage; scheduling and validation live elsewhere.

    ``target`` is unused: the mandatory limit is bound to the resolved policy,
    not a caller-selected replacement. Bounds include open-bound closures;
    component validation must reject excluded boundary points afterwards.
    """
    if target is not None:
        raise ValueError("RF target override is not supported")
    result = minimize(problem.objective, np.asarray(vector, float), method="SLSQP",
        bounds=problem.box.bounds, constraints=({"type": "ineq", "fun": problem.residuals},),
        options={"maxiter": maxiter})
    return result.x, {"success": bool(result.success), "status": int(result.status),
                      "message": str(result.message), "nit": int(result.nit),
                      "nfev": int(result.nfev)}


def _json_value(value):
    """Keep failed callback values inspectable without emitting invalid JSON."""
    if isinstance(value, np.ndarray):
        return _json_value(value.tolist())
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def _error(exc):
    return {"type": type(exc).__name__, "message": str(exc),
            "code": getattr(exc, "code", None),
            "sample_index": getattr(exc, "sample_index", None)}


def _grid(problem):
    e = problem.evaluator
    digest = hashlib.sha256()
    for arr, dtype in ((e.f, "<f8"), (e.setting, "<i8"),
                       (e.role, "<i8"), (e.segment, "<i8")):
        digest.update(np.asarray(arr, dtype=dtype).tobytes())
    return {"points_per_interval": problem.points_per_interval,
            "sample_count": len(e.f), "grid_sha256": digest.hexdigest(),
            "segment_count": len(set(e.segment.tolist()))}


def _observe(problem, vector):
    """Finite forward and component checks are observations, not promotion."""
    result = {"sampled_rf": {"state": "not_run"},
              "component_policy": {"state": "not_run"},
              "box": {"state": "not_run"}}
    try:
        x, _ = problem._split(vector)
        bounds = problem.box.bounds
        bad = [i for i, (v, (lo, hi)) in enumerate(zip(vector, bounds))
               if (lo is not None and v < lo) or (hi is not None and v > hi)]
        open_bad = [i for i in problem.box.open_lower if vector[i] <= bounds[i][0]]
        result["box"] = {"state": "pass" if not bad and not open_bad else "fail",
                         "outside_indices": bad, "open_lower_indices": open_bad}
        try:
            check = problem.circuit.validate_components(x)
            result["component_policy"] = {"state": "pass", "detail": check}
        except Exception as exc:
            result["component_policy"] = {"state": "fail", "error": _error(exc)}
        try:
            residual = problem.residuals(vector)
            if not np.all(np.isfinite(residual)):
                raise ValueError("Non-finite RF residual")
            role = problem.evaluator.role
            result["sampled_rf"] = {
                "state": "observed", "residuals_db": residual.tolist(),
                "minimum_residual_db": float(np.min(residual)),
                "passband_epigraph_min_residual_db": float(np.min(residual[role == 0])),
                "h2_min_residual_db": float(np.min(residual[role == 1])),
                "h3_min_residual_db": float(np.min(residual[role == 2])),
                "worst_il_db": float(vector[-1] - np.min(residual[role == 0])),
                "min_h2_db": float(problem.mandatory_stop_db + np.min(residual[role == 1])),
                "min_h3_db": float(problem.mandatory_stop_db + np.min(residual[role == 2])),
                "all_sampled_inequalities_nonnegative": bool(np.all(residual >= 0)),
            }
        except Exception as exc:
            result["sampled_rf"] = {"state": "error", "error": _error(exc)}
    except Exception as exc:
        result["input_error"] = _error(exc)
    return result


class _StageAbort(Exception):
    """Stop v2 safely on numerical/callback failure; retain recorded calls."""


def run_c1_staged(circuit, seed_record, *, coarse_points, fine_points,
                  optimize_stage=scipy_slsqp_stage, source_provenance=None):
    """Run one initial vector through existing v2; return a complete record.

    The seed is replayed and matched against C1, including its policy, topology,
    source-vector SHA, seed, jitter, output, and coarse grid. Callback contract:
    ``(problem, x, maxiter, None) -> (x, status_dict)``. Status must contain
    SciPy-style success(bool), status(int), message(str), nit/nfev (int). A
    callback or numeric exception aborts without inventing an optimizer status
    or trying a recovery. Returned stage records retain input/output and warm
    start predecessor, even if the v2 run aborts partway through an attempt.
    ``source_provenance`` is caller-supplied source revision/dirty patch metadata;
    missing metadata is explicitly not supplied, never inferred as clean.
    This API runs one start only; no EXP storage, multistart or dense checks.
    """
    if not callable(optimize_stage):
        raise TypeError("optimize_stage must be callable")
    if source_provenance is not None:
        if not isinstance(source_provenance, dict):
            raise TypeError("source_provenance must be a dict")
        json.dumps(source_provenance, allow_nan=False)
    coarse = SampledEpigraph(circuit, coarse_points)
    fine = SampledEpigraph(circuit, fine_points)
    if not isinstance(seed_record, dict):
        raise TypeError("Expected C1 seed record")
    replay = coarse.seed(seed_record["input_vector"], policy_id=seed_record["policy_id"],
        policy_fingerprint=seed_record["policy_fingerprint"],
        definition_sha256=seed_record["definition_sha256"],
        input_sha256=seed_record["input_vector_sha256"], seed=seed_record["seed"],
        jitter_fraction=seed_record["jitter_fraction"])
    if (json.dumps(replay, sort_keys=True, allow_nan=False) !=
            json.dumps(seed_record, sort_keys=True, allow_nan=False)):
        raise ValueError("Seed record does not match C1 deterministic replay")
    initial = np.asarray(replay["vector"], dtype=float)
    csha = definition_fingerprint(circuit.definition)
    policy = circuit.resolved_policy
    record = {"schema": "c1-staged-v2-record-1", "iteration_policy_id": TERMINATION_AWARE_POLICY_ID,
        "seed": deepcopy(replay), "policy_id": circuit.policy_id,
        "policy_fingerprint": circuit.policy_fingerprint, "definition_sha256": csha,
        "definition": asdict(circuit.definition),
        "budget": {**STANDARD_SLSQP_BUDGET.as_dict(), "policy_id": TERMINATION_AWARE_POLICY_ID},
        "bands_file": policy["bands_file"],
        "bands_sha256": hashlib.sha256(rf_input_file(ROOT, policy["bands_file"]).read_bytes()).hexdigest(),
        "s2p_sha256": {k: policy["external_port_parasitics"][k]["sha256"]
                       for k in ("input_parasitic", "output_parasitic")},
        "grids": {"coarse": _grid(coarse), "fine": _grid(fine)},
        "source_provenance": {"state": "provided", "value": deepcopy(source_provenance)}
                             if source_provenance is not None else {"state": "not_supplied"},
        "environment": {"python": sys.version, "platform": platform.platform(),
                        "numpy": np.__version__, "scipy": scipy.__version__},
        "stage_calls": [], "attempts": [], "controller": None,
        "numerical_state": "not_run", "exception": None,
        "validation": {"independent_mna": "not_run", "power_balance": "not_run",
                       "dense_rf": "not_run", "continuous_frequency": "not_run",
                       "physical": "not_run", "owner_approval": "not_run"},
        "candidate_promotion_blocked": True, "rf_compliance_certified": False}
    calls = record["stage_calls"]
    started = time.monotonic()

    def wrapped(problem, vector, maxiter, target):
        index = len(calls)
        name = "coarse" if problem is coarse else "fine"
        x = np.asarray(vector, dtype=float).copy()
        stage = {"call_index": index, "attempt_index": 0 if index < 2 else 1,
                 "stage": name, "maxiter": maxiter,
                 "grid": record["grids"][name], "input_vector": x.tolist(),
                 "input_vector_sha256": vector_fingerprint(x),
                 "warm_start_source": "seed" if index == 0 else f"stage_call_{index-1}",
                 "output_vector": None, "status": None, "observation": None,
                 "exception": None, "elapsed_seconds": None}
        calls.append(stage)
        tick = time.monotonic()
        try:
            raw_vector, raw_status = optimize_stage(problem, x.copy(), maxiter, target)
            # Retain original returned values before validating the callback contract.
            output = np.asarray(raw_vector, dtype=float)
            stage["output_vector"] = _json_value(output)
            stage["status"] = _json_value(raw_status)
            if (output.shape != initial.shape or not np.all(np.isfinite(output))):
                raise ValueError("Optimizer returned wrong-sized or non-finite vector")
            if (not isinstance(raw_status, dict) or type(raw_status.get("success")) is not bool
                    or type(raw_status.get("status")) is not int
                    or not isinstance(raw_status.get("message"), str)
                    or any(type(raw_status.get(k)) is not int or raw_status[k] < 0
                           for k in ("nit", "nfev"))):
                raise ValueError("Optimizer status does not satisfy callback contract")
            if raw_status["success"] != (raw_status["status"] == 0):
                raise ValueError("Optimizer success/status contradict each other")
            stage["exit_cause"] = ("success" if raw_status["success"] else
                                   f"status_{raw_status['status']}")
            stage["observation"] = _observe(problem, output)
            if stage["observation"]["sampled_rf"]["state"] != "observed":
                raise ValueError("Stage output cannot be evaluated on its finite grid")
            status = _json_value(raw_status)
            status["converged"] = status["success"]
            status["stage_call_index"] = index
            return output.copy(), status
        except Exception as exc:
            stage["exception"] = _error(exc)
            raise _StageAbort(str(exc)) from exc
        finally:
            stage["elapsed_seconds"] = time.monotonic() - tick

    try:
        result = run_termination_aware_slsqp(coarse, fine, initial, None, wrapped)
        record["controller"] = {k: deepcopy(v) for k, v in result.items() if k != "attempts"}
        for attempt in result["attempts"]:
            item = deepcopy(attempt)
            item["vector"] = np.asarray(item["vector"], float).tolist()
            record["attempts"].append(item)
        record["numerical_state"] = "converged" if result["attempts"][-1]["converged"] else "not_converged"
    except _StageAbort as exc:
        record["numerical_state"] = "failed"
        record["exception"] = _error(exc.__cause__ or exc)
        # The controller cannot return attempt metadata on an exception. Keep
        # all completed and interrupted calls grouped, without inventing a
        # controller decision or claiming convergence of an incomplete pair.
        for attempt_index in range(1 + (len(calls) > 2)):
            group = [s for s in calls if s["attempt_index"] == attempt_index]
            record["attempts"].append({"tier": "controller_not_returned",
                "stage_call_indices": [s["call_index"] for s in group],
                "state": "interrupted" if any(s["exception"] for s in group)
                         or len(group) < 2 else "completed_unclassified"})
    finally:
        record["elapsed_seconds"] = time.monotonic() - started
    return record
