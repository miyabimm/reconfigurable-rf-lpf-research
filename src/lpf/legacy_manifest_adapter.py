"""Auditable compatibility view of one *pinned*, nonstandard EXP-047 source.

Do not feed this view to validate_manifest: it is NOT a synthesized complete
experiment manifest. It supplies only the fields needed by the existing
experiment index to acknowledge the original partial in-chat experiment.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .constraint_versions import constraint_fingerprint, load_constraint, ROOT

OVERLAY = "data/validation/exp047_legacy_manifest_adapter_20261017.json"
ORIGINAL = "experiments/chatgpt_topology_search/runs/EXP-047/manifest.json"
MAPPING_FIELDS = {
    "experiment_id", "constraint_class", "constraint_id", "objective",
    "index_execution_status", "index_numerical_validation",
    "index_independent_validation", "index_purpose",
}
EXPECTED_SOURCE_SHA = "94973b5e5a9e9b0fcd3a3ad9ffd39ea4197475e0"


def _blob_sha(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def legacy_exp047_index_view(root=ROOT):
    """Validate unchanged original source and output minimal index-only mapping.

    Unknown execution revision, seed, environment and full optimizer replay
    remain UNKNOWN and are explicitly not turned into proven facts here.
    """
    root = Path(root)
    ov = json.loads((root / OVERLAY).read_text(encoding="utf-8"))
    original_path = root / ORIGINAL
    raw = original_path.read_bytes()
    sha = _blob_sha(raw)
    if (ov.get("schema_version") != 1 or ov.get("phase") != "Phase 2" or
            ov.get("source_manifest_path") != ORIGINAL or
            ov.get("source_manifest_git_blob_sha1") != EXPECTED_SOURCE_SHA or
            sha != EXPECTED_SOURCE_SHA):
        raise ValueError("EXP-047 legacy source identity changed; explicit review required")
    m = json.loads(raw)
    mapping = ov["mapping"]
    if set(mapping) != MAPPING_FIELDS or (
        mapping["experiment_id"], mapping["constraint_class"], mapping["constraint_id"],
        mapping["objective"], mapping["index_execution_status"],
        mapping["index_numerical_validation"], mapping["index_independent_validation"],
    ) != ("EXP-047", "formal", "RF-F003", "full_lpf", "partial", "screened", "passed"):
        raise ValueError("EXP-047 normalization mapping changed")
    if not isinstance(mapping["index_purpose"], str) or not mapping["index_purpose"].strip():
        raise ValueError("EXP-047 source index purpose is absent")
    if (m.get("schema_version") != 1 or m.get("experiment_id") != "EXP-047" or
            m.get("phase") != "Phase 2" or m.get("constraint_id") != "RF-F003" or
            m.get("phase3") != "not_authorized"):
        raise ValueError("EXP-047 original source identity does not match overlay")
    e, v = m["execution"], m["validation"]
    semantics = ov["verified_source_semantics"]
    if (e.get("status") != "partial_local_best_found" or
            e.get("github_actions_search_executed") is not False or
            v.get("physical_realization") is not False or
            v.get("continuous_extrema_proof") is not False or
            semantics.get("original_execution_status") != e["status"] or
            semantics.get("github_actions_search_executed") is not False or
            semantics.get("physical_realization_verified") is not False or
            semantics.get("continuous_extrema_proven") is not False or
            semantics.get("phase3") != m["phase3"]):
        raise ValueError("EXP-047 execution/verification declarations changed")
    unknown = ov["unknown_not_inferred"]
    if set(unknown) != {
        "original_optimizer_git_commit", "original_random_seed",
        "original_environment", "original_worktree_cleanliness",
        "original_solver_convergence_all_candidates"
    } or any(x is not None for x in unknown.values()):
        raise ValueError("Original unknown provenance must remain explicitly unknown")

    resolved = load_constraint("RF-F003", root=root, allow_trial=False)
    digest = constraint_fingerprint(resolved)
    if (resolved["active_constraint_status"] != "formal" or
            m.get("active_formal_constraint_sha256") != digest or
            m.get("bands_sha256") != hashlib.sha256(
                (root / "rf/bands.csv").read_bytes()).hexdigest()):
        raise ValueError("EXP-047 formal policy or frequency-band source mismatch")
    ports = resolved["external_port_parasitics"]
    for kind in ("input_parasitic", "output_parasitic"):
        expected = ports[kind]["sha256"]
        if m["s2p_provenance"][("input" if kind == "input_parasitic" else "output")+"_sha256"] != expected:
            raise ValueError("EXP-047 source S2P provenance mismatch")
        path = root / ports[kind]["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Original fixed S2P content is not as expected")

    checked = m["validated_candidates"]
    if not isinstance(checked, list) or len(checked) < 4:
        raise ValueError("EXP-047 selected candidate evidence absent")
    for candidate in checked:
        rel = candidate["reference"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+\.json", rel):
            raise ValueError("EXP-047 evidence reference must be a local JSON name")
        if not (original_path.parent / rel).is_file():
            raise ValueError("EXP-047 evidence file missing: " + rel)

    # This is deliberately NOT a canonical new_manifest output. Its narrow
    # shape supports index comparisons only and does not pass validate_manifest.
    return {
        "experiment_id": mapping["experiment_id"],
        "purpose": mapping["index_purpose"],
        "objective": mapping["objective"],
        "constraints": {
            "class": "formal", "constraint_id": "RF-F003",
            "effective_constraint_sha256": digest,
        },
        "execution": {"status": mapping["index_execution_status"]},
        "validation": {
            "numerical": mapping["index_numerical_validation"],
            "independent": mapping["index_independent_validation"],
        },
    }
