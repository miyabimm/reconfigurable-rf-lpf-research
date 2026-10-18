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
