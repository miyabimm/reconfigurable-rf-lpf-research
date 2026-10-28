#!/usr/bin/env python3
"""Non-destructive Phase 2 research candidate catalog consistency audit.

This script checks saved data and classifications; it does not run RF solvers.
Finite-grid numerical agreement is not a physical or continuous-band proof.
"""
import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = "data/research_candidate_register.csv"
THRESHOLD_TOLERANCE_DB = 1e-5
METRIC_MATCH_TOLERANCE_DB = 1e-6


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _csv(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _path(root, relative):
    path = Path(relative)
    if not relative or path.is_absolute() or ".." in path.parts or "\\" in relative:
        raise ValueError("Invalid repository-relative path: " + str(relative))
    absolute = (root / path).resolve()
    if not absolute.is_relative_to(root.resolve()) or not absolute.is_file():
        raise ValueError("Missing or external evidence: " + relative)
    return absolute


def check_threshold(classification, requirement, h2, h3, policy_class):
    """Classify raw extrema separately from solver feasibility tolerance."""
    if classification == "historical_only":
        return [] if policy_class == "historical" else ["Historical label on versioned result"]
    if policy_class == "historical":
        return ["Historical result must not be promoted into a current ranking"]
    if classification == "reported_finite_grid":
        return [] if min(h2, h3) >= requirement else ["Reported finite-grid extrema below requirement"]
    if classification == "strict_finite_grid":
        return [] if min(h2, h3) >= requirement else ["Strict classification contradicts raw harmonic value"]
    if classification == "tolerance_only":
        if not (min(h2, h3) < requirement and
                min(h2, h3) >= requirement - THRESHOLD_TOLERANCE_DB):
            return ["Tolerance-only label contradicts raw harmonic values"]
        return []
    return ["Unknown harmonic threshold classification"]


def _source_metrics(row, checkpoint, validation):
    stage = row["checkpoint_stage_index"]
    if stage and isinstance(checkpoint.get("candidates"), list):
        if validation is not None:
            raise ValueError("EXP-016 reported results must not be labeled as new independent verification")
        idx = int(stage)
        candidates = checkpoint["candidates"]
        if idx < 0 or idx >= len(candidates):
            raise ValueError("Candidate index missing in archived checkpoint")
        item = candidates[idx]
        if item["id"] != row["catalog_id"]:
            raise ValueError("Archived candidate identity mismatch")
        if float(item["goal_harmonics_db"]) < float(row["requirement_db"]):
            raise ValueError("Reported harmonic goal below catalog requirement")
        m = item["reference_metrics"]
        return item["area_units"], m["worst_IL_db"], m["min_H2_db"], m["min_H3_db"]
    if stage:
        if not isinstance(validation, list):
            raise ValueError("Stage validation evidence must be an array")
        matches = [item for item in validation if str(item.get("stage_index")) == stage]
        if len(matches) != 1:
            raise ValueError("Missing or duplicate stage index in independent grid evidence")
        item = matches[0]
        if float(item["target_db"]) != float(row["requirement_db"]):
            raise ValueError("Stage target does not match catalog requirement")
        return (checkpoint["chip_area_cost"], item["worst_il_db"],
                item["min_h2_db"], item["min_h3_db"])
    if "performance" in checkpoint:
        m = checkpoint["performance"]
        return checkpoint["area_units"], m["worst_IL_db"], m["min_H2_db"], m["min_H3_db"]
    if "evaluation" in checkpoint:
        m = checkpoint["evaluation"]
        return checkpoint["chip_area_units"], m["worst_IL_db"], m["min_H2_db"], m["min_H3_db"]
    if "metrics" in checkpoint:
        m = checkpoint["metrics"]
        return checkpoint["area_units"], m["worst_IL_db"], m["min_H2_db"], m["min_H3_db"]
    if all(k in checkpoint for k in ("area", "IL", "H2", "H3")):
        return checkpoint["area"], checkpoint["IL"], checkpoint["H2"], checkpoint["H3"]
    raise ValueError("Unrecognized saved candidate metrics schema")


def audit_catalog(root=ROOT):
    root = Path(root)
    issues = []
    try:
        records = _csv(root / INDEX)
        experiment_rows = {row["experiment_id"]: row for row in
                           _csv(root / "data/experiment_index.csv")}
        legacy_rows = {row["candidate_id"]: row for row in
                       _csv(root / "data/candidate_index.csv")}
        registry = _json(root / "rf/constraints/registry.json")
    except (OSError, ValueError, KeyError) as exc:
        return ["Cannot load catalog/registry: " + str(exc)]
    ids = set()
    if not records:
        return ["Empty research candidate catalog"]
    for row in records:
        candidate_id = row.get("catalog_id", "?")
        try:
            if candidate_id in ids:
                raise ValueError("Duplicate catalog identity")
            ids.add(candidate_id)
            policy_class = row["constraint_class"]
            policy_id = row["constraint_id"]
            objective = row["objective"]
            if objective != "full_lpf":
                raise ValueError("This initial curated catalog contains only full_lpf checkpoints")
            requirement = float(row["requirement_db"])
            area, il, h2, h3 = [float(row[k]) for k in
                                ("chip_area_units", "worst_il_db", "min_h2_db", "min_h3_db")]
            if not all(map(math.isfinite, (requirement, area, il, h2, h3))):
                raise ValueError("Non-finite metric")
            if requirement not in (30.0, 35.0) or area < 0:
                raise ValueError("Invalid target or chip-area cost")
            threshold_errors = check_threshold(
                row["threshold_classification"], requirement, h2, h3, policy_class)
            if threshold_errors:
                raise ValueError("; ".join(threshold_errors))
            if policy_class == "historical":
                if policy_id or row["effective_constraint_sha256"] or candidate_id not in legacy_rows:
                    raise ValueError("Invalid historical provenance")
                historical = legacy_rows[candidate_id]
                if historical["constraint_class"] != "historical":
                    raise ValueError("Historical status differs from the established index")
                for k, v in (("max_il_db", il), ("min_h2_db", h2), ("min_h3_db", h3)):
                    if abs(float(historical[k]) - v) > METRIC_MATCH_TOLERANCE_DB:
                        raise ValueError("Historical index performance mismatch")
            elif policy_class in ("formal", "trial"):
                exp = experiment_rows[row["experiment_id"]]
                if (policy_id != exp["constraint_id"] or
                        policy_class != exp["constraint_class"] or
                        objective != exp["objective"] or
                        row["effective_constraint_sha256"] != exp["effective_constraint_sha256"]):
                    raise ValueError("Experiment index/constraint mismatch")
                valid = registry["formal"] if policy_class == "formal" else registry["trial"]
                if policy_id not in valid:
                    raise ValueError("Unregistered RF constraint ID")
            else:
                raise ValueError("Unknown policy class")
            expected_group = ("legacy_2026_10_10_full_lpf_35_historical"
                              if policy_class == "historical" else
                              f"{policy_id}_{objective}_{int(requirement)}_{row['threshold_classification']}")
            if row["comparison_key"] != expected_group:
                raise ValueError("Comparison key could mix unlike RF evidence")
            checkpoint = _json(_path(root, row["checkpoint_path"]))
            validation_path = _path(root, row["verification_path"])
            validation = _json(validation_path) if validation_path.suffix == ".json" else None
            from_source = _source_metrics(row, checkpoint, validation)
            for k, observed, expected in zip(
                    ("chip_area_units", "worst_il_db", "min_h2_db", "min_h3_db"),
                    (area, il, h2, h3), from_source):
                if abs(observed - float(expected)) > METRIC_MATCH_TOLERANCE_DB:
                    raise ValueError(f"{k} disagrees with saved checkpoint/validation")
            if (not row["checkpoint_stage_index"] and "candidate_id" in checkpoint and
                    row["catalog_id"] != checkpoint["candidate_id"]):
                raise ValueError("Checkpoint identity mismatch")
            recorded_constraint = checkpoint.get("constraint_id", checkpoint.get("trial_constraint_id"))
            if policy_class != "historical" and recorded_constraint != policy_id:
                raise ValueError("Checkpoint constraint mismatch")
            source_hash = checkpoint.get("effective_constraint_sha256", checkpoint.get("constraint_sha256"))
            if source_hash and policy_class != "historical" and source_hash != row["effective_constraint_sha256"]:
                raise ValueError("Checkpoint resolved-policy SHA differs from catalog")
            if policy_class == "formal" and registry["formal"][policy_id]["state"] != "approved":
                raise ValueError("Formal candidate references an unapproved snapshot")
            # Approved earlier formal snapshots remain valid historical evidence;
            # changing active_formal_id must not relabel their original metrics.
            if (validation_path.name == "summary.json" and
                    row["experiment_id"] in ("EXP-017", "EXP-023")):
                replays = validation["reproductions"]
                matched = [a for a in replays if a["candidate_id"] == candidate_id and
                           a["candidate_path"] == row["checkpoint_path"]]
                if len(matched) != 1 or not matched[0]["reproduction_within_1e-5_db"]:
                    raise ValueError("Missing numerical replay proof")
                metrics = matched[0]["recomputed_metrics_db"]
                for v, key in zip((il, h2, h3), ("worst_IL_db", "min_H2_db", "min_H3_db")):
                    if abs(v - metrics[key]) > METRIC_MATCH_TOLERANCE_DB:
                        raise ValueError("Catalog disagrees with independently recorded replay")
        except (KeyError, TypeError, ValueError, OSError, OverflowError) as exc:
            issues.append(f"{candidate_id}: {exc}")
    return issues


if __name__ == "__main__":
    problems = audit_catalog()
    if problems:
        raise SystemExit("FAILED research catalog:\n- " + "\n- ".join(problems))
    print("PASS: curated research checkpoint paths, policy classes, raw thresholds and source metrics")
