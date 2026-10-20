"""Read immutable formal constraints and explicit trial overrides, never auto-promote trials."""
import copy
import hashlib
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "data/constraints/registry.json"


def _read(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"),
                         parse_constant=_invalid_constant)
    if not isinstance(payload, dict):
        raise ValueError(f"Constraint JSON must be an object: {path}")
    return payload


def _invalid_constant(value):
    raise ValueError(f"Non-finite JSON value: {value}")


def repository_file(root, relative):
    """Resolve a repository-local evidence path, refusing traversal and symlinks out."""
    root = Path(root).resolve()
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("Expected repository-relative file path")
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Path escapes repository")
    return path


def validate_registry(*, root=ROOT):
    """Check registered identities/approvals; never register or promote a version."""
    root = Path(root)
    registry = _read(root / "data/constraints/registry.json")
    if type(registry.get("schema_version")) is not int or registry["schema_version"] != 1:
        raise ValueError("Unsupported constraint registry schema")
    for kind, prefix in (("formal", "RF-F"), ("trial", "RF-T")):
        entries = registry.get(kind)
        if not isinstance(entries, dict):
            raise ValueError(f"Registry {kind} must be an object")
        for cid, entry in entries.items():
            if not re.fullmatch(prefix + r"[0-9]{3}", cid) or not isinstance(entry, dict):
                raise ValueError(f"Invalid {kind} registration: {cid}")
            expected = f"data/constraints/{kind}/{cid}.json"
            if entry.get("file") != expected:
                raise ValueError(f"Constraint path/identity mismatch: {cid}")
            payload = _read(repository_file(root, expected))
            if kind == "formal":
                if entry.get("state") != "approved":
                    raise ValueError(f"Formal version not approved: {cid}")
                if (payload.get("active_constraint_id") != cid or
                        payload.get("active_constraint_status") != "formal"):
                    raise ValueError("Formal snapshot identity mismatch")
                if entry.get("effective_constraint_sha256") != constraint_fingerprint(payload):
                    raise ValueError(f"Formal snapshot fingerprint mismatch: {cid}")
            else:
                if entry.get("state") not in {"proposed", "study_authorized", "rejected", "withdrawn"}:
                    raise ValueError(f"Invalid trial approval state: {cid}")
                if payload.get("constraint_id") != cid or payload.get("status") != "trial":
                    raise ValueError("Trial snapshot identity mismatch")
                base = payload.get("base_constraint_id")
                if base not in registry["formal"] or entry.get("base_constraint_id") != base:
                    raise ValueError("Trial must pin the same registered formal base in file and registry")
                if payload.get("study_authorized") is not (entry["state"] == "study_authorized"):
                    raise ValueError("Trial approval differs between file and registry")
                reserved = {"active_constraint_id", "active_constraint_status", "policy_version",
                            "trial_base_constraint_id", "phase3"}
                overrides = payload.get("overrides")
                if not isinstance(overrides, dict) or reserved.intersection(overrides):
                    raise ValueError("Trial may not override constraint identity, legacy policy or phase")
                base_payload = _read(repository_file(root, registry["formal"][base]["file"]))
                resolved = _merge(base_payload, overrides)
                if "study_additional_stopband" in payload:
                    _validate_trial_additional_stopband(
                        payload["study_additional_stopband"], base_payload)
                if "study_shunt_dtc_parasitic" in payload:
                    _validate_trial_shunt_dtc_parasitic(
                        payload["study_shunt_dtc_parasitic"], resolved)
                if "study_pcb_pattern_c_by_connection" in payload:
                    _validate_trial_pcb_pattern_c_by_connection(
                        payload["study_pcb_pattern_c_by_connection"], resolved)
                if "study_ic_fixed_c_by_connection" in payload:
                    if "study_shunt_dtc_parasitic" in payload:
                        raise ValueError("IC fixed C model replaces, not augments, old shunt DTC parasite")
                    _validate_trial_ic_fixed_c_by_connection(
                        payload["study_ic_fixed_c_by_connection"], resolved)
                if cid == "RF-T008" and (
                        "study_ic_fixed_c_by_connection" not in payload
                        or "study_shunt_dtc_parasitic" in payload):
                    raise ValueError("Revised RF-T008 must use IC fixed C instead of shunt parasitic")
                layout = payload.get("study_variable_c_layout")
                spec = resolved["components"]["IC_VARIABLE_C"]
                if not isinstance(layout, dict):
                    raise ValueError(f"Invalid trial variable-C layout: {cid}")
                if set(layout) == {"branch_count", "count_policy", "connection_policy"}:
                    if (type(layout["branch_count"]) is not int or
                            layout["branch_count"] < 1 or
                            layout["branch_count"] > spec["max_branches_principle"] or
                            layout["count_policy"] != "up_to" or
                            layout["connection_policy"] != "any_allowed"):
                        raise ValueError(f"Invalid flexible variable-C layout: {cid}")
                else:
                    expected = {"branch_count", "shunt_to_ground", "non_ground_bridge"}
                    if set(layout) != expected or any(
                        type(layout[key]) is not int or layout[key] < 0 for key in expected
                    ):
                        raise ValueError(f"Invalid trial variable-C layout: {cid}")
                    if (layout["branch_count"] != layout["shunt_to_ground"] + layout["non_ground_bridge"]
                        or layout["branch_count"] < 1
                        or layout["branch_count"] > spec["max_branches_principle"]
                        or "shunt_to_ground" not in spec["positions_allowed_by_default"]
                        or (layout["non_ground_bridge"] > 0) !=
                           ("non_ground_bridge" in spec["positions_allowed_by_default"])
                        or spec["series_requires_separate_approval"] is not True):
                        raise ValueError(f"Trial layout and allowed positions disagree: {cid}")
    if registry.get("active_formal_id") not in registry["formal"]:
        raise ValueError("Active constraint must be a registered approved formal version")
    return registry


