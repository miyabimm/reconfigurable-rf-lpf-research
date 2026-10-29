"""S4B in-memory candidate records and like-for-like finite-grid Pareto.

No optimizer, storage runner or dense scan is supplied. JSON is evidence to
inspect, not authenticated PASS: deserialization alone never enables ranking.
Explicit recheck repeats the existing limited audit when it was requested.
Convergence is a consistency-checked *reported optimizer state*, not a proof
that SciPy actually ran or that a candidate satisfies RF/physical requirements.
"""
from collections import defaultdict
from dataclasses import asdict, dataclass, field
import json
import math

import numpy as np

from lpf.constraint_versions import load_constraint
from .api import CircuitDefinition, build_nominal_circuit
from .candidate_audit import audit_candidate
from .circuit_layout import CapacitorPlacement, InductorTree
from .limited_candidate_evidence import _identity, compare_recomputed_evidence
from .problem_seed import definition_fingerprint, vector_fingerprint
from .sampled_epigraph import SampledEpigraph
from .staged_optimization import run_c1_staged, _grid
from .topology_enumeration import exact_candidate_key, nominal_area


SCHEMA = "s4b-candidate-record-v1"
_VALIDATION = ("independent_mna", "power_balance", "dense_rf",
               "continuous_frequency", "physical", "owner_approval")


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _copy(value):
    return json.loads(_json(value))


def _without_timing(value):
    if isinstance(value, dict):
        return {k: _without_timing(v) for k, v in value.items() if k != "elapsed_seconds"}
    if isinstance(value, list):
        return [_without_timing(v) for v in value]
    return value


def _points(value):
    if value is not None and (type(value) is not int or value not in (1, 2, 3)):
        raise ValueError("Only explicit 1/2/3-point diagnostic grids supported")


def _provenance(value):
    if value is None:
        return {"state": "not_supplied"}
    if not isinstance(value, dict):
        raise ValueError("Source provenance must be a dictionary")
    for name, length in (("git_head", 40), ("dirty_patch_sha256", 64), ("input_source_sha256", 64)):
        text = value.get(name)
        if not isinstance(text, str) or len(text) != length or any(c not in "0123456789abcdef" for c in text):
            raise ValueError("Missing/invalid source fingerprint: " + name)
    if value.get("kind") not in ("synthetic", "frozen", "recorded"):
        raise ValueError("Source kind must be synthetic/frozen/recorded")
    return {"state": "provided", "value": _copy(value)}


def _seed(circuit, saved):
    _points(saved["points_per_interval"])
    p = SampledEpigraph(circuit, saved["points_per_interval"])
    actual = p.seed(saved["input_vector"], policy_id=saved["policy_id"],
        policy_fingerprint=saved["policy_fingerprint"],
        definition_sha256=saved["definition_sha256"],
        input_sha256=saved["input_vector_sha256"], seed=saved["seed"],
        jitter_fraction=saved["jitter_fraction"])
    if _copy(actual) != saved:
        raise ValueError("C1 seed replay mismatch")


