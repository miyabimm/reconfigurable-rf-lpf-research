"""Phase 2 experiment provenance; historical evidence is never silently upgraded.

A historical inventory hash identifies an archived file, NOT the unknown RF
conditions used to produce it. New runs store the complete resolved RF policy.
"""
import csv
import hashlib
import importlib.metadata
import io
import json
import math
import platform
import re
import subprocess
from pathlib import Path

from .constraint_versions import (
    ROOT, constraint_fingerprint, load_constraint, repository_file, rf_input_file, validate_registry,
)

RUNS = "experiments/chatgpt_topology_search/runs"
INDEX_FIELDS = (
    "experiment_id", "constraint_class", "constraint_id", "effective_constraint_sha256",
    "objective", "execution_status", "numerical_validation", "independent_validation",
    "manifest", "purpose",
)
EXECUTION_STATES = {"planned", "running", "partial", "completed", "failed", "not_run", "unknown"}
VALIDATION_STATES = {"not_run", "screened", "passed", "failed", "reported_in_sources", "unknown"}


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sha(value, size=64):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{" + str(size) + "}", value) is not None


def _environment():
    return {
        "python": platform.python_version(), "platform": platform.platform(),
        "dependencies": {name: importlib.metadata.version(name) for name in ("numpy", "scipy")},
    }


def new_manifest(experiment_id, purpose, search_scope, *, objective, seed,
                 root=ROOT, constraint_id=None, allow_trial=False):
    """Capture current inputs before a new run; no optimization or approval occurs.

    Callers must persist this manifest and update execution/validation after running.
    An unknown seed is permitted but explicitly prevents exact optimizer replay.
    """
    root = Path(root)
    resolved = load_constraint(constraint_id, root=root, allow_trial=allow_trial)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, text=True).strip())
    manifest = {
        "schema_version": 1, "experiment_id": experiment_id, "phase": "Phase 2",
        "purpose": purpose, "objective": objective,
        "constraints": {
            "class": resolved["active_constraint_status"],
            "constraint_id": resolved["active_constraint_id"],
            "base_constraint_id": resolved.get("trial_base_constraint_id"),
            "effective_constraint_sha256": constraint_fingerprint(resolved),
            "effective_constraints": resolved,
            "legacy_policy_version": resolved.get("policy_version"),
        },
        "code": {"execution_sha": sha, "working_tree_dirty": dirty, "archive_sha": None},
        "random_seed": seed, "environment": _environment(), "search_scope": search_scope,
        "bands_sha256": file_sha256(rf_input_file(root, resolved["bands_file"])),
        "execution": {"status": "planned", "elapsed_seconds": None, "evaluation_count": None},
        "validation": {
            "numerical": "not_run", "independent": "not_run", "implementation": "not_run",
            "analysis_grid": None, "independent_grid": None,
        },
        "evidence": [], "limitations": [],
    }
    if dirty:
        manifest["limitations"].append("Working tree is dirty; execution SHA alone cannot replay this run.")
    if seed is None:
        manifest["limitations"].append("Random seed is unknown; exact optimizer replay is unavailable.")
    validate_manifest(manifest, root=root)
    return manifest