def _validate_trial_additional_stopband(spec, base):
    """Fail closed on trial-only wideband attenuation gates and available S2P span.

    No field is added to (or mutates) the immutable formal RF-F003 snapshot.
    """
    keys = {"low_hz", "high_hz", "sample_step_hz", "include_endpoints",
            "min_attenuation_db", "settings", "metric", "reference_planes",
            "applicable_objective"}
    if not isinstance(spec, dict) or set(spec) != keys:
        raise ValueError("Invalid trial additional stopband schema")
    lo, hi, step = (spec[key] for key in ("low_hz", "high_hz", "sample_step_hz"))
    if (any(type(n) is not int for n in (lo, hi, step))
            or lo < 0 or hi <= lo or step <= 0 or (hi - lo) % step != 0):
        raise ValueError("Invalid additional stopband finite frequency grid")
    if (type(spec["min_attenuation_db"]) not in (int, float)
            or not math.isfinite(spec["min_attenuation_db"])
            or spec["min_attenuation_db"] <= 0):
        raise ValueError("Invalid additional stopband attenuation threshold")
    if (spec["settings"] != ["B71", "B12", "B28", "B13+B14", "B26", "B8"]
            or spec["include_endpoints"] is not True
            or spec["metric"] != "-10log10(Pload/Pavs)"
            or spec["reference_planes"] != "external_input_to_external_output"
            or spec["applicable_objective"] != "full_lpf"):
        raise ValueError("Invalid trial additional stopband interpretation")
    parasitics = base.get("external_port_parasitics")
    if not isinstance(parasitics, dict):
        raise ValueError("Trial additional stopband requires fixed external S2P")
    fmt = parasitics["format"]
    if (lo < fmt["f_start_hz"] or hi > fmt["f_stop_hz"]
            or step < fmt["f_step_hz"]
            or spec["reference_planes"] != parasitics["system_evaluation"]["metrics_reference_planes"]):
        raise ValueError("Trial additional stopband exceeds fixed external model range")



