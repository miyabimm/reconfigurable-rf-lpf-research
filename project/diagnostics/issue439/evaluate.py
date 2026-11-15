#!/usr/bin/env python3
"""Bounded read-only RF scoring and final finite-grid validation for Issue #439."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from lpf.constraint_versions import constraint_fingerprint, load_constraint, rf_input_file
from lpf.rf_core import build_rf_model
from lpf.rf_core.independent import validate_response
from lpf.search.component_constraints import validate_values
from lpf.search.performance import (build_evaluation_grid, compile_requirements,
                                    evaluate_requirements, grid_fingerprint)
from lpf.search.proposals import definition_from_data
from lpf.search.storage import sha, vector_sha
from lpf.search.starts import load_explicit

OUT = ROOT / "project/diagnostics/issue439"
PRE = OUT / "preflight.json"
RF_SHA = "e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532"
BASE_IL = 0.8278411484628502
SEEDS = list(range(1001, 1021))


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def context():
    pre = json.loads(PRE.read_text())
    policy = load_constraint("RF-T008", root=ROOT, allow_trial=True)
    if constraint_fingerprint(policy) != RF_SHA or pre["rf"]["effective_sha256"] != RF_SHA:
        raise SystemExit("STOP: RF-T008 fingerprint mismatch")
    definition_data = json.loads((ROOT / pre["definition"]["path"]).read_bytes())
    if file_sha(ROOT / pre["definition"]["path"]) != pre["definition"]["byte_sha256"] or sha(definition_data) != pre["definition"]["canonical_sha256"]:
        raise SystemExit("STOP: definition fingerprint mismatch")
    definition = definition_from_data(definition_data)
    model = build_rf_model(definition, policy)
    bands = rf_input_file(ROOT, policy["bands_file"])
    req = compile_requirements(policy, bands, "full_lpf")
    if len(req.intervals) != 28 or len({r.case for r in req.intervals}) != 6:
        raise SystemExit("STOP: expected all six settings / 28 separate intervals")
    grids = {
        "search70": build_evaluation_grid(req, 2, 3),
        "selection84": build_evaluation_grid(req, 3),
        "terminal476": build_evaluation_grid(req, 17),
        "dense28028": build_evaluation_grid(req, 1001),
    }
    expected = {"search70": 70, "selection84": 84, "terminal476": 476, "dense28028": 28028}
    for name, n in expected.items():
        if len(grids[name].frequency_hz) != n:
            raise SystemExit(f"STOP: {name} expected {n} samples")
    return pre, policy, model, req, grids


def score(vector, policy, model, req, grid):
    physical = validate_values(model.definition, model.schema, vector, policy, frozen_model=model)
    response = model.evaluator(grid).evaluate(vector)
    assessment = evaluate_requirements(response, req, requested_grid=grid)
    h_ix = np.flatnonzero(np.isin(grid.segment, [i.segment for i in req.intervals if i.region in ("H2", "H3")]))
    h2_ix = np.flatnonzero(np.isin(grid.segment, [i.segment for i in req.intervals if i.region == "H2"]))
    h3_ix = np.flatnonzero(np.isin(grid.segment, [i.segment for i in req.intervals if i.region == "H3"]))
    h = response.il_db[h_ix]
    il_term = max(0.0, assessment["worst_il_db"] - 0.30) ** 2
    h_term = float(100.0 * np.mean(np.maximum(0.0, 30.01 - h) ** 2))
    settings = {}
    for interval in req.intervals:
        ix = np.flatnonzero(grid.segment == interval.segment)
        row = settings.setdefault(interval.case, {"worst_pass_il_db": None, "min_h2_db": None, "min_h3_db": None})
        if interval.region in ("UL", "DL"):
            value = float(np.max(response.il_db[ix]))
            row["worst_pass_il_db"] = value if row["worst_pass_il_db"] is None else max(row["worst_pass_il_db"], value)
        elif interval.region in ("H2", "H3"):
            key = "min_" + interval.region.lower() + "_db"
            value = float(np.min(response.il_db[ix]))
            row[key] = value if row[key] is None else min(row[key], value)
    return dict(vector_sha256=vector_sha(vector), samples=len(grid.frequency_hz),
                grid_sha256=grid_fingerprint(grid), strict_feasible=assessment["strict_feasible"],
                worst_il_db=assessment["worst_il_db"], max_violation_db=assessment["max_violation_db"],
                sum_violation_db=assessment["sum_violation_db"], min_h2_db=float(np.min(response.il_db[h2_ix])),
                min_h3_db=float(np.min(response.il_db[h3_ix]),), objective_j=il_term+h_term,
                il_term=il_term, harmonic_term=h_term, target_30_01=bool(np.all(h >= 30.01)),
                settings=settings, physical=physical, response=response, assessment=assessment)


def initial():
    pre, policy, model, req, grids = context()
    rows = []
    requested = 0
    for item in pre["starts"]:
        seed = item["seed"]
        if item["status"] != "legal":
            rows.append(dict(seed=seed, status="invalid_start_not_run", reason=item.get("reason"),
                             vector=item.get("vector"), vector_sha256=item.get("vector_sha256")))
            continue
        explicit = load_explicit(OUT / "inputs" / f"seed-{seed}-starts.json")[seed]
        if explicit["vector_sha256"] != item["vector_sha256"] or explicit["vector"] != item["vector"]:
            raise SystemExit(f"STOP: frozen start mismatch at seed {seed}")
        result = score(explicit["vector"], policy, model, req, grids["search70"])
        if result["vector_sha256"] != item["vector_sha256"]:
            raise SystemExit(f"STOP: start SHA mismatch at seed {seed}")
        rows.append(dict(seed=seed, status="completed", vector=explicit["vector"],
                         vector_sha256=explicit["vector_sha256"], metrics={k:v for k,v in result.items() if k not in ("response", "assessment")}))
        requested += 70
        write_json(OUT / "initial_evaluations.progress.json", dict(rows=rows, requested_completed_samples=requested))
    expected_legal = sum(x["status"] == "legal" for x in pre["starts"])
    if sum(x["status"] == "completed" for x in rows) != expected_legal or requested != expected_legal * 70:
        raise SystemExit("STOP: initial-point finite-grid read-only evaluation incomplete")
    result = dict(kind="issue439_initial_read_only", source_head=pre["source_head"],
                  preflight_sha256=file_sha(PRE), rf_constraint_id="RF-T008", rf_effective_sha256=RF_SHA,
                  samples_per_start=70, grid_sha256=grid_fingerprint(grids["search70"]), rows=rows,
                  proposed_seed_count=20, legal_seed_count=expected_legal, invalid_seed_count=20-expected_legal,
                  primary_requested_completed_samples=requested,
                  purpose="same 70-sample grid J/IL/H2/H3 baseline before optimization; no solver")
    write_json(OUT / "initial_evaluations.json", result)
    (OUT / "initial_evaluations.progress.json").unlink(missing_ok=True)
    print(json.dumps({"legal": expected_legal, "invalid": 20-expected_legal,
                      "primary_requested_completed_samples": requested,
                      "seed_metrics": [{"seed": r["seed"], "j": r.get("metrics", {}).get("objective_j"),
                                        "strict": r.get("metrics", {}).get("strict_feasible"),
                                        "il": r.get("metrics", {}).get("worst_il_db"),
                                        "min_h2": r.get("metrics", {}).get("min_h2_db"),
                                        "min_h3": r.get("metrics", {}).get("min_h3_db")} for r in rows]},
                     indent=2, allow_nan=False))


def _terminal_harmonic_minima(assessment):
    values = {"H2": [], "H3": []}
    for row in assessment["rows"]:
        interval = row["requirement"]["interval"]
        region = interval["region"]
        if region in values:
            values[region].extend(row["observations_db"])
    return {"min_h2_db": min(values["H2"]), "min_h3_db": min(values["H3"])}


def finalize(execution_path: Path):
    pre, policy, model, req, grids = context()
    initial_data = json.loads((OUT / "initial_evaluations.json").read_text())
    execution = json.loads(execution_path.read_text())
    if execution["source_head"] != pre["source_head"] or execution["preflight_sha256"] != file_sha(PRE):
        raise SystemExit("STOP: execution/preflight identity mismatch")
    initial_by_seed = {row["seed"]: row for row in initial_data["rows"]}
    records, eligible = [], []
    total_job_primary = 0
    total_search = 0
    mna_spot_samples = 0
    for seed_info in pre["starts"]:
        seed = seed_info["seed"]
        if seed_info["status"] != "legal":
            records.append(dict(seed=seed, status="invalid_start_not_run", reason=seed_info.get("reason")))
            continue
        run = next((r for r in execution["rows"] if r["seed"] == seed), None)
        if run is None:
            records.append(dict(seed=seed, status="not_run"))
            continue
        if run["status"] != "complete":
            records.append(dict(seed=seed, status=run["status"], validation_error=run.get("validation_error"),
                                output=run.get("output")))
            continue
        output = Path(run["output"])
        raw = json.loads((output / "result.json").read_text())
        input_record = json.loads((output / "input.json").read_text())
        step, best = raw["steps"][0], raw["steps"][0]["rf_best"]
        terminal = raw["terminal"]["candidates"][0]
        assessment = terminal["assessment"]
        minima = _terminal_harmonic_minima(assessment)
        init = initial_by_seed[seed]["metrics"]
        strict = bool(assessment["strict_feasible"])
        il = float(assessment["worst_il_db"])
        row = dict(seed=seed, status=raw["status"], converged=bool(step["converged"]),
                   solver_success=bool(step["solver_result"]["runs"][0]["success"]),
                   solver_status=step["solver_result"]["runs"][0]["status"],
                   stop_reason=step["stop_reason"], nfev=step["solver_result"]["nfev"],
                   nit=step["solver_result"]["runs"][0]["nit"],
                   start_vector_sha256=seed_info["vector_sha256"], initial_metrics=init,
                   best_j=best["objective_j"], best_vector=best["vector"],
                   best_vector_sha256=best["vector_sha256"], best_metrics_70=dict(
                       worst_il_db=best["worst_il_db"], max_violation_db=best["max_violation_db"],
                       sum_violation_db=best["sum_violation_db"]),
                   terminal_vector_sha256=terminal["vector_sha256"], terminal_strict30=strict,
                   terminal_worst_il_db=il, terminal_min_harmonics=minima,
                   terminal_max_violation_db=assessment["max_violation_db"],
                   terminal_sum_violation_db=assessment["sum_violation_db"],
                   terminal_mna_spot=terminal["independent"],
                   delta_il_db=il-BASE_IL,
                   within_plus_0_02=bool(strict and il <= BASE_IL+0.02),
                   within_plus_0_05=bool(strict and il <= BASE_IL+0.05),
                   converged_strict_plus_0_02=bool(step["converged"] and strict and il <= BASE_IL+0.02),
                   requested_samples=raw["costs"], output=str(output),
                   input_sha256=run["summary"]["input_sha256"], result_sha256=run["summary"]["result_sha256"],
                   checkpoints=run["summary"]["checkpoints"], wall_seconds=run["measured_wall_seconds"],
                   cpu_user_seconds=run["resources"].get("user_seconds"),
                   cpu_system_seconds=run["resources"].get("system_seconds"),
                   max_rss_kib=run["resources"].get("max_rss_kib"), plan_sha256=input_record["plan_sha256"])
        records.append(row)
        total_job_primary += sum(raw["costs"][key] for key in ("search_requested_samples", "selection_requested_samples", "terminal_requested_samples"))
        total_search += row["nfev"]
        mna_spot_samples += sum(raw["costs"]["independent_mna_samples_by_stage"].values())
        if strict:
            eligible.append((il, terminal["vector_sha256"], seed, row))

    selected = sorted(eligible, key=lambda x: (x[0], x[1]))[:5]
    dense_results = []
    dense_primary = 0
    dense_mna = 0
    for il, vector_digest, seed, row in selected:
        vector = row["best_vector"]
        dense = score(vector, policy, model, req, grids["dense28028"])
        mna_eval = score(vector, policy, model, req, grids["selection84"])
        mna = validate_response(model, vector, mna_eval["response"])
        if vector_sha(vector) != vector_digest:
            raise SystemExit("STOP: selected vector SHA mismatch")
        if dense["strict_feasible"] is not None and not isinstance(dense["strict_feasible"], bool):
            raise SystemExit("STOP: malformed dense strict result")
        dense_results.append(dict(seed=seed, vector_sha256=vector_digest,
                                  terminal_worst_il_db=il, dense1001={k:v for k,v in dense.items() if k not in ("response", "assessment")},
                                  independent_mna84=mna,
                                  independent_mna_samples=84,
                                  validation_limitations="finite 1001-point-per-interval grid and 84 independent MNA samples only"))
        dense_primary += 28028 + 84
        dense_mna += 84

    initial_primary = initial_data["primary_requested_completed_samples"]
    primary_total = initial_primary + total_job_primary + dense_primary
    if total_search > 3_000_000 or primary_total > 211_000_000 or mna_spot_samples + dense_mna > 460:
        raise SystemExit("STOP: Issue #439 forward/sample budget exceeded")
    converged = [r for r in records if r.get("converged")]
    executed = [r for r in records if "nfev" in r]
    strict_rows = [r for r in executed if r["terminal_strict30"]]
    plus02 = [r for r in executed if r["within_plus_0_02"]]
    plus05 = [r for r in executed if r["within_plus_0_05"]]
    all20 = len(records)
    report = dict(
        issue=439, source_head=pre["source_head"], rf=pre["rf"], definition=pre["definition"],
        preflight_sha256=file_sha(PRE), initial_evaluations_sha256=file_sha(OUT / "initial_evaluations.json"),
        execution_sha256=file_sha(execution_path), baseline_reference=dict(source="Issue #437 / EXP-062 existing; not rerun",
            terminal17_worst_il_db=BASE_IL, dense1001_strict30="PASS in existing record"),
        seeds=records, dense_validation=dense_results,
        rates=dict(proposed_seeds=all20, legal_starts=sum(s["status"]=="legal" for s in pre["starts"]),
                   executed=len(executed), converged=len(converged), converged_over_20=len(converged)/20,
                   converged_over_legal=(len(converged)/len([s for s in pre["starts"] if s["status"]=="legal"]) if any(s["status"]=="legal" for s in pre["starts"]) else None),
                   strict30=len(strict_rows), strict30_over_20=len(strict_rows)/20,
                   strict30_over_legal=(len(strict_rows)/len([s for s in pre["starts"] if s["status"]=="legal"]) if any(s["status"]=="legal" for s in pre["starts"]) else None),
                   plus_0_02=len(plus02), plus_0_05=len(plus05),
                   converged_and_strict_and_plus_0_02=sum(r["converged_strict_plus_0_02"] for r in executed)),
        search_forwards=dict(total=total_search, min=(min(r["nfev"] for r in executed) if executed else None),
                             median=(float(np.median([r["nfev"] for r in executed])) if executed else None),
                             max=(max(r["nfev"] for r in executed) if executed else None), cap=3_000_000),
        samples=dict(primary_initial=initial_primary, primary_jobs=total_job_primary,
                     primary_dense_and_mna_comparisons=dense_primary, primary_total=primary_total,
                     primary_cap=211_000_000, independent_mna_spot_samples=mna_spot_samples,
                     independent_mna_dense84_samples=dense_mna, independent_mna_total=mna_spot_samples+dense_mna,
                     independent_mna_cap=460),
        status_counts={s:sum(r.get("status")==s for r in records) for s in
                       ("converged", "not_converged", "invalid_start_not_run", "not_run", "stop_unknown")},
        limitations=["finite grids only; no continuous-band guarantee", "no EM/Q(f)/SRF/tolerance/measurement validation",
                     "bounded multi-seed evidence, not a global optimum proof", "RF-T008 trial full_lpf, not formal RF-F003"])
    write_json(OUT / "results.json", report)
    print(json.dumps(dict(rates=report["rates"], search_forwards=report["search_forwards"],
                          samples=report["samples"], dense=[dict(seed=r["seed"], strict=r["dense1001"]["strict_feasible"],
                          worst_il_db=r["dense1001"]["worst_il_db"], min_h2_db=r["dense1001"]["min_h2_db"],
                          min_h3_db=r["dense1001"]["min_h3_db"], mna=r["independent_mna84"].get("status")) for r in dense_results]),
                     indent=2, allow_nan=False))


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("initial", "finalize"):
        raise SystemExit("usage: evaluate.py initial | finalize")
    if sys.argv[1] == "initial":
        initial()
    else:
        finalize(OUT / "execution.json")