def validate_manifest(manifest, *, root=ROOT, verify_evidence=True, allow_archived=False):
    """Validate provenance and resolve versioned policies again to detect drift."""
    if not isinstance(manifest, dict):
        raise ValueError("Manifest must be an object")
    required = {"schema_version", "experiment_id", "phase", "purpose", "objective", "constraints",
                "code", "random_seed", "environment", "search_scope", "bands_sha256",
                "execution", "validation", "evidence", "limitations"}
    if required - manifest.keys():
        raise ValueError(f"Missing manifest fields: {sorted(required - manifest.keys())}")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("Unsupported manifest schema")
    if manifest["phase"] != "Phase 2":
        raise ValueError("Manifest must remain in Phase 2")
    if not isinstance(manifest["experiment_id"], str) or not re.fullmatch(r"EXP-[0-9]{3}", manifest["experiment_id"]):
        raise ValueError("Invalid experiment identity")
    if not isinstance(manifest["purpose"], str) or not manifest["purpose"].strip():
        raise ValueError("Experiment purpose required")
    if manifest["objective"] not in {"matching_only", "full_lpf", "mixed", "unknown"}:
        raise ValueError("Invalid evaluation objective")
    for key in ("constraints", "code", "execution", "validation", "search_scope"):
        if not isinstance(manifest[key], dict):
            raise ValueError(f"Manifest {key} must be an object")
    c = manifest["constraints"]
    if {"class", "constraint_id", "base_constraint_id", "effective_constraint_sha256",
        "effective_constraints", "legacy_policy_version"} - c.keys():
        raise ValueError("Missing constraint provenance")
    if c["class"] == "historical":
        if any(c[k] is not None for k in ("constraint_id", "base_constraint_id",
                                         "effective_constraint_sha256", "effective_constraints")):
            raise ValueError("Historical inventory must not invent resolved RF constraints")
    elif c["class"] in {"formal", "trial"}:
        if not isinstance(c["constraint_id"], str) or manifest["objective"] in {"mixed", "unknown"}:
            raise ValueError("Versioned runs require a constraint ID and separate evaluation objective")
        from .constraint_history import archived_binding
        binding = (archived_binding(c['constraint_id'], c['effective_constraint_sha256'], root=root)
                   if allow_archived else None)
        if binding is not None:
            if (binding != {'class': c['class'], 'base_constraint_id': c['base_constraint_id']}
                    or not isinstance(c['effective_constraints'], dict)
                    or constraint_fingerprint(c['effective_constraints']) != c['effective_constraint_sha256']):
                raise ValueError('Historical manifest RF evidence binding mismatch')
            # Already-saved resolved evidence, not old-schema execution/parsing.
            resolved = c['effective_constraints']
        else:
            resolved = load_constraint(c['constraint_id'], root=root, allow_trial=c['class'] == 'trial')
        if (resolved["active_constraint_status"] != c["class"] or
                resolved.get("trial_base_constraint_id") != c["base_constraint_id"] or
                c["effective_constraints"] != resolved or
                c["effective_constraint_sha256"] != constraint_fingerprint(resolved) or
                c["legacy_policy_version"] != resolved.get("policy_version")):
            raise ValueError("Manifest resolved RF constraints/fingerprint mismatch")
        if not _sha(manifest["bands_sha256"]) or manifest["bands_sha256"] != file_sha256(rf_input_file(root, resolved["bands_file"])):
            raise ValueError("Manifest band definitions mismatch")
    else:
        raise ValueError("Invalid constraint classification")
    code = manifest["code"]
    if {"execution_sha", "archive_sha", "working_tree_dirty"} - code.keys():
        raise ValueError("Missing code provenance")
    for key in ("execution_sha", "archive_sha"):
        if code[key] is not None and not _sha(code[key], 40):
            raise ValueError(f"Invalid code SHA: {key}")
    if code["working_tree_dirty"] is not None and type(code["working_tree_dirty"]) is not bool:
        raise ValueError("Invalid dirty-tree flag")
    if c["class"] != "historical" and (code["execution_sha"] is None or code["working_tree_dirty"] is None):
        raise ValueError("New runs must capture code SHA and dirty-tree state")
    if manifest["random_seed"] is not None and (type(manifest["random_seed"]) is not int or manifest["random_seed"] < 0):
        raise ValueError("Seed must be a nonnegative integer or null")
    if manifest["environment"] is not None and not isinstance(manifest["environment"], dict):
        raise ValueError("Environment must be an object or null")
    if manifest["bands_sha256"] is not None and not _sha(manifest["bands_sha256"]):
        raise ValueError("Invalid band fingerprint")
    execution = manifest["execution"]
    if {"status", "elapsed_seconds", "evaluation_count"} - execution.keys() or execution["status"] not in EXECUTION_STATES:
        raise ValueError("Invalid execution state")
    for key in ("elapsed_seconds", "evaluation_count"):
        v = execution[key]
        if v is not None and (type(v) not in (int, float) or not math.isfinite(v) or v < 0):
            raise ValueError(f"Invalid execution counter: {key}")
    if execution["evaluation_count"] is not None and type(execution["evaluation_count"]) is not int:
        raise ValueError("Evaluation count must be an integer")
    validation = manifest["validation"]
    if {"numerical", "independent", "implementation", "analysis_grid", "independent_grid"} - validation.keys():
        raise ValueError("Missing validation levels/grids")
    for key in ("numerical", "independent", "implementation"):
        if validation[key] not in VALIDATION_STATES:
            raise ValueError(f"Invalid validation state: {key}")
    if not isinstance(manifest["limitations"], list) or any(not isinstance(x, str) for x in manifest["limitations"]):
        raise ValueError("Limitations must be a list of strings")
    if not isinstance(manifest["evidence"], list):
        raise ValueError("Evidence must be a list")
    seen = set()
    for item in manifest["evidence"]:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"} or not _sha(item["sha256"]):
            raise ValueError("Invalid evidence record")
        path = repository_file(root, item['path'])
        if allow_archived:
            from .constraint_history import archived_evidence_file
            archived = archived_evidence_file(item['path'], item['sha256'], root=root)
            if archived is not None:
                path = archived
        if item["path"] in seen:
            raise ValueError("Duplicate evidence path")
        seen.add(item["path"])
        if verify_evidence and (not path.is_file() or file_sha256(path) != item["sha256"]):
            raise ValueError(f"Historical evidence changed or missing: {item['path']}")
    # Also rejects NaN/Infinity anywhere in nested scope, counters or policy.
    json.dumps(manifest, allow_nan=False)
    return manifest