def _validate_trial_shunt_dtc_parasitic(spec, resolved):
    """Validate explicit nominal per-ground-shunt DTC fixed branch rules.

    This metadata is trial-specific; do not mutate the formal RF-F003 snapshot.
    """
    keys = {"applies_to", "fixed_capacitance_pf", "q", "q_model",
            "variable_capacitance_pf_range", "present_at_variable_C_zero",
            "not_applicable_to_non_ground_variable_C", "frequency_invariant",
            "setting_invariant", "pcb_pattern_C_count_increment",
            "additional_chip_area_units", "tolerance_status"}
    if not isinstance(spec, dict) or set(spec) != keys:
        raise ValueError("Invalid trial shunt-DTC parasitic schema")
    cap = spec["fixed_capacitance_pf"]
    q = spec["q"]
    if (type(cap) not in (float, int) or not math.isfinite(cap) or cap <= 0
            or type(q) not in (float, int) or not math.isfinite(q) or q <= 0
            or q != resolved["components"]["PCB_PATTERN_C"]["q"]):
        raise ValueError("Invalid fixed shunt-DTC C or PCB-C Q")
    var = resolved["components"]["IC_VARIABLE_C"]
    if (var["max_branches_principle"] != 3 or var["q"] != 35
            or spec["variable_capacitance_pf_range"] != [
                var["min_total_variable_pf_per_branch"],
                var["max_total_variable_pf_per_branch"]]):
        raise ValueError("Trial must retain RF-T005 variable C limits")
    expected = {
        "applies_to": "each_shunt_to_ground_IC_VARIABLE_C_branch",
        "q_model": "omega_C_over_1_over_Q_minus_j",
        "present_at_variable_C_zero": True,
        "not_applicable_to_non_ground_variable_C": True,
        "frequency_invariant": True,
        "setting_invariant": True,
        "pcb_pattern_C_count_increment": 0,
        "additional_chip_area_units": 0,
        "tolerance_status": "nominal_only_not_evaluated",
    }
    if any(type(spec[key]) is not type(value) or spec[key] != value
           for key, value in expected.items()):
        raise ValueError("Invalid scope or accounting of shunt-DTC parasitic")

def _validate_trial_pcb_pattern_c_by_connection(spec, resolved):
    """Validate RF-T008's connection-selective PCB-C size/Q, not a global Q override.

    The immutable formal PCB_PATTERN_C record remains 0.02..0.2pF/Q40.
    Special permanent shunt DTC 0.5pF/Q40 is outside the PCB_PATTERN_C count.
    """
    keys = {"ground_node", "grounded", "non_ground", "max_count", "q_model",
            "fixed_components_only", "setting_invariant", "nominal_only"}
    if not isinstance(spec, dict) or set(spec) != keys:
        raise ValueError("Invalid location-specific PCB-C trial schema")
    formal = resolved["components"]["PCB_PATTERN_C"]
    reference = {"min_pf_per_component": formal["min_pf_per_component"],
                 "max_pf_per_component": formal["max_pf_per_component"],
                 "q": formal["q"]}
    if (type(spec["ground_node"]) is not int or spec["ground_node"] != 0
            or type(spec["max_count"]) is not int
            or spec["max_count"] != formal["max_count"]
            or spec["q_model"] != "omega_C_over_1_over_Q_minus_j"
            or spec["fixed_components_only"] is not True
            or spec["setting_invariant"] is not True
            or spec["nominal_only"] is not True):
        raise ValueError("Invalid PCB-C ground convention or trial accounting")
    expected_ground = {"min_pf_per_component": formal["min_pf_per_component"],
                       "max_pf_per_component": 1.0, "q": 60}
    if spec["non_ground"] != reference or spec["grounded"] != expected_ground:
        raise ValueError("PCB-C trial must change only grounded fixed PCB-C")
    for rule in (spec["grounded"], spec["non_ground"]):
        if (not isinstance(rule, dict)
                or any(type(rule[k]) not in (int, float) or not math.isfinite(rule[k])
                       for k in ("min_pf_per_component", "max_pf_per_component", "q"))
                or rule["min_pf_per_component"] <= 0
                or rule["min_pf_per_component"] > rule["max_pf_per_component"]
                or rule["q"] <= 0):
            raise ValueError("Invalid grounded/non-grounded PCB-C numerical limits")


