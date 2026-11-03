"""Stage-3 C2: C1 problem / v2 budget boundary and in-memory audit record.

Calling this module is not authorization to run a scientific experiment. It
never writes historical evidence or performs dense / independent validation.
Each stage's optimizer is injectable; the v2 controller is the sole retry
policy. Numerical convergence, sampled RF observations, component checks and
candidate promotion are explicitly separate.
"""
from contextlib import nullcontext
from functools import partial
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import math
import platform
import re
import sys
import time

import numpy as np
import scipy
from scipy.optimize import minimize

from lpf.slsqp_budget import (run_termination_aware_slsqp, TERMINATION_AWARE_POLICY_ID,
                              STANDARD_SLSQP_BUDGET)
from lpf.constraint_versions import rf_input_file
from ._grid import ROOT
from .problem_seed import definition_fingerprint, vector_fingerprint, VectorBox
from .sampled_epigraph import SampledEpigraph
from .evaluation_cost import SampleBudgetExceeded


def scipy_slsqp_stage(problem, vector, maxiter, target, *,
                      coordinates="physical", finite_difference_eps=None, cost_meter=None):
    """Single C1 constrained stage; scheduling and validation live elsewhere.

    ``target`` is unused: the mandatory limit is bound to the resolved policy,
    not a caller-selected replacement. Bounds include open-bound closures;
    component validation must reject excluded boundary points afterwards.
    Explicit opt-in via functools.partial(..., coordinates="normalized"); the
    callback still accepts/returns the full physical vector, so v2 and saved
    vector SHAs remain physical. This path rejects excluded open endpoints
    rather than repairing them. Optional absolute finite_difference_eps is a
    comparison setting, not a production default; ftol is never overridden.
    Optional EvaluationCost measures actual forward and solver callback events
    without caching or extra checks. Use a fresh meter per stage; a supplied
    meter remains inspectable on failure. Its snapshot excludes subsequent
    C2 observations / validation. The default API/output remains unchanged.
    """
    if target is not None:
        raise ValueError("RF target override is not supported")
    if coordinates not in ("physical", "normalized"):
        raise ValueError("Unknown coordinate system")
    if finite_difference_eps is not None and (
            not np.isscalar(finite_difference_eps)
            or not np.isfinite(finite_difference_eps) or finite_difference_eps <= 0):
        raise ValueError("finite_difference_eps must be finite and positive")
    options = {"maxiter": maxiter}
    if finite_difference_eps is not None:
        options["eps"] = float(finite_difference_eps)
    original = np.asarray(vector, float)
    with cost_meter.timed() if cost_meter is not None else nullcontext():
        if cost_meter is not None:
            problem = cost_meter.epigraph(problem)
        if coordinates == "normalized":
            from .normalized_epigraph import NormalizedEpigraph
            problem = NormalizedEpigraph(problem)
            original = problem.to_normalized(original)
        objective, residuals = problem.objective, problem.residuals
        if cost_meter is not None:
            objective = cost_meter.callback(objective)
            residuals = cost_meter.callback(residuals, constraint=True)
        result = minimize(objective, original, method="SLSQP",
            bounds=problem.box.bounds, constraints=({"type": "ineq", "fun": residuals},),
            options=options)
        output = problem.to_physical(result.x) if coordinates == "normalized" else result.x
    state = {"success": bool(result.success), "status": int(result.status),
             "message": str(result.message), "nit": int(result.nit),
             "nfev": int(result.nfev)}
    if cost_meter is not None:
        state["evaluation_cost"] = cost_meter.snapshot()
    if coordinates == "normalized" or finite_difference_eps is not None:
        state["coordinate_configuration"] = {
            "coordinates": coordinates, "epigraph_units": "dB",
            "finite_difference_eps": finite_difference_eps,
            "eps_units": "physical" if coordinates == "physical" else "unit_box_and_t_db",
            "ftol": "scipy_default_unchanged"}
    return output, state


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
            role = problem.evaluator.role
            if problem.search_stop_db is None:
                il = problem.evaluator.il(x)
                if not np.all(np.isfinite(il)):
                    raise ValueError("Non-finite RF observation")
                residual = vector[-1] - il[role == 0]
                pass_residual = residual
                h2_residual = h3_residual = None
                min_h2 = float(np.min(il[role == 1]))
                min_h3 = float(np.min(il[role == 2]))
            else:
                residual = problem.residuals(vector)
                if not np.all(np.isfinite(residual)):
                    raise ValueError("Non-finite RF residual")
                pass_residual = residual[role == 0]
                h2_residual = float(np.min(residual[role == 1]))
                h3_residual = float(np.min(residual[role == 2]))
                min_h2 = float(problem.search_stop_db + h2_residual)
                min_h3 = float(problem.search_stop_db + h3_residual)
            result["sampled_rf"] = {
                "state": "observed", "residuals_db": residual.tolist(),
                "minimum_residual_db": float(np.min(residual)),
                "passband_epigraph_min_residual_db": float(np.min(pass_residual)),
                "h2_min_residual_db": h2_residual,
                "h3_min_residual_db": h3_residual,
                "worst_il_db": float(vector[-1] - np.min(pass_residual)),
                "min_h2_db": min_h2,
                "min_h3_db": min_h3,
                "all_sampled_inequalities_nonnegative": bool(np.all(residual >= 0)),
            }
        except SampleBudgetExceeded:
            raise
        except Exception as exc:
            result["sampled_rf"] = {"state": "error", "error": _error(exc)}
    except SampleBudgetExceeded:
        raise
    except Exception as exc:
        result["input_error"] = _error(exc)
    return result