def _numerical(circuit, vector, staged, seed):
    if seed is not None:
        _seed(circuit, seed)
    if staged is None:
        if seed is not None and list(vector) != seed["vector"][:-1]:
            raise ValueError("Candidate vector differs from C1 seed output")
        return {"state": "not_run", "vector_binding": "c1_seed_output" if seed else "explicit"}
    if (staged.get("schema") != "c1-staged-v2-record-1"
            or staged.get("policy_id") != circuit.policy_id
            or staged.get("policy_fingerprint") != circuit.policy_fingerprint
            or staged.get("definition_sha256") != definition_fingerprint(circuit.definition)
            or staged.get("definition") != _copy(asdict(circuit.definition))
            or staged.get("candidate_promotion_blocked") is not True
            or staged.get("rf_compliance_certified") is not False
            or staged.get("seed") != seed):
        raise ValueError("C2 record policy/definition/seed/gate mismatch")
    state = staged.get("numerical_state")
    calls = staged.get("stage_calls")
    if state not in ("converged", "not_converged", "failed") or not isinstance(calls, list) or not calls:
        raise ValueError("Incomplete C2 numerical record")
    for grid in staged["grids"].values():
        _points(grid["points_per_interval"])
    if state == "failed":
        if not staged.get("exception") or not any(c.get("exception") for c in calls):
            raise ValueError("Failed C2 state without exception evidence")
        # Failed callback output/status may itself be invalid/nonfinite (C2
        # stores strings such as 'nan'). Preserve it, never rank it as success.
        return {"state": state, "vector_binding": "failure_anchor_not_final_output",
                "consistency": "failure_diagnostics_preserved_not_replayed"}
    if staged.get("exception") is not None or any(c.get("exception") for c in calls):
        raise ValueError("Successful/completed C2 record contradicts exception")
    if list(vector) != calls[-1]["output_vector"][:-1]:
        raise ValueError("Candidate vector differs from final C2 output")
    index = 0
    def replay(problem, x, maxiter, target):
        nonlocal index
        if index >= len(calls):
            raise ValueError("Missing C2 replay call")
        old = calls[index]
        index += 1
        if old["input_vector"] != x.tolist() or old["maxiter"] != maxiter:
            raise ValueError("C2 input/budget replay mismatch")
        return np.asarray(old["output_vector"], float), old["status"]
    source = staged["source_provenance"]
    actual = run_c1_staged(circuit, seed,
        coarse_points=staged["grids"]["coarse"]["points_per_interval"],
        fine_points=staged["grids"]["fine"]["points_per_interval"], optimize_stage=replay,
        source_provenance=source["value"] if source["state"] == "provided" else None)
    # Reuse the existing v2 controller and C1 observations, not a second set of
    # retry/status/epigraph rules. Timing/environment of the saved run are kept.
    keys = ("iteration_policy_id", "budget", "seed", "bands_sha256", "s2p_sha256",
            "grids", "stage_calls", "attempts", "controller", "numerical_state", "validation")
    if index != len(calls) or any(_without_timing(_copy(actual[k])) != _without_timing(staged[k]) for k in keys):
        raise ValueError("C2 status/attempt/observation replay mismatch")
    return {"state": state, "vector_binding": "final_c2_output",
            "meaning": "reported_optimizer_status_consistent_with_v2; not_solver_attestation"}


def _context(circuit):
    p = circuit.resolved_policy
    return {"objective": "full_lpf_worst_six_setting_UL_DL_external_port_IL",
            "reference_planes": "external_input_to_external_output",
            "thresholds": p["evaluation"]["full_phase2"], "finite_grid_only": True}


@dataclass(frozen=True)
class CandidateRecord:
    """Immutable JSON snapshot; fresh checks are intentionally not serialized.

    This is not a security/signature boundary. The transient flag just prevents
    treating read-back caller-supplied observations as independently verified.
    """
    _json_text: str
    _rechecked: bool = field(default=False, repr=False, compare=False)

    def to_json(self):
        return self._json_text

    def as_dict(self):
        return json.loads(self._json_text)

    @classmethod
    def from_json(cls, text):
        def invalid_constant(value):
            raise ValueError("Non-finite JSON number: " + value)
        def unique_fields(pairs):
            result = {}
            for k, v in pairs:
                if k in result:
                    raise ValueError("Duplicate JSON field: " + k)
                result[k] = v
            return result
        body = json.loads(text, parse_constant=invalid_constant, object_pairs_hook=unique_fields)
        _validate_payload(body)
        return cls(_json(body))


def _circuit(body):
    d = dict(body["definition"])
    d["inductor_tree"] = InductorTree(**d["inductor_tree"])
    d["capacitor_placement"] = CapacitorPlacement(**d["capacitor_placement"])
    return build_nominal_circuit(load_constraint(body["policy_id"], allow_trial=True), CircuitDefinition(**d))