def _validate_trial_ic_fixed_c_by_connection(spec, resolved):
    """Validate IC-fixed Q60 per installed variable-C branch (RF-T008 rev2).

    The RF-F003 0..3pF/Q35 variable-C limit remains independent of the
    setting-common 0.2..3 or 0.5..3pF/Q60 fixed component.
    """
    keys = {"ground_node", "grounded", "non_ground", "fixed_c_q",
            "variable_c_q", "variable_capacitance_pf_range",
            "fixed_c_stays_at_variable_C_zero", "fixed_c_setting_invariant",
            "fixed_c_frequency_invariant",
            "fixed_c_only_in_parallel_with_installed_variable_C",
            "fixed_c_count_per_installed_variable_C", "max_composite_branches",
            "fixed_c_counts_toward_pcb_pattern_C", "additional_chip_area_units",
            "q_model", "physical_chip_footprint_status", "tolerance_status"}
    if not isinstance(spec, dict) or set(spec) != keys:
        raise ValueError("Invalid RF-T008 IC fixed C trial schema")
    var = resolved["components"]["IC_VARIABLE_C"]
    pcb = resolved["components"]["PCB_PATTERN_C"]
    if (type(spec["ground_node"]) is not int or spec["ground_node"] != 0
            or type(spec["fixed_c_q"]) not in (int, float)
            or spec["fixed_c_q"] != 60
            or type(spec["variable_c_q"]) not in (int, float)
            or spec["variable_c_q"] != var["q"] or var["q"] != 35
            or spec["variable_capacitance_pf_range"] != [
                var["min_total_variable_pf_per_branch"],
                var["max_total_variable_pf_per_branch"]]
            or spec["max_composite_branches"] != var["max_branches_principle"]
            or spec["max_composite_branches"] != 3
            or spec["fixed_c_stays_at_variable_C_zero"] is not True
            or spec["fixed_c_setting_invariant"] is not True
            or spec["fixed_c_frequency_invariant"] is not True
            or spec["fixed_c_only_in_parallel_with_installed_variable_C"] is not True
            or type(spec["fixed_c_count_per_installed_variable_C"]) is not int
            or spec["fixed_c_count_per_installed_variable_C"] != 1
            or type(spec["fixed_c_counts_toward_pcb_pattern_C"]) is not int
            or spec["fixed_c_counts_toward_pcb_pattern_C"] != 0
            or type(spec["additional_chip_area_units"]) is not int
            or spec["additional_chip_area_units"] != 0
            or spec["q_model"] != "omega_C_over_1_over_Q_minus_j"
            or spec["physical_chip_footprint_status"] != "not_modeled_nominal_phase2_only"
            or spec["tolerance_status"] != "nominal_only_not_evaluated"):
        raise ValueError("IC fixed C Q, branch accounting or model inconsistent")
    for position, lo in (("grounded", 0.5), ("non_ground", 0.2)):
        rule = spec[position]
        if (not isinstance(rule, dict)
                or set(rule) != {"min_pf_per_branch", "max_pf_per_branch"}
                or any(type(rule[k]) not in (int, float) or not math.isfinite(rule[k])
                       for k in ("min_pf_per_branch", "max_pf_per_branch"))
                or rule["min_pf_per_branch"] != lo
                or rule["max_pf_per_branch"] != 3):
            raise ValueError("IC fixed C capacity limits differ from approved ranges")
    # Fixed IC capacitors are NOT counted as PCB_PATTERN_C.
    if pcb["max_count"] != 3:
        raise ValueError("Unexpected PCB-C count in T008")


def _same_kind(existing, replacement):
    """Require type-compatible trial values, including nested list members."""
    if isinstance(existing, bool):
        return type(replacement) is bool
    if isinstance(existing, (int, float)):
        return type(replacement) in (int, float) and math.isfinite(replacement)
    if isinstance(existing, dict):
        return (isinstance(replacement, dict) and set(replacement) == set(existing) and
                all(_same_kind(existing[key], value) for key, value in replacement.items()))
    if isinstance(existing, list):
        return isinstance(replacement, list) and (
            not existing or all(
                any(_same_kind(template, item) for template in existing)
                for item in replacement))
    return type(replacement) is type(existing)


def _merge(base, overrides):
    if not isinstance(overrides, dict):
        raise ValueError("Trial overrides must be an object")
    result = copy.deepcopy(base)
    for key, value in overrides.items():
        if key not in result:
            raise ValueError(f"Unknown constraint override key: {key}")
        existing = result[key]
        if isinstance(value, dict):
            if not isinstance(existing, dict):
                raise ValueError(f"Not an object in base constraints: {key}")
            result[key] = _merge(existing, value)
        elif isinstance(existing, dict) or not _same_kind(existing, value):
            raise ValueError(f"Constraint override type mismatch: {key}")
        else:
            result[key] = value
    return result


