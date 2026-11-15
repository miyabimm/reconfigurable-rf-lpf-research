#!/usr/bin/env python3
"""Read-only curation of persisted Issue #439 results; does not call RF/MNA/solver."""
import hashlib
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "project/diagnostics/issue439"
PRE = OUT / "preflight.json"
INITIAL = OUT / "initial_evaluations.json"
EXECUTION = OUT / "execution.json"
RESULTS = OUT / "results.json"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def main():
    pre = read_json(PRE)
    initial = read_json(INITIAL)
    execution = read_json(EXECUTION)
    report = read_json(RESULTS)
    assert len(execution["rows"]) == 20
    assert [row["seed"] for row in execution["rows"]] == list(range(1001, 1021))
    assert all(row["status"] == "complete" for row in execution["rows"])
    assert execution["preflight_sha256"] == digest(PRE)
    assert execution["source_provenance_sha256"] == digest(OUT / "source_provenance.json")
    report_by_seed = {row["seed"]: row for row in report["seeds"]}
    mna_spots = 0
    job_primary = 0
    job_search = 0
    target30_search = nominal35_search = 0
    target30_terminal = nominal35_terminal = 0

    for run in execution["rows"]:
        seed = run["seed"]
        raw_path = Path(run["output"])
        raw_result_path = raw_path / "result.json"
        raw_input_path = raw_path / "input.json"
        raw = read_json(raw_result_path)
        inp = read_json(raw_input_path)
        row = report_by_seed[seed]
        terminal = raw["terminal"]["candidates"][0]
        assessment = terminal["assessment"]
        observations = {"H2": [], "H3": []}
        interval_rows = []
        interval_ids = set()
        cases = set()
        regions = set()
        mandatory_pass = True
        nominal_harmonic_pass = True
        for item in assessment["rows"]:
            req = item["requirement"]
            interval = req["interval"]
            region = interval["region"]
            case = interval["case"]
            level = req["level"]
            interval_ids.add(interval["identity"])
            cases.add(case)
            regions.add(region)
            if region in observations:
                observations[region].extend(item["observations_db"])
                if level == "nominal" and not item["passed"]:
                    nominal_harmonic_pass = False
            if level == "mandatory" and not item["passed"]:
                mandatory_pass = False
            if assessment["strict_feasible"]:
                interval_rows.append(dict(
                    interval_identity=interval["identity"], csv_line=interval["csv_line"],
                    case=case, region=region, interval_type=interval["type"],
                    low_hz=interval["low_hz"], high_hz=interval["high_hz"],
                    level=level, metric=req["metric"], bound=req["bound"], threshold_db=req["threshold_db"],
                    passed=item["passed"], violation_db=item["violation_db"],
                    worst_observation_db=item["worst_observation_db"],
                    worst_frequency_hz=item["worst_frequency_hz"],
                    samples_checked=len(item["observations_db"])))
            else:
                interval_rows.append([interval["identity"], level, item["passed"], item["violation_db"]])
        if len(interval_ids) != 28 or len(cases) != 6 or not {"UL", "DL", "H2", "H3"}.issubset(regions):
            raise SystemExit(f"STOP: terminal grid evidence is not all six settings / 28 intervals: seed {seed}")
        if mandatory_pass != assessment["strict_feasible"]:
            raise SystemExit(f"STOP: strict mandatory summary mismatch: seed {seed}")
        minima = dict(min_h2_db=min(observations["H2"]), min_h3_db=min(observations["H3"]))
        target30 = minima["min_h2_db"] >= 30.01 and minima["min_h3_db"] >= 30.01
        nominal35 = nominal_harmonic_pass
        row["terminal_min_harmonics"] = minima
        row["terminal_target_30_01"] = target30
        row["terminal_nominal_35db_harmonics"] = nominal35
        row["terminal_interval_requirements"] = interval_rows
        row["terminal_unique_intervals_checked"] = len(interval_ids)
        row["terminal_settings_checked"] = len(cases)
        row["terminal_requirement_rows_checked"] = len(interval_rows)

        initial_metrics = row["initial_metrics"]
        initial_metrics["nominal_35db_harmonics"] = (
            initial_metrics["min_h2_db"] >= 35.0 and initial_metrics["min_h3_db"] >= 35.0)
        best_metrics = row["best_metrics_70"]
        best_metrics["nominal_35db_harmonics"] = (
            best_metrics["min_h2_db"] >= 35.0 and best_metrics["min_h3_db"] >= 35.0)
        target30_search += bool(best_metrics["target_30_01"])
        nominal35_search += best_metrics["nominal_35db_harmonics"]
        target30_terminal += target30
        nominal35_terminal += nominal35

        resources = run["resources"]
        gnu_wall = resources.get("elapsed_wall_seconds")
        if gnu_wall is None:
            raise SystemExit(f"STOP: missing GNU time wall value for seed {seed}")
        # Seeds 1001-1003 were reconciled from raw GNU time logs after a wrapper
        # bookkeeping exception; their outer monotonic wall measurement was not preserved.
        outer_wall = None if seed <= 1003 else run.get("measured_wall_seconds")
        selected_wall = gnu_wall if seed <= 1003 else outer_wall
        row["wall_seconds"] = selected_wall
        row["gnu_time_wall_seconds"] = gnu_wall
        row["gnu_time_wall_valid"] = gnu_wall >= 0
        row["orchestrator_wall_seconds"] = outer_wall
        row["wall_measurement_scope"] = ("GNU /usr/bin/time elapsed around uv + Worker; outer monotonic wall not preserved"
                                         if seed <= 1003 else
                                         "Python time.monotonic around subprocess (includes /usr/bin/time + uv + Worker)")
        row["cpu_user_seconds"] = resources.get("user_seconds")
        row["cpu_system_seconds"] = resources.get("system_seconds")
        row["cpu_user_plus_system_seconds"] = resources.get("user_seconds", 0.0) + resources.get("system_seconds", 0.0)
        row["max_rss_kib"] = resources.get("max_rss_kib")
        row["source_identity_sha256"] = inp["source_sha256"]
        row["input_sha256"] = digest(raw_input_path)
        row["result_sha256"] = digest(raw_result_path)
        row["stdout_sha256"] = run["stdout_sha256"]
        row["resources_sha256"] = run["resources_sha256"]
        mna_spots += len(terminal["independent"].get("sample_indices", []))
        job_primary += sum(raw["costs"][key] for key in
                           ("search_requested_samples", "selection_requested_samples", "terminal_requested_samples"))
        job_search += raw["steps"][0]["solver_result"]["nfev"]

    for dense in report["dense_validation"]:
        metrics = dense["dense1001"]
        metrics["nominal_35db_harmonics"] = metrics["min_h2_db"] >= 35 and metrics["min_h3_db"] >= 35
        dense["terminal_target_30_01"] = (
            dense["terminal_worst_il_db"] is not None and
            report_by_seed[dense["seed"]]["terminal_target_30_01"])

    report["terminal_interval_evidence_schema"] = {
        "compact_nonpass_rows": ["interval_identity", "level", "passed", "violation_db"],
        "strict_candidate_rows": "full object with CSV identity, case/region/type, interval bounds, metric/limit, pass/violation, worst sample and sample count",
        "full_detail_strict_terminal_seed_ids": [r["seed"] for r in report["seeds"] if r["terminal_strict30"]]
    }
    report["rates"].update(
        search_target_30_01=target30_search,
        terminal_target_30_01=target30_terminal,
        search_nominal_35db=nominal35_search,
        terminal_nominal_35db=nominal35_terminal,
        terminal_nominal_35db_harmonics_definition="all nominal H2/H3 requirement rows pass on 17-point terminal grid")
    report["samples"].update(primary_initial=initial["primary_requested_completed_samples"],
                             primary_jobs=job_primary, independent_mna_spot_samples=mna_spots,
                             independent_mna_total=mna_spots+report["samples"]["independent_mna_dense84_samples"])
    report["search_forwards"]["total"] = job_search
    report["evaluation_script_sha256"] = digest(OUT / "evaluate.py")
    report["postprocess_script_sha256"] = digest(OUT / "summarize.py")
    report["postprocess_rf_forwards"] = 0
    report["source_identity_sha256"] = execution["rows"][0]["summary"]["source_sha256"]
    report["notes"] = [
        "For each seed, the final best-J search vector was independently reread on the same 70-sample grid as the initial start; those 20x70 readbacks are included in primary sample accounting.",
        "Terminal assessment includes all six settings and 28 separate UL/DL/H2/H3 intervals; per-requirement rows were curated from the persisted Worker result without new RF forwards.",
        "Additional post-search interval-summary curation performs zero RF forwards; dense/MNA requested sample accounting is recorded separately.",
        "The initial preflight was augmented before search with full hard bounds/physical reports; vector/config/start byte fingerprints and the 1,400 initial evaluation outputs were verified unchanged, without repeating RF evaluation.",
        "Seed 1001 Worker completed normally; the first wrapper raised after completion during summary aggregation. Persisted files were reconciled and validated without retry or resume.",
        "Seeds 1001-1003 outer monotonic wall values were not preserved; GNU time raw values are reported. Seeds 1004-1020 use the wrapper's monotonic wall. GNU time for seed 1015 reported an invalid negative elapsed value (-1.88 s); it is retained as raw diagnostic only and not used for the selected wall statistic."
    ]
    primary_total = (initial["primary_requested_completed_samples"] + job_primary
                    + report["samples"]["primary_best_70_readbacks"]
                    + report["samples"]["primary_dense_and_mna_comparisons"])
    report["samples"]["primary_total"] = primary_total
    report["samples"]["search_forward_cap"] = 3_000_000
    if (primary_total > report["samples"]["primary_cap"] or job_search > 3_000_000
            or report["samples"]["independent_mna_total"] > report["samples"]["independent_mna_cap"]):
        raise SystemExit("STOP: postprocessed sample accounting exceeds the Issue cap")

    execution["phase"] = "complete"
    execution["checkpoint_sha_lists_curated_to"] = "results.json per-seed rows; execution.json omits duplicate arrays"
    for run in execution["rows"]:
        run["summary"].pop("checkpoints", None)
        run["checkpoint_sha_list_path"] = f"results.json#seeds/{run['seed']}/checkpoints"
    execution["post_search_validation"] = dict(
        completed_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        final_best_same_grid_readbacks=20, final_best_same_grid_primary_samples=report["samples"]["primary_best_70_readbacks"],
        dense_candidates=len(report["dense_validation"]),
        dense_primary_samples=sum(28_028 for _ in report["dense_validation"]),
        dense_mna_comparison_primary_samples=report["samples"]["independent_mna_dense84_samples"],
        dense_independent_mna_samples=report["samples"]["independent_mna_dense84_samples"],
        independent_mna_terminal_spots=mna_spots,
        independent_mna_total=report["samples"]["independent_mna_total"],
        primary_total=primary_total, search_forwards=job_search,
        all_20_jobs_complete=True, no_retry_resume_or_extra_seed=True)
    execution["primary_samples_post_search_best_readbacks"] = report["samples"]["primary_best_70_readbacks"]
    execution["primary_samples_final_dense_and_mna_comparisons"] = report["samples"]["primary_dense_and_mna_comparisons"]
    execution["primary_samples_total_actual"] = primary_total
    execution["independent_mna_samples_total_actual"] = report["samples"]["independent_mna_total"]
    execution["search_forwards_total_actual"] = job_search
    write_json(EXECUTION, execution)
    report["execution_sha256"] = digest(EXECUTION)
    write_json(RESULTS, report)
    print(json.dumps(dict(results_sha256=digest(RESULTS), execution_sha256=digest(EXECUTION),
                          rates=report["rates"], samples=report["samples"],
                          intervals_per_terminal=[row["terminal_unique_intervals_checked"] for row in report["seeds"]]),
                     indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