def _validate_payload(b):
    fields = {"schema", "candidate_id", "policy_id", "policy_sha256", "definition",
              "definition_sha256", "vector", "vector_sha256", "values", "topology_key", "vector_key",
              "parameter_schema", "stamped_topology",
              "nominal_area", "identity", "source_provenance", "context", "numerical", "seed_record",
              "staged_record", "component", "rf", "validation", "audit", "candidate_promotion_blocked",
              "rf_compliance_certified"}
    if (not isinstance(b, dict) or set(b) != fields or b["schema"] != SCHEMA
            or not isinstance(b["candidate_id"], str) or not b["candidate_id"]
            or b["candidate_promotion_blocked"] is not True or b["rf_compliance_certified"] is not False
            or any(b["validation"].get(k) != "not_run" for k in _VALIDATION[2:])):
        raise ValueError("Incomplete record schema or unsupported promotion/validation claim")
    c = _circuit(b)
    values = c.decode(b["vector"])
    if (b["policy_sha256"] != c.policy_fingerprint
            or b["definition_sha256"] != definition_fingerprint(c.definition)
            or b["vector_sha256"] != vector_fingerprint(b["vector"])
            or b["values"] != _copy(asdict(values))
            or b["parameter_schema"] != _copy(asdict(c.schema))
            or b["stamped_topology"] != _copy(asdict(c.topology))
            or b["context"] != _context(c)
            or b["topology_key"] != exact_candidate_key(c)
            or b["vector_key"] != exact_candidate_key(c, b["vector"])
            or b["nominal_area"] != _copy(nominal_area(c))):
        raise ValueError("Record policy/vector/structure/area/context mismatch")
    if (set(b["validation"]) != set(_VALIDATION)
            or b["numerical"].get("state") not in ("not_run", "converged", "not_converged", "failed")
            or b["component"].get("state") not in ("pass", "fail")
            or b["rf"].get("state") not in ("not_run", "observed", "error")):
        raise ValueError("Unknown/incomplete observation state")
    expected_numerical = b["staged_record"]["numerical_state"] if b["staged_record"] else "not_run"
    if b["numerical"]["state"] != expected_numerical:
        raise ValueError("Contradictory numerical states")
    rf = b["rf"]
    _points(rf["requested_sampled_points"])
    lp = rf["requested_limited_points"]
    if lp is not None and (type(lp) is not int or lp not in (2, 3)):
        raise ValueError("Unsupported limited evidence depth")
    expected_independent = "not_run" if lp is None else (
        "passed_limited" if b["audit"] and b["audit"].get("limited_evidence") else "failed")
    if any(b["validation"][k] != expected_independent for k in _VALIDATION[:2]):
        raise ValueError("Independent validation claim without bound evidence")
    if rf["state"] == "observed":
        points = lp or rf["requested_sampled_points"]
        if points is None or rf["grid"]["points_per_interval"] != points or (
                rf["grid"]["sample_count"] != 28*points or rf["grid"]["segment_count"] != 28):
            raise ValueError("Incomplete/mismatched finite grid")
        evidence_class = "limited_independent" if expected_independent == "passed_limited" else "forward_only"
        if rf["evidence_class"] != evidence_class or set(rf["metrics"]) != {"worst_il_db", "min_h2_db", "min_h3_db"}:
            raise ValueError("Incomplete metrics or contradictory evidence class")
    _json(b)  # Reject all numeric nonfinites, including non-metric fields.