def load_constraint(constraint_id=None, *, root=ROOT, allow_trial=False):
    """Return resolved constraints; trials require explicit opt-in and registry approval."""
    root = Path(root)
    registry = validate_registry(root=root)
    cid = constraint_id or registry["active_formal_id"]
    if cid in registry["formal"]:
        payload = _read(repository_file(root, registry["formal"][cid]["file"]))
        if payload.get("active_constraint_id") != cid:
            raise ValueError("Formal snapshot identity mismatch")
        return payload
    if cid not in registry["trial"] or not allow_trial:
        raise ValueError(f"Unknown or unapproved constraint ID: {cid}")
    entry = registry["trial"][cid]
    if entry.get("state") != "study_authorized":
        raise ValueError(f"Trial not authorized: {cid}")
    trial = _read(repository_file(root, entry["file"]))
    if trial.get("constraint_id") != cid or trial.get("status") != "trial":
        raise ValueError("Trial snapshot identity mismatch")
    base_id = trial["base_constraint_id"]
    if base_id not in registry["formal"]:
        raise ValueError("Trial base must be an immutable formal version")
    base = load_constraint(base_id, root=root)
    result = _merge(base, trial["overrides"])
    result["active_constraint_id"] = cid
    result["active_constraint_status"] = "trial"
    result["trial_base_constraint_id"] = base_id
    result["trial_variable_c_layout"] = copy.deepcopy(trial["study_variable_c_layout"])
    if "study_additional_stopband" in trial:
        result["trial_additional_stopband"] = copy.deepcopy(trial["study_additional_stopband"])
    if "study_shunt_dtc_parasitic" in trial:
        result["trial_shunt_dtc_parasitic"] = copy.deepcopy(trial["study_shunt_dtc_parasitic"])
    if "study_pcb_pattern_c_by_connection" in trial:
        result["trial_pcb_pattern_c_by_connection"] = copy.deepcopy(
            trial["study_pcb_pattern_c_by_connection"])
    if "study_ic_fixed_c_by_connection" in trial:
        result["trial_ic_fixed_c_by_connection"] = copy.deepcopy(
            trial["study_ic_fixed_c_by_connection"])
    return result


def constraint_fingerprint(resolved_policy):
    """SHA-256 of canonical resolved JSON, suitable for a run manifest."""
    encoded = json.dumps(resolved_policy, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_variable_c_connections(branches, resolved_policy):
    """Check specified C-branch endpoints against formal/trial *connection* scope.

    Branches are dictionaries with integer 'a', 'b' node IDs (0 = ground).
    Non-ground branches must explicitly identify role='bridge' or
    role='series'. This checks connection metadata; graph analysis is
    separately needed to establish the physical relationship of each
    connection to the fixed signal path.
    """
    if not isinstance(branches, (list, tuple)):
        raise ValueError("Variable C branches must be a sequence")
    spec = resolved_policy["components"]["IC_VARIABLE_C"]
    if len(branches) > spec["max_branches_principle"]:
        raise ValueError("Variable C count exceeds resolved constraints")
    grounded = bridges = series = 0
    for branch in branches:
        if not isinstance(branch, dict):
            raise ValueError("Variable C branch must be a mapping")
        a, b = branch.get("a"), branch.get("b")
        if (type(a) is not int or type(b) is not int or a < 0 or b < 0 or a == b):
            raise ValueError("Invalid variable-C connection")
        if a == 0 or b == 0:
            if "shunt_to_ground" not in spec["positions_allowed_by_default"]:
                raise ValueError("Ground-shunt variable C is not authorized")
            if branch.get("role") not in (None, "shunt_to_ground"):
                raise ValueError("Invalid ground-shunt variable C role")
            grounded += 1
        else:
            role = branch.get("role")
            if role not in ("bridge", "series"):
                raise ValueError("Non-ground variable C requires an explicit role")
            if role == "bridge":
                if "non_ground_bridge" not in spec["positions_allowed_by_default"]:
                    raise ValueError("Non-ground bridge is not authorized")
                bridges += 1
            else:
                if ("series" not in spec["positions_allowed_by_default"] or
                        spec["series_requires_separate_approval"]):
                    raise ValueError("Series variable C is not authorized")
                series += 1
    if resolved_policy.get("active_constraint_status") == "trial":
        layout = resolved_policy["trial_variable_c_layout"]
        if layout.get("connection_policy") == "any_allowed":
            if len(branches) > layout["branch_count"]:
                raise ValueError("Trial variable-C count exceeds maximum")
        elif (len(branches) != layout["branch_count"]
              or grounded != layout["shunt_to_ground"]
              or bridges != layout["non_ground_bridge"] or series):
            raise ValueError("Variable-C connections do not match authorized trial layout")
    return True