class _StageAbort(Exception):
    """Stop v2 safely on numerical/callback failure; retain recorded calls."""


def _check_guard_source(source_provenance):
    if not isinstance(source_provenance, dict):
        raise ValueError('Guarded search requires explicit source provenance')
    for name, length in (('git_head', 40), ('dirty_patch_sha256', 64), ('input_source_sha256', 64)):
        value = source_provenance.get(name)
        if not isinstance(value, str) or re.fullmatch(r'[0-9a-f]{' + str(length) + r'}', value) is None:
            raise ValueError('Guarded search requires explicit source ' + name)
    if source_provenance.get('kind') not in ('synthetic', 'frozen', 'recorded'):
        raise ValueError('Guarded search requires source provenance kind')


def run_c1_staged(circuit, seed_record, *, coarse_points, fine_points,
                  optimize_stage=scipy_slsqp_stage, source_provenance=None, record_sink=None,
                  cost_meter=None, extra_frequencies=(), warm_start_vector=None,
                  search_guard=False, working_configuration=None,
                  require_legal_output=False):
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
    ``record_sink``, when supplied, receives snapshots before dispatch and after
    every stage (including interruption), then the final record. Sink failures
    propagate: callers must not claim durable preservation after a write fails.
    Optional cost_meter covers seed replay, all solver forwards and post-stage
    observations, using one shared meter across v2 recovery stages. Supply a
    fresh SampleBudgetCost for a per-start hard requested-sample ceiling.
    Budget exhaustion is saved separately from solver status/nonconvergence;
    no recovery is attempted. Injected test optimizers receive a metered view.
    working_configuration explicitly sets selected settings, a search-only
    stop_db (None means IL-only) and fixed_indices. It requires a warm start,
    reseeds t on the selected coarse passband, and rejects illegal outputs.
    This API runs one start only; no EXP storage, multistart or dense checks.
    """
    if not callable(optimize_stage):
        raise TypeError("optimize_stage must be callable")
    if type(search_guard) is not bool or type(require_legal_output) is not bool:
        raise TypeError("search_guard and require_legal_output must be bool")
    if source_provenance is not None:
        if not isinstance(source_provenance, dict):
            raise TypeError("source_provenance must be a dict")
        json.dumps(source_provenance, allow_nan=False)
    if search_guard:
        _check_guard_source(source_provenance)
    extra_frequencies = tuple(extra_frequencies)
    seed_problem = SampledEpigraph(circuit, coarse_points)
    working = {}
    fixed_indices = ()
    if working_configuration is not None:
        if (not isinstance(working_configuration, dict) or
                set(working_configuration) != {"settings", "stop_db", "fixed_indices"} or
                search_guard or extra_frequencies or warm_start_vector is None):
            raise ValueError("Invalid working configuration or missing warm start")
        working = {"settings": working_configuration["settings"],
                   "working_stop_db": working_configuration["stop_db"]}
        fixed_indices = working_configuration["fixed_indices"]
        if (not isinstance(fixed_indices, (tuple, list)) or
                any(type(i) is not int or not 0 <= i < circuit.schema.vector_length
                    for i in fixed_indices) or len(set(fixed_indices)) != len(fixed_indices)):
            raise ValueError("Invalid fixed physical indices")
    coarse = (SampledEpigraph(circuit, coarse_points, extra_frequencies=extra_frequencies,
                              search_guard=search_guard, **working)
              if extra_frequencies or search_guard or working else seed_problem)
    fine = SampledEpigraph(circuit, fine_points, extra_frequencies=extra_frequencies,
                           search_guard=search_guard, **working)
    if not isinstance(seed_record, dict):
        raise TypeError("Expected C1 seed record")
    replay_problem = cost_meter.epigraph(seed_problem) if cost_meter is not None else seed_problem
    with cost_meter.timed() if cost_meter is not None else nullcontext():
        replay = replay_problem.seed(seed_record["input_vector"], policy_id=seed_record["policy_id"],
            policy_fingerprint=seed_record["policy_fingerprint"],
            definition_sha256=seed_record["definition_sha256"],
            input_sha256=seed_record["input_vector_sha256"], seed=seed_record["seed"],
            jitter_fraction=seed_record["jitter_fraction"])
    if (json.dumps(replay, sort_keys=True, allow_nan=False) !=
            json.dumps(seed_record, sort_keys=True, allow_nan=False)):
        raise ValueError("Seed record does not match C1 deterministic replay")
    initial = np.asarray(replay["vector"], dtype=float)
    if warm_start_vector is not None:
        initial = np.asarray(warm_start_vector, dtype=float).copy()
        x, _ = coarse._split(initial)
        circuit.validate_components(x)
        if any((lo is not None and v < lo) or (hi is not None and v > hi)
               for v, (lo, hi) in zip(initial, coarse.box.bounds)) or any(
                   initial[i] <= coarse.box.bounds[i][0] for i in coarse.box.open_lower):
            raise ValueError('Warm start outside component or epigraph box')
    if working_configuration is not None:
        # Fix only physical coordinates; the epigraph is always free and reseeded.
        for problem in (coarse, fine):
            bounds = list(problem.box.bounds)
            for i in fixed_indices:
                bounds[i] = (float(initial[i]), float(initial[i]))
            # A fixed value was already checked against the original open bound;
            # its equality box must not itself be treated as an open endpoint.
            problem.box = VectorBox(tuple(bounds), tuple(
                i for i in problem.box.open_lower if i not in fixed_indices))
        measured = cost_meter.epigraph(coarse) if cost_meter is not None else coarse
        with cost_meter.timed() if cost_meter is not None else nullcontext():
            il = measured.evaluator.il(initial[:-1])
        initial[-1] = float(np.max(il[measured.evaluator.role == 0]))
        if not np.isfinite(initial[-1]):
            raise ValueError("Non-finite warm-start passband IL")
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
    if working_configuration is not None:
        record['working_configuration'] = deepcopy(working_configuration)
        record['working_initial_vector'] = initial.tolist()
    if search_guard:
        record['search_guard'] = {'guard_db': coarse.search_guard_db,
                                  'mandatory_stop_db': coarse.mandatory_stop_db,
                                  'search_stop_db': coarse.search_stop_db}
    if extra_frequencies or warm_start_vector is not None:
        record['frequency_exchange_input'] = {
            'extra_frequencies': [list(point) for point in extra_frequencies],
            'warm_start_vector': initial.tolist()}
    calls = record["stage_calls"]
    started = time.monotonic()

    def persist():
        if cost_meter is not None:
            record["evaluation_cost"] = cost_meter.snapshot()
            if hasattr(cost_meter, "max_samples"):
                record["max_frequency_samples_requested"] = cost_meter.max_samples
        if record_sink is not None:
            record_sink(deepcopy(record))

    persist()

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
        persist()
        tick = time.monotonic()
        before_cost = cost_meter.snapshot() if cost_meter is not None else None
        try:
            if cost_meter is not None and (optimize_stage is scipy_slsqp_stage or
                    (isinstance(optimize_stage, partial) and optimize_stage.func is scipy_slsqp_stage)):
                raw_vector, raw_status = optimize_stage(
                    problem, x.copy(), maxiter, target, cost_meter=cost_meter)
            elif cost_meter is not None:
                with cost_meter.timed():
                    raw_vector, raw_status = optimize_stage(
                        cost_meter.epigraph(problem), x.copy(), maxiter, target)
            else:
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
            if cost_meter is not None:
                with cost_meter.timed():
                    stage["observation"] = _observe(cost_meter.epigraph(problem), output)
            else:
                stage["observation"] = _observe(problem, output)
            if stage["observation"]["sampled_rf"]["state"] != "observed":
                raise ValueError("Stage output cannot be evaluated on its finite grid")
            if working_configuration is not None or require_legal_output:
                component = stage["observation"]["component_policy"]
                detail = component.get("detail", {})
                if (stage["observation"]["box"]["state"] != "pass" or
                        component["state"] != "pass" or
                        detail.get("component_policy_pass") is False or
                        detail.get("connection_role_evidence_incomplete") is True):
                    raise ValueError("Working stage returned an illegal physical vector")
            status = _json_value(raw_status)
            status["converged"] = status["success"]
            status["stage_call_index"] = index
            return output.copy(), status
        except Exception as exc:
            stage["exception"] = _error(exc)
            raise _StageAbort(str(exc)) from exc
        finally:
            stage["elapsed_seconds"] = time.monotonic() - tick
            if cost_meter is not None:
                stage["evaluation_cost"] = {
                    k: v - before_cost[k] for k, v in cost_meter.snapshot().items()}
            persist()

    try:
        result = run_termination_aware_slsqp(coarse, fine, initial, None, wrapped)
        record["controller"] = {k: deepcopy(v) for k, v in result.items() if k != "attempts"}
        for attempt in result["attempts"]:
            item = deepcopy(attempt)
            item["vector"] = np.asarray(item["vector"], float).tolist()
            record["attempts"].append(item)
        record["numerical_state"] = "converged" if result["attempts"][-1]["converged"] else "not_converged"
    except _StageAbort as exc:
        record["numerical_state"] = (
            "budget_exhausted" if isinstance(exc.__cause__, SampleBudgetExceeded) else "failed")
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
        persist()
    return record


def run_c1_continuation(circuit, seed_record, *, method, cost_meter, source_provenance,
                        optimize_stage=scipy_slsqp_stage, record_sink=None):
    """Opt-in A/B/C/D control over existing v2 and final guarded exchange.

    This is an in-memory search control, not an experiment/storage runner.
    A caller must provide the same per-start budget and a durable sink. Each
    intermediate stage stops on nonconvergence or an invalid physical result.
    """
    from ._grid import CASES
    from .evaluation_cost import SampleBudgetCost
    from .frequency_exchange_c1 import run_c1_frequency_exchange

    if method not in ('A', 'B', 'C', 'D'):
        raise ValueError('Unknown continuation method')
    if not isinstance(cost_meter, SampleBudgetCost):
        raise TypeError('A shared sample budget is required')
    if not callable(record_sink):
        raise TypeError('A record sink is required')
    _check_guard_source(source_provenance)
    nv = circuit.schema.n_variable
    if method in ('C', 'D') and nv != 2:
        raise ValueError('Band staging requires exactly two variable-C branches')
    v = np.asarray(seed_record['vector'], dtype=float).copy()
    if v.shape != (circuit.schema.vector_length + 1,) or not np.all(np.isfinite(v)):
        raise ValueError('Expected complete initial physical vector and epigraph')
    initial_component = circuit.validate_components(v[:-1])
    if (initial_component.get('component_policy_pass') is False or
            initial_component.get('connection_role_evidence_incomplete') is True):
        raise ValueError('Initial component or connection-role validation failed')
    result = {'method': method, 'state': 'running', 'stages': [],
              'last_valid_vector': v.tolist(), 'final_exchange': None,
              'rf_compliance_certified': False, 'final_validation': 'not_run'}

    class SinkFailure(Exception):
        pass

    sink_failure = None
    def persist():
        nonlocal sink_failure
        result['evaluation_cost'] = cost_meter.snapshot()
        try:
            record_sink(deepcopy(result))
        except Exception as exc:
            sink_failure = exc
            raise SinkFailure('Continuation record sink failed') from exc

    def cv_indices(case):
        first = circuit.schema.vector_length - len(CASES) * nv + CASES.index(case) * nv
        return tuple(range(first, first + nv))

    def retain_valid_stage(snapshot):
        calls = snapshot.get('stage_calls', [])
        if not calls:
            return
        call = calls[-1]
        observation = call.get('observation') or {}
        component = observation.get('component_policy') or {}
        detail = component.get('detail') or {}
        if (call.get('output_vector') is not None and call.get('exception') is None and
                observation.get('sampled_rf', {}).get('state') == 'observed' and
                observation.get('box', {}).get('state') == 'pass' and
                component.get('state') == 'pass' and
                detail.get('component_policy_pass') is True and
                detail.get('connection_role_evidence_incomplete') is False):
            result['last_valid_vector'] = deepcopy(call['output_vector'])

    def stage(label, settings, threshold, fixed):
        nonlocal v
        item = {'label': label, 'input_vector': v.tolist(), 'record': None}
        result['stages'].append(item)
        persist()
        def stage_snapshot(snapshot):
            item['record'] = snapshot
            retain_valid_stage(snapshot)
            persist()
        record = run_c1_staged(circuit, seed_record, coarse_points=2, fine_points=3,
            optimize_stage=optimize_stage, source_provenance=source_provenance,
            cost_meter=cost_meter, record_sink=stage_snapshot, warm_start_vector=v,
            working_configuration={'settings': list(settings), 'stop_db': threshold,
                                   'fixed_indices': list(fixed)})
        item['record'] = record
        if record['numerical_state'] != 'converged':
            result['state'] = record['numerical_state']
            result['exception'] = deepcopy(record['exception'])
            persist()
            return False
        v = np.asarray(record['stage_calls'][-1]['output_vector'], dtype=float)
        result['last_valid_vector'] = v.tolist()
        persist()
        return True

    persist()
    try:
        if method in ('C', 'D'):
            # Explicit experimental intervention, not a component repair.
            v[list(cv_indices('B8'))] = 0.
            circuit.validate_components(v[:-1])
            result['b8_initial_zero_vector'] = v.tolist()
            result['last_valid_vector'] = v.tolist()
            persist()
            inactive = [i for case in CASES for i in cv_indices(case)]
            if not stage('B8_il_only', ('B8',), None, inactive):
                return result
            active = ['B8']
            for new_cases in (('B71',), tuple(case for case in CASES if case not in ('B8', 'B71'))):
                for case in new_cases:
                    # Only the new setting's Cv may move in this local adjustment.
                    fixed = [i for i in range(circuit.schema.vector_length) if i not in cv_indices(case)]
                    if not stage('adjust_' + case, (case,), None, fixed):
                        return result
                    active.append(case)
                fixed = [i for case in CASES if case not in active for i in cv_indices(case)]
                if len(active) < len(CASES):
                    fixed.extend(cv_indices('B8'))
                if not stage('bands_' + '+'.join(active) + '_il_only', active, None, fixed):
                    return result
        elif method == 'B':
            if not stage('all_il_only', CASES, None, ()):
                return result
        if method in ('B', 'D'):
            for threshold in (10., 20., 25., 28.):
                if not stage('all_' + str(threshold), CASES, threshold, ()):
                    return result
        # Final exchange starts at the previous physical vector, with a fresh t
        # on the all-setting coarse grid. All costs share the original meter.
        final_problem = cost_meter.epigraph(SampledEpigraph(circuit, 2))
        with cost_meter.timed():
            values = final_problem.evaluator.il(v[:-1])
        v[-1] = float(np.max(values[final_problem.evaluator.role == 0]))
        if not np.isfinite(v[-1]):
            raise ValueError('Non-finite final passband seed')
        result['final_initial_vector'] = v.tolist()
        persist()
        def exchange_snapshot(snapshot):
            result['final_exchange'] = snapshot
            persist()
        def final_stage_snapshot(snapshot):
            result['final_stage'] = snapshot
            retain_valid_stage(snapshot)
            persist()
        exchange = run_c1_frequency_exchange(circuit, seed_record, cost_meter=cost_meter,
            optimize_stage=optimize_stage, source_provenance=source_provenance,
            exchange_sink=exchange_snapshot, stage_sink=final_stage_snapshot,
            search_guard=True, warm_start_vector=v)
        result['final_exchange'] = exchange
        result['state'] = ('budget_exhausted' if exchange['stop_reason'] == 'budget_exhausted'
                           else 'completed')
        if result['state'] == 'completed' and exchange.get('final_vector') is not None:
            result['last_valid_vector'] = exchange['final_vector']
    except SinkFailure:
        raise
    except SampleBudgetExceeded as exc:
        result['state'] = 'budget_exhausted'
        result['exception'] = _error(exc)
    except Exception as exc:
        if sink_failure is not None:
            raise SinkFailure('Continuation record sink failed') from sink_failure
        result['state'] = 'failed'
        result['exception'] = _error(exc)
    persist()
    return result