def record_candidate(candidate_id, circuit, vector, *, seed_record=None, staged_record=None,
                     source_provenance=None, sampled_points=None, limited_points=None):
    """Capture a finite complete vector and existing C1/C2 records without mutation.

    Without C1/C2 input, default is component/role only; RF/MNA/power not_run.
    Seed/C2 replay includes finite forward checks; completed C2 input defaults
    the record's forward summary to its final stage grid. Forward diagnostic
    grids are restricted to 1/2/3 points per separate interval. Only
    explicit limited_points=2/3 invokes the existing independent audit. No saved
    PASS flag is accepted. A failed attempt can be attached to a finite anchor
    vector; its actual invalid output stays verbatim in staged_record.
    """
    _points(sampled_points)
    if limited_points is not None and (type(limited_points) is not int or limited_points not in (2, 3)):
        raise ValueError("Limited audit requires 2/3 points")
    if sampled_points is not None and limited_points is not None and sampled_points != limited_points:
        raise ValueError("Forward and independent grids must agree")
    # Reuse the identity gate and actual code/input hashes of limited evidence,
    # even when RF/MNA are not requested. This hashes files; it runs no solver.
    x = tuple(map(float, circuit.encode(circuit.decode(vector))))
    identity = _identity(circuit, x)
    staged = _copy(staged_record)
    seed = _copy(seed_record)
    if staged is not None:
        if seed is not None and seed != staged["seed"]:
            raise ValueError("Conflicting C1/C2 seeds")
        seed = staged["seed"]
        old = staged["source_provenance"]
        if old["state"] == "provided":
            if source_provenance is not None and _copy(source_provenance) != old["value"]:
                raise ValueError("Conflicting execution source provenance")
            source_provenance = old["value"]
    numerical = _numerical(circuit, x, staged, seed)
    if staged is not None and numerical["state"] != "failed" and sampled_points is None and limited_points is None:
        sampled_points = staged["stage_calls"][-1]["grid"]["points_per_interval"]
    source = _provenance(source_provenance)
    # Invalid components are recorded rather than losing failed candidate data.
    try:
        audit = audit_candidate(circuit, x, limited_points_per_interval=limited_points)
        component = {"state": "pass", "detail": audit["component_policy"]}
    except ValueError as exc:
        audit = None
        component = {"state": "fail", "error": {"type": type(exc).__name__, "message": str(exc)}}
    validation = dict.fromkeys(_VALIDATION, "not_run")
    rf = {"state": "not_run", "requested_sampled_points": sampled_points,
          "requested_limited_points": limited_points}
    if limited_points is not None:
        state = "passed_limited" if audit and audit["limited_evidence"] else "failed"
        validation.update(independent_mna=state, power_balance=state)
    points = limited_points or sampled_points
    if points is not None:
        try:
            problem = SampledEpigraph(circuit, points)
            grid = _grid(problem)
            independent = validation["independent_mna"] == "passed_limited"
            if independent:
                # The existing evidence already checked all forward/MNA samples
                # to 1e-9 dB and power to 1e-12 W; keep its bound observations.
                summary = audit["limited_evidence"]["summary"]
                metrics = {"worst_il_db": summary["pass_il"]["il_db"],
                           "min_h2_db": summary["H2"]["il_db"], "min_h3_db": summary["H3"]["il_db"]}
                locations = [summary[k] for k in ("pass_il", "H2", "H3")]
            else:
                summary = problem.evaluator.summary(x)
                metrics = {"worst_il_db": summary["worst_IL_db"],
                           "min_h2_db": summary["min_H2_db"], "min_h3_db": summary["min_H3_db"]}
                locations = summary["locations"]
            rf.update(state="observed", evidence_class="limited_independent" if independent else "forward_only",
                      grid=grid, metrics=metrics, locations=locations)
        except ValueError as exc:
            rf.update(state="error", error={"type": type(exc).__name__, "message": str(exc)})
    body = {"schema": SCHEMA, "candidate_id": candidate_id, "policy_id": circuit.policy_id,
            "policy_sha256": circuit.policy_fingerprint, "definition": asdict(circuit.definition),
            "definition_sha256": definition_fingerprint(circuit.definition),
            "vector": x, "vector_sha256": vector_fingerprint(x), "values": asdict(circuit.decode(x)),
            "parameter_schema": asdict(circuit.schema), "stamped_topology": asdict(circuit.topology),
            "topology_key": exact_candidate_key(circuit), "vector_key": exact_candidate_key(circuit, x),
            "nominal_area": nominal_area(circuit), "identity": identity,
            "source_provenance": source, "context": _context(circuit), "numerical": numerical,
            "seed_record": seed, "staged_record": staged, "component": component,
            "rf": rf, "validation": validation, "audit": audit,
            "candidate_promotion_blocked": True, "rf_compliance_certified": False}
    if _identity(circuit, x) != identity:
        raise ValueError("Source/input identity changed during candidate recording")
    body = _copy(body)
    _validate_payload(body)
    return CandidateRecord(_json(body), True)


def recheck_record(record):
    """Recompute observations; saved metrics/evidence cannot supply PASS.

    Identical source/input context is required. Changed source/HEAD is a new
    observation, not a retrospective rewrite of saved evidence. For changed
    context call record_candidate separately and keep the original record.
    """
    b = record.as_dict()
    _validate_payload(b)
    c = _circuit(b)
    fresh = record_candidate(b["candidate_id"], c, b["vector"], seed_record=b["seed_record"],
        staged_record=b["staged_record"], source_provenance=b["source_provenance"].get("value"),
        sampled_points=b["rf"]["requested_sampled_points"], limited_points=b["rf"]["requested_limited_points"])
    if b["audit"] and b["audit"].get("limited_evidence"):
        actual_audit = fresh.as_dict()["audit"]
        if not actual_audit or actual_audit.get("limited_evidence") is None:
            raise ValueError("Limited evidence failed during record recheck")
        compare_recomputed_evidence(b["audit"]["limited_evidence"], actual_audit["limited_evidence"])
    if fresh.as_dict() != b:
        raise ValueError("Saved record differs from fresh recomputation")
    return fresh