def write_manifest(path, manifest, *, root=ROOT):
    """Create once; refusing replacement protects saved research provenance."""
    validate_manifest(manifest, root=root)
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def experiment_index(manifests):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=INDEX_FIELDS, lineterminator="\n")
    writer.writeheader()
    for path, m in sorted(manifests, key=lambda pair: pair[1]["experiment_id"]):
        c, v = m["constraints"], m["validation"]
        writer.writerow({
            "experiment_id": m["experiment_id"], "constraint_class": c["class"],
            "constraint_id": c["constraint_id"], "effective_constraint_sha256": c["effective_constraint_sha256"],
            "objective": m["objective"], "execution_status": m["execution"]["status"],
            "numerical_validation": v["numerical"], "independent_validation": v["independent"],
            "manifest": path, "purpose": m["purpose"],
        })
    return output.getvalue()


# Issue #359: only these immutable historical manifests and their former
# runtime-only files are eligible for a missing-file exception in the *index
# audit*. Normal validate_manifest and new EXP storage remain fully strict.
_RETIRED_RUNTIME = {
    'EXP-034': ('5a8316cb09d2bed17103811422f3e0d21b0ada74eea4eabf8e4259f8f6854926', 'rf_f002_recovery_20261014/(?:manager-sigterm-residual|sigint-resume)'),
    'EXP-035': ('488307692164d0b49125c3cb63918c5febd8d395432c979edd19fbe136e4817f', 'rf_f002_parallel_benchmark_20261014/[12]-worker'),
    'EXP-036': ('f7e6253436f8fe5e5756551f85c31b17c7107ca32e5592e65c2986966463db7e', 'rf_f002_recovery_20261014/exp036-sigint-resume'),
    'EXP-037': ('c2b2e62097672378ded31e3a7fc912df494806c1e07e3c7a0f7a4519ea2c2de2', 'rf_f002_warm_start_refinement_20261014/unremapped-import-diagnostic'),
    'EXP-038': ('fdb69db72215abebb23e0c0429db04c8b41f5c1a9e6d9b046b8abb77a2e5408f', 'rf_f002_checkpoint_warmstarts_20261014/corrected-run'),
    'EXP-039': ('e2a9d0a7fddcf28077cfe508e1e631bf397b193395cc284b2bf24483f26f0ee5', 'rf_f002_grid_refinement_20261014/run'),
    'EXP-040': ('792fc494504fbb8ac19d7dffab571760b66d3b3c3271dec8be5c85adc2401891', 'rf_f002_solver_ablation_20261014/runs/(?:scaled-relaxed-ftol|scaled-tight|unscaled-tight)'),
    'EXP-041': ('94476a496c28b5cfe4ad51caf7cc8130d60ee43e7771caa14c811a9b376bd96e', 'rf_f002_unscaled_followup_20261014/run'),
}
_RUNTIME_FILE = r'(?:\.manager\.lock|manager\.log|locks/[0-9a-f]{24}\.lock|logs/[0-9a-f]{24}\.attempt-[12]\.log)'
_RECOVERY_TRACE = 'data/validation/rf_f002_recovery_20261014/sigint-resume/manager.log'


