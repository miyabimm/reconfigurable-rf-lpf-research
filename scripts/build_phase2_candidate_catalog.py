#!/usr/bin/env python3
"""Phase 2 unified curated view: historical 14 + archived 2026-10-17 Pareto 10.

No RF computation, optimization or original-evidence mutation. All new numeric
records are sourced from the immutable dated snapshot and verified Git blob
objects. The source and verification material remain separate from this index.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY = "data/catalog/research_candidate_register_20261017.csv"
LEGACY_ORIGINAL_PATH = "data/research_candidate_register.csv"
LEGACY_BLOB_SHA1 = "a0015088db4c8a243c0fa5a3e4000c4e47b3fddb"
REGISTRY_SNAPSHOT = "data/catalog/constraints_registry_20261017.json"
REGISTRY_BLOB_SHA1 = "4363b99aae968c6573e286f7dc20ea32e959fe8b"
EXPERIMENT_INDEX_SNAPSHOT = "data/catalog/experiment_index_20261017.csv"
EXPERIMENT_INDEX_BLOB_SHA1 = "4fb76382458436f0de1a1fd8083bd6d9d737d18d"
SNAPSHOT = "data/pareto_snapshots/rf_t005_rf_f003_20261017.json"
OUTPUT_CSV = "data/catalog/phase2_candidate_catalog_20261017.csv"

BASE_COLUMNS = (
    "catalog_id", "experiment_id", "constraint_class", "constraint_id",
    "effective_constraint_sha256", "objective", "requirement_db",
    "chip_area_units", "worst_il_db", "min_h2_db", "min_h3_db",
    "threshold_classification", "checkpoint_path", "checkpoint_stage_index",
    "verification_path", "comparison_key",
)
EXTRA_COLUMNS = (
    "origin", "snapshot_id", "source_subcandidate_id", "checkpoint_git_blob_sha1",
    "verification_git_blob_sha1", "num_lqp02hv", "num_gjm01",
    "num_pcb_pattern_c", "num_ic_variable_c", "mesh_interval_count",
    "mesh_points_per_interval", "independent_mna_probe_points",
    "experiment_execution_status", "solver_convergence_status",
    "continuous_band_extrema_proven", "physical_realization_verified",
    "original_metadata_discrepancy",
)
FIELDS = BASE_COLUMNS + EXTRA_COLUMNS
SNAPSHOT_CLASSES = {"trial": "trial", "formal_active": "formal"}


def rows_from_csv(root: Path, rel: str) -> list[dict[str, str]]:
    with (root / rel).open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def read_json(root: Path, rel: str):
    return json.loads((root / rel).read_text(encoding="utf-8"))


def safe_evidence(root: Path, rel: str) -> bytes:
    if not isinstance(rel, str) or not rel:
        raise ValueError("missing evidence path")
    fragment = Path(rel)
    if fragment.is_absolute() or ".." in fragment.parts or "\\" in rel:
        raise ValueError("unsafe evidence path: " + rel)
    base = root.resolve()
    full = (base / fragment).resolve()
    if not full.is_relative_to(base) or not full.is_file():
        raise ValueError("missing or external evidence: " + rel)
    return full.read_bytes()


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def evidence_blob_check(root: Path, record: dict) -> str:
    rel = record.get("path", "")
    claimed = record.get("blob_sha", "")
    if not re.fullmatch("[0-9a-f]{40}", claimed):
        raise ValueError("missing or invalid source Git blob SHA for " + str(rel))
    observed = git_blob_sha1(safe_evidence(root, rel))
    if observed != claimed:
        raise ValueError("Git blob mismatch for " + rel)
    return claimed


def numeric(value, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite " + label)
    return number


def build_catalog(root=ROOT):
    root = Path(root)
    if git_blob_sha1(safe_evidence(root, LEGACY)) != LEGACY_BLOB_SHA1:
        raise ValueError("original 2026-10-17 historical catalog source blob changed")
    raw = rows_from_csv(root, LEGACY)
    if len(raw) != 14:
        raise ValueError("2026-10-17 legacy source must contain 14 curated records")
    for item in raw:
        if set(item) != set(BASE_COLUMNS):
            raise ValueError("legacy CSV schema changed unexpectedly")
    snap = read_json(root, SNAPSHOT)
    # Freeze dated source metadata; active main policy and live experiment
    # index may legitimately evolve after this historical snapshot.
    for rel, expected in ((REGISTRY_SNAPSHOT, REGISTRY_BLOB_SHA1),
                          (EXPERIMENT_INDEX_SNAPSHOT, EXPERIMENT_INDEX_BLOB_SHA1)):
        if git_blob_sha1(safe_evidence(root, rel)) != expected:
            raise ValueError("archived 2026-10-17 metadata blob changed: " + rel)
    registry = read_json(root, REGISTRY_SNAPSHOT)
    if (snap.get("snapshot_id") != "AREA_IL_PARETO_RF_T005_RF_F003_20261017"
            or snap.get("phase") != "Phase 2" or snap.get("status")
            != "archived_best_found_non_dominated_observed_candidates"):
        raise ValueError("unexpected immutable snapshot identity")
    if registry.get("active_formal_id") != "RF-F003":
        raise ValueError("active formal RF constraint changed: review before reusing 2026-10-17 catalog")
    experiments = {x["experiment_id"]: x for x in
                   rows_from_csv(root, EXPERIMENT_INDEX_SNAPSHOT)}
    seen = {x["catalog_id"] for x in raw}
    if len(seen) != len(raw):
        raise ValueError("duplicate legacy catalog IDs")
    records = [{**r, **{k: "" for k in EXTRA_COLUMNS}, "origin": "legacy_curated_register",
                "experiment_execution_status": (experiments[r["experiment_id"]]["execution_status"]
                                                if r["experiment_id"] in experiments else "unknown")}
               for r in raw]
    expected = {"RF-T005": 6, "RF-F003": 4}
    found = Counter()
    for condition in snap["conditions"]:
        cid = condition["constraint_id"]
        found[cid] += len(condition["candidates"])
        if cid not in expected or condition["type"] not in SNAPSHOT_CLASSES:
            raise ValueError("unexpected snapshot constraint ID or class")
        kind = SNAPSHOT_CLASSES[condition["type"]]
        registry_group = registry["formal" if kind == "formal" else "trial"]
        if cid not in registry_group:
            raise ValueError("constraint ID and declared type mismatch: " + cid)
        constraint = registry_group[cid]
        if kind == "formal":
            if (constraint["effective_constraint_sha256"] !=
                    condition["effective_constraint_sha256"]):
                raise ValueError("formal policy fingerprint mismatch")
        else:
            if (constraint["base_constraint_id"] != "RF-F003" or
                    condition["based_on"] != "RF-F003"):
                raise ValueError("trial base policy mismatch")
        for c in condition["candidates"]:
            identity = c["id"]
            if identity in seen:
                raise ValueError("duplicate ID across source catalogs: " + identity)
            seen.add(identity)
            e = experiments[c["experiment_id"]]
            if (e["constraint_class"] != kind or e["constraint_id"] != cid or
                    e["effective_constraint_sha256"] != condition["effective_constraint_sha256"]
                    or e["objective"] != "full_lpf"):
                raise ValueError("experiment index/source condition mismatch for " + identity)
            counts = c["component_count"]
            nl = int(counts["LQP02HV_Q25"])
            ng = int(counts["GJM01_Q80"])
            np = int(counts["PCB_PATTERN_C_Q40"])
            nc = int(counts["IC_variable_C_Q35"])
            if min(nl, ng, np, nc) < 0 or nc > condition["maximum_IC_C_branches"]:
                raise ValueError("component count outside trial/formal policy: " + identity)
            area = numeric(c["chip_area_units"], "chip area")
            if not math.isclose(area, nl + 2.0 * ng / 3.0, abs_tol=1e-10):
                raise ValueError("chip area formula mismatch: " + identity)
            metric = c["metrics"]
            il = numeric(metric["worst_il_db"], "IL")
            h2 = numeric(metric["min_h2_db"], "H2")
            h3 = numeric(metric["min_h3_db"], "H3")
            verify = c["verification"]
            if (not verify["finite_mesh_H2_H3_30dB_pass"] or
                    h2 < 30.0 or h3 < 30.0 or il <= 0 or
                    verify["mesh_frequency_intervals"] != 28 or
                    verify["points_per_interval"] < 1 or
                    verify["independent_coupled_L_MNA_probe_points"] < 0):
                raise ValueError("snapshot finite mesh claim inconsistent: " + identity)
            if (verify["continuous_frequency_extrema_proven"] or
                    verify["physical_realization_verified"]):
                raise ValueError("new claims beyond saved snapshot: " + identity)
            source = c["source"]
            checkpoint = source["complete_parameter_vector"]
            metric_evidence = source["reported_metric_evidence"]
            checkpoint_sha = evidence_blob_check(root, checkpoint)
            metric_sha = evidence_blob_check(root, metric_evidence)
            # Source pointer identity is essential when extracting a sub-candidate
            # from a JSON containing more than one stored parameter vector.
            if not checkpoint["path"].startswith(
                    "experiments/chatgpt_topology_search/runs/" + c["experiment_id"] + "/"):
                raise ValueError("source path does not belong to experiment " + identity)
            note = c.get("source_metadata_discrepancy", "")
            if note and identity != "F003_4L_A6p667_EXP047":
                raise ValueError("unexpected metadata correction: " + identity)
            r = {
                "catalog_id": identity,
                "experiment_id": c["experiment_id"],
                "constraint_class": kind,
                "constraint_id": cid,
                "effective_constraint_sha256": condition["effective_constraint_sha256"],
                "objective": snap["objective"],
                "requirement_db": "30",
                "chip_area_units": str(area),
                "worst_il_db": str(il),
                "min_h2_db": str(h2),
                "min_h3_db": str(h3),
                "threshold_classification": "strict_finite_grid",
                "checkpoint_path": checkpoint["path"],
                "checkpoint_stage_index": "",
                "verification_path": metric_evidence["path"],
                "comparison_key": cid + "_full_lpf_30_strict_finite_grid",
                "origin": "archived_pareto_20261017",
                "snapshot_id": snap["snapshot_id"],
                "source_subcandidate_id": c.get("selected_candidate_id", ""),
                "checkpoint_git_blob_sha1": checkpoint_sha,
                "verification_git_blob_sha1": metric_sha,
                "num_lqp02hv": str(nl),
                "num_gjm01": str(ng),
                "num_pcb_pattern_c": str(np),
                "num_ic_variable_c": str(nc),
                "mesh_interval_count": str(verify["mesh_frequency_intervals"]),
                "mesh_points_per_interval": str(verify["points_per_interval"]),
                "independent_mna_probe_points": str(verify["independent_coupled_L_MNA_probe_points"]),
                "experiment_execution_status": e["execution_status"],
                "solver_convergence_status": c.get("solver_status", "not_stated_in_snapshot"),
                "continuous_band_extrema_proven": "false",
                "physical_realization_verified": "false",
                "original_metadata_discrepancy": note,
            }
            records.append(r)
    if dict(found) != expected or len(records) != 24:
        raise ValueError("source counts changed; expected legacy 14 + trial 6 + formal 4")
    grouped = defaultdict(list)
    for r in records:
        grouped[r["comparison_key"]].append(r)
    for key, group in grouped.items():
        fingerprints = {(r["constraint_class"], r["constraint_id"],
                         r["effective_constraint_sha256"], r["objective"],
                         r["requirement_db"], r["threshold_classification"]) for r in group}
        if len(fingerprints) != 1:
            raise ValueError("condition/evidence mixed in " + key)
    for cid in expected:
        group = [r for r in records if r["constraint_id"] == cid]
        if len(group) != expected[cid]:
            raise ValueError("unexpected snapshot group size")
        for a in group:
            for b in group:
                if a is b:
                    continue
                aa, al = float(a["chip_area_units"]), float(a["worst_il_db"])
                ba, bl = float(b["chip_area_units"]), float(b["worst_il_db"])
                if ba <= aa and bl <= al and (ba < aa or bl < al):
                    raise ValueError("archived snapshot is not internally nondominated: " +
                                     a["catalog_id"])
    return records


def as_csv(records: list[dict]) -> str:
    out = io.StringIO(newline="")
    w = csv.DictWriter(out, fieldnames=FIELDS, lineterminator="\n")
    w.writeheader()
    w.writerows(records)
    return out.getvalue()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true",
                   help="fail when generated output differs; never change files")
    args = p.parse_args()
    records = build_catalog()
    content = as_csv(records)
    file = ROOT / OUTPUT_CSV
    if args.check:
        if not file.is_file() or file.read_text(encoding="utf-8") != content:
            raise SystemExit("STALE derived catalog: " + OUTPUT_CSV)
    else:
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")
    print("PASS: unified catalog (14 legacy + 6 RF-T005 + 4 RF-F003), "
          "10 source vectors and 10 metric sources Git-blob verified; "
          + ("on-disk outputs match" if args.check else "outputs generated"))


if __name__ == "__main__":
    main()
