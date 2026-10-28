#!/usr/bin/env python3
"""Lightweight metadata audit of active Phase 2 policy, bands and candidates.

Not an EM verification or a substitute for numerical circuit regression.
LPF-007/008 remain mandatory baseline entries; additional current-policy
candidates can be registered without changing this script.
"""
import csv
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.lpf.experiment_manifest import audit_provenance
from src.lpf.constraint_versions import load_constraint, validate_registry, rf_input_file
CASES = ("B71", "B12", "B28", "B13+B14", "B26", "B8")
REQUIRED_BASELINES = {"LPF-007", "LPF-008"}


def read_csv(path):
    with (ROOT / path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def audit(detail=False):
    issues = []
    policy = load_constraint()
    if policy.get("phase3") != "paused_until_explicit_owner_approval":
        issues.append("Phase 3 unexpectedly enabled")
    if policy["area_budget"]["hard_cap"] is not None:
        issues.append("Formal RF policy unexpectedly imposes a chip-area cap")
    registry = validate_registry()
    if registry["active_formal_id"] != policy.get("active_constraint_id"):
        issues.append("Active formal constraint version mismatch")
    if policy.get("canonical_docs") not in {
        "docs/specification.md", "project/specification.md"
    }:
        issues.append("Unrecognized specification reference in immutable RF policy")
    if not (ROOT / "project/specification.md").is_file():
        issues.append("Current specification document missing")
    if not (ROOT / "docs/historical_results.md").is_file():
        issues.append("Historical research index missing")

    with rf_input_file(ROOT, policy["bands_file"]).open(newline="", encoding="utf-8") as handle:
        bands = list(csv.DictReader(handle))
    for case in CASES:
        for region in ("UL", "DL", "H2", "H3"):
            if not any(x["case"] == case and x["region"] == region for x in bands):
                issues.append(f"Missing {case}/{region}")
        ul = [x for x in bands if x["case"] == case and x["region"] == "UL"]
        for multiple, region in ((2, "H2"), (3, "H3")):
            harmonics = [x for x in bands if x["case"] == case and x["region"] == region]
            if len(ul) != len(harmonics):
                issues.append(f"Invalid {case}/{region} segment count")
                continue
            for a, b in zip(ul, harmonics):
                for end in ("low_mhz", "high_mhz"):
                    if abs(float(b[end]) - multiple * float(a[end])) > 1e-8:
                        issues.append(f"Invalid {case}/{region}/{end}")

    index = read_csv("data/candidate_index.csv")
    ids = [row["candidate_id"] for row in index]
    seen = set()
    for name in ids:
        if name in seen:
            issues.append(f"Duplicate candidate in index: {name}")
        seen.add(name)
    for name in sorted(REQUIRED_BASELINES - seen):
        issues.append(f"Required baseline missing: {name}")

    for row in index:
        name = row["candidate_id"]
        # Avoid path traversal when interpreting the machine-readable index.
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            issues.append(f"Invalid candidate ID: {name}")
            continue
        path = ROOT / "candidates" / (name + ".json")
        if not path.is_file():
            issues.append(f"Candidate JSON missing: {name}")
            continue
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
            if item["candidate_id"] != name or item["objective"] != row["objective"]:
                issues.append(f"Candidate identity or objective mismatch: {name}")
            if row["objective"] != "full_lpf":
                issues.append(f"Active candidate is not full_lpf: {name}")
            if row.get("constraint_class") == "historical":
                # Immutable legacy entries are audited against their own
                # recorded policy epoch, NEVER reclassified to active RF-F003.
                historical_key = row.get("historical_registry_key")
                if not historical_key or historical_key not in registry["historical"]:
                    issues.append(f"Missing historical registry identity: {name}")
                    continue
                expected_spec = registry["historical"][historical_key]["policy_version"]
            else:
                expected_spec = row["constraint_id"]
                if not expected_spec:
                    issues.append("Versioned candidate has no constraint ID: " + name)
                    continue
            if item["spec_id"] != expected_spec or row["spec_id"] != expected_spec:
                issues.append(f"Candidate spec mismatch: {name}")
            perf = item["performance"]
            for col, key in (("max_il_db", "worst_IL_db"),
                             ("min_h2_db", "min_H2_db"),
                             ("min_h3_db", "min_H3_db")):
                a, b = float(row[col]), float(perf[key])
                if not math.isfinite(a) or not math.isfinite(b) or abs(a - b) > 1e-6:
                    issues.append(f"Candidate performance mismatch: {name} {key}")
            area = float(item["area_units"])
            if not math.isfinite(area) or area < 0:
                issues.append(f"Candidate area cap exceeded: {name}")
            variable_caps = item["topology"]["variable_caps"]
            bound_policy = (load_constraint("RF-F001") if row.get("constraint_class") == "historical"
                            else load_constraint(row["constraint_id"],
                                                 allow_trial=row.get("constraint_class") == "trial"))
            cpolicy = bound_policy["components"]["IC_VARIABLE_C"]
            if len(variable_caps) > cpolicy["max_branches_principle"]:
                issues.append(f"Candidate variable C count exceeded: {name}")
            for cap in variable_caps:
                if (cap["b"] != 0 or cap["Q"] != cpolicy["q"] or
                    cap["min_pF"] < cpolicy["min_total_variable_pf_per_branch"] or
                    cap["max_pF"] > cpolicy["max_total_variable_pf_per_branch"]):
                    issues.append(f"Candidate variable C policy mismatch: {name}")
            settings = item["ic_variable_C_pf_by_setting"]
            if set(settings) != set(CASES):
                issues.append(f"Candidate setting list mismatch: {name}")
            for case, cc in settings.items():
                if len(cc) != len(variable_caps) or any(
                    not math.isfinite(float(v)) or
                    float(v) < cpolicy["min_total_variable_pf_per_branch"] or
                    float(v) > cpolicy["max_total_variable_pf_per_branch"] for v in cc
                ):
                    issues.append(f"Candidate variable C values invalid: {name}/{case}")
            if row["evidence"] != "candidates/" + name + ".json":
                issues.append(f"Candidate index evidence path mismatch: {name}")
            if row["status"] != "grid_verified_nonconverged_IL_target_fail" and name in REQUIRED_BASELINES:
                issues.append(f"Baseline verification label changed: {name}")
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            issues.append(f"Invalid candidate schema: {name}: {exc}")

    issues.extend(audit_provenance(root=ROOT))

    if detail:
        print("Cases:", len(CASES), "band segments:", len(bands),
              "active candidates:", len(index))
    return issues


if __name__ == "__main__":
    errors = audit(detail=True)
    if errors:
        raise SystemExit("FAILED:\n- " + "\n- ".join(errors))
    print("PASS: active policy, band definitions, baseline presence, candidate metadata and experiment provenance")