def _retired_runtime_view(manifest_path, manifest, *, root):
    """Omit only absent, retired runtime entries from a pinned manifest view.

    The original is untouched. Existing files, the interrupt traceback and all
    other evidence remain SHA-checked. Never use this view for new EXP gates.
    """
    if not isinstance(manifest, dict):
        return manifest
    spec = _RETIRED_RUNTIME.get(manifest.get('experiment_id'))
    if (spec is None or file_sha256(manifest_path) != spec[0]
            or _read(manifest_path) != manifest):
        return manifest
    pattern = re.compile('data/validation/' + spec[1] + '/' + _RUNTIME_FILE)
    evidence = []
    for item in manifest['evidence']:
        name = item['path']
        repository_file(root, name)  # reject escapes even for retired entries
        path = Path(root) / name
        retired = (name != _RECOVERY_TRACE and pattern.fullmatch(name)
                   and not path.exists() and not path.is_symlink())
        if not retired:
            evidence.append(item)
    return {**manifest, 'evidence': evidence}


def audit_provenance(*, root=ROOT):
    """Audit the index and evidence, except retired missing runtime artifacts.

    This is not a complete historical evidence audit; see Issue #359. Future
    storage and direct manifest validation do not use this exception.
    """
    root = Path(root)
    issues, manifests = [], []
    try:
        registry = validate_registry(root=root)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        return [f"Invalid constraint registry: {exc}"]
    for directory in sorted((root / RUNS).glob("EXP-*")):
        try:
            path = directory / "manifest.json"
            raw_manifest = _read(path)
            if directory.name == "EXP-047" and "constraints" not in raw_manifest:
                # Strictly source-pinned 2026-10-17 in-chat source. The normal
                # provenance schema still applies to every other run. We do
                # not invent a missing execution SHA, seed, or environment.
                from .legacy_manifest_adapter import legacy_exp047_index_view
                m = legacy_exp047_index_view(root=root)
            else:
                view = _retired_runtime_view(path, raw_manifest, root=root)
                validate_manifest(view, root=root, allow_archived=True)
                m = raw_manifest
            if m["experiment_id"] != directory.name:
                raise ValueError("Manifest/directory identity mismatch")
            manifests.append((path.relative_to(root).as_posix(), m))
        except (KeyError, TypeError, ValueError, OSError) as exc:
            issues.append(f"Invalid {directory.name} manifest: {exc}")
    if not issues:
        try:
            if (root / "data/experiment_index.csv").read_text(encoding="utf-8") != experiment_index(manifests):
                issues.append("Experiment index differs from manifests")
        except OSError as exc:
            issues.append(f"Missing experiment index: {exc}")
    known = {path: m for path, m in manifests}
    try:
        with (root / "data/candidate_index.csv").open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                cid = row["candidate_id"]
                kind = row.get("constraint_class")
                ref = row.get("manifest")
                policy_id = row.get("constraint_id")
                digest = row.get("effective_constraint_sha256")
                if kind == "historical":
                    if policy_id or digest or re.fullmatch(r"RF-[FT][0-9]{3}", row["spec_id"]):
                        raise ValueError(f"Historical candidate relabelled with versioned RF constraints: {cid}")
                    source = row.get("historical_registry_key")
                    if source and source not in registry.get("historical", {}):
                        raise ValueError(f"Unknown historical registry reference: {cid}")
                elif kind in {"formal", "trial"}:
                    from .constraint_history import archived_binding
                    binding = archived_binding(policy_id, digest, root=root)
                    if binding is None:
                        policy = load_constraint(policy_id, root=root, allow_trial=kind == 'trial')
                        valid = policy['active_constraint_status'] == kind and digest == constraint_fingerprint(policy)
                    else:
                        valid = binding['class'] == kind
                    if not policy_id or not valid or row['spec_id'] != policy_id:
                        raise ValueError(f"Candidate constraint fingerprint/identity mismatch: {cid}")
                    if not ref:
                        raise ValueError(f"Versioned candidate requires experiment manifest: {cid}")
                else:
                    raise ValueError(f"Missing candidate constraint classification: {cid}")
                if ref and (ref not in known or known[ref]["constraints"]["class"] != kind or
                            (known[ref]["constraints"]["constraint_id"] or "") != (policy_id or "") or
                            (known[ref]["constraints"]["effective_constraint_sha256"] or "") != (digest or "") or
                            known[ref]["objective"] != row["objective"]):
                    raise ValueError(f"Candidate/manifest provenance mismatch: {cid}")
    except (KeyError, TypeError, ValueError, OSError) as exc:
        issues.append(f"Invalid candidate provenance: {exc}")
    return issues