def _classification(record):
    b = record.as_dict()
    _validate_payload(b)
    reasons = []
    if not record._rechecked:
        reasons.append("serialized_evidence_not_rechecked")
    if b["source_provenance"]["state"] != "provided":
        reasons.append("source_provenance_missing")
    if b["staged_record"] and b["staged_record"]["source_provenance"]["state"] != "provided":
        reasons.append("execution_provenance_missing")
    if b["numerical"]["state"] != "converged":
        reasons.append("numerical_" + b["numerical"]["state"])
    elif b["staged_record"]:
        # C2 replay checks reported status consistency, not feasibility. Use
        # its final output/grid, not t as the Pareto IL or an earlier attempt.
        sampled = b["staged_record"]["stage_calls"][-1]["observation"]["sampled_rf"]
        if sampled["state"] != "observed":
            reasons.append("final_c2_epigraph_not_verified")
        elif not sampled["passband_epigraph_min_residual_db"] >= 0:
            reasons.append("final_c2_epigraph_inequality_failed_on_grid")
    optimizer_kind = b["source_provenance"].get("value", {}).get("optimizer_kind")
    if b["numerical"]["state"] == "converged" and optimizer_kind not in ("synthetic_callback", "reported_slsqp"):
        reasons.append("optimizer_evidence_class_missing")
    if b["component"]["state"] != "pass":
        reasons.append("component_not_verified")
    elif b["component"]["detail"]["connection_role_evidence_incomplete"]:
        reasons.append("declared_role_not_proven_by_l_tree")
    if b["rf"]["state"] != "observed":
        reasons.append("rf_" + b["rf"]["state"])
    if "failed" in b["validation"].values():
        reasons.append("independent_validation_failed")
    metrics = b["rf"].get("metrics")
    thresholds = b["context"]["thresholds"]
    observations = None
    if metrics is not None:
        if any(type(metrics.get(k)) not in (float, int) or not math.isfinite(metrics[k]) for k in
               ("worst_il_db", "min_h2_db", "min_h3_db")):
            raise ValueError("Non-finite/incomplete RF metrics")
        stop = min(metrics["min_h2_db"], metrics["min_h3_db"])
        observations = {"mandatory_harmonics_met": stop >= thresholds["minimum_h2_h3_db"],
                        "nominal_harmonics_met": stop >= thresholds["nominal_h2_h3_target_db"],
                        "nominal_il_met": metrics["worst_il_db"] <= thresholds["nominal_max_il_db"]}
        if not observations["mandatory_harmonics_met"]:
            reasons.append("mandatory_harmonics_failed_on_grid")
    key = None
    if not reasons:
        key = _json({"policy_id": b["policy_id"], "policy_sha256": b["policy_sha256"],
            "context": b["context"], "grid": b["rf"]["grid"],
            "evidence_class": b["rf"]["evidence_class"], "validation": b["validation"],
            "source_kind": b["source_provenance"]["value"]["kind"],
            "optimizer_evidence_class": optimizer_kind,
            "inputs": b["identity"]["input_sha256"],
            "source_tree_sha256": b["identity"]["source_tree_sha256"],
            "environment": b["identity"]["environment"]})
    return b, reasons, key, observations


def pareto_report(records):
    """Small area–IL non-dominance report, never a promotion decision.

    Eligibility requires consistent reported convergence and nonnegative final
    C2 passband epigraph residuals, in addition to the component/harmonic gates.
    This is a comparison of checked optimization candidates, not arbitrary
    circuits. The IL axis remains the recomputed finite-grid worst IL, never t.
    Keep equal points. Dominance means <= on both axes and < on at least one,
    as in scripts/report_research_pareto.py. Excluded records/reasons remain in
    output. Different conditions/depths have different groups, never ranks.
    """
    groups = defaultdict(list)
    rows = []
    ids = set()
    for record in records:
        b, reasons, key, observations = _classification(record)
        cid = b["candidate_id"]
        if cid in ids:
            raise ValueError("Duplicate candidate ID")
        ids.add(cid)
        row = {"candidate_id": cid, "comparison_key": key, "reasons": reasons,
               "threshold_observations": observations, "pareto_within_group": None,
               "area_units": b["nominal_area"]["area_units"],
               "metrics": b["rf"].get("metrics"), "candidate_promotion_blocked": True}
        rows.append(row)
        if key is not None:
            groups[key].append(row)
    def dominates(a, b):
        aa, ai = a["area_units"], a["metrics"]["worst_il_db"]
        ba, bi = b["area_units"], b["metrics"]["worst_il_db"]
        return aa <= ba and ai <= bi and (aa < ba or ai < bi)
    for subset in groups.values():
        for row in subset:
            row["pareto_within_group"] = not any(dominates(other, row) for other in subset)
    return {"candidates": sorted(rows, key=lambda r: r["candidate_id"]),
            "groups": [{"comparison_key": key, "front": sorted(r["candidate_id"] for r in subset
                        if r["pareto_within_group"]), "count": len(subset)}
                       for key, subset in sorted(groups.items())],
            "global_optimum_proven": False, "rf_compliance_certified": False,
            "candidate_promotion_blocked": True}
