"""Finite-grid independent RF diagnostics; not a certification or dense run."""
import csv
import math

import numpy as np
from scipy.optimize import minimize_scalar

from ._grid import ROOT, validated_band_segments
from .independent_rf import evaluate_independent_sample


def scan_independent_rf(circuit, vector, *, points_per_interval, coverage="canonical",
                        refine=False, tolerance_hz=1.0, _sample_observer=None):
    """Evaluate canonical case settings or the diagnostic six-setting cross product.

    Local refinement only examines interior sampled extrema. It cannot guarantee
    detection of a feature invisible on the grid, nor continuous-band bounds.
    """
    if type(points_per_interval) is not int or points_per_interval < 2:
        raise ValueError("points_per_interval must be an integer >= 2")
    if refine and points_per_interval < 3:
        raise ValueError("refinement requires at least 3 points per interval")
    if coverage not in ("canonical", "cross"):
        raise ValueError("coverage must be canonical or cross")
    if not math.isfinite(tolerance_hz) or tolerance_hz <= 0:
        raise ValueError("tolerance_hz must be positive and finite")
    with (ROOT / "rf/bands.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    segments = validated_band_segments(rows)
    full = circuit._adapter.policy["evaluation"]["full_phase2"]
    component = circuit.validate_components(vector)
    results = []
    for index, (canonical, role, low, high) in enumerate(segments):
        for setting in (range(6) if coverage == "cross" else (canonical,)):
            frequencies = np.linspace(low * 1e6, high * 1e6, points_per_interval)
            def sample(frequency):
                result = evaluate_independent_sample(circuit, vector, frequency, setting)
                if _sample_observer is not None:
                    _sample_observer(index, setting, float(frequency), result)
                value = float(result["il_db"])
                if not math.isfinite(value):
                    raise ValueError("Non-finite independent IL")
                return value
            values = [sample(f) for f in frequencies]
            sign = -1 if role == 0 else 1
            best = min(range(len(values)), key=lambda i: sign * values[i])
            grid = {"frequency_hz": float(frequencies[best]), "il_db": values[best]}
            refined = dict(grid)
            extra = 0
            if refine:
                for i in range(1, len(values)-1):
                    if sign*values[i] <= sign*values[i-1] and sign*values[i] <= sign*values[i+1]:
                        def objective(f):
                            nonlocal extra
                            extra += 1
                            return sign * sample(f)
                        result = minimize_scalar(objective, bounds=(frequencies[i-1], frequencies[i+1]),
                                                 method="bounded", options={"xatol": tolerance_hz})
                        if not result.success or not math.isfinite(result.fun):
                            raise ValueError("Local extremum refinement failed")
                        if result.fun < sign * refined["il_db"]:
                            refined = {"frequency_hz": float(result.x), "il_db": float(sign*result.fun)}
            row = rows[index]
            observed = refined["il_db"]
            results.append({"segment": index, "case": row["case"], "region": row["region"],
                            "subband": row.get("note", ""), "setting": setting,
                            "canonical_setting": canonical, "low_hz": low*1e6, "high_hz": high*1e6,
                            "grid_worst": grid, "refined_worst": refined,
                            "additional_evaluations": extra,
                            "mandatory_stop_pass": observed >= full["minimum_h2_h3_db"] if role else None,
                            "nominal_goal_pass": observed >= full["nominal_h2_h3_target_db"] if role else observed <= full["nominal_max_il_db"]})
    # Ties retain CSV segment order, then ascending setting; grid ties retain
    # ascending frequency. Cross summaries never stand in for canonical ones.
    def worst(regions, key, maximize):
        subset = [r for r in results if r['region'] in regions]
        chosen = min(subset, key=lambda r: (-1 if maximize else 1) * r[key]['il_db'])
        return {name: chosen[name] for name in ('segment', 'case', 'region', 'subband', 'setting', 'canonical_setting')} | chosen[key]
    summary = {key: {role: worst(regions, key, maximum) for role, regions, maximum in (
        ('pass_il', ('UL', 'DL'), True), ('UL', ('UL',), True), ('DL', ('DL',), True),
        ('H2', ('H2',), False), ('H3', ('H3',), False))}
        for key in ('grid_worst', 'refined_worst')}
    # These comparisons describe only the selected finite samples. A trial
    # result, even one meeting every numerical target, is not formal compliance.
    observed = summary['refined_worst'] if refine else summary['grid_worst']
    def observation(value, threshold, meets):
        return {"value_db": value, "threshold_db": threshold,
                "status": "sampled_numeric_observation" if meets else "failed"}
    thresholds = {
        region: observation(observed[region]['il_db'], full['nominal_max_il_db'],
                            observed[region]['il_db'] <= full['nominal_max_il_db'])
        for region in ('UL', 'DL')
    }
    for region in ('H2', 'H3'):
        value = observed[region]['il_db']
        thresholds[region] = {
            'mandatory': observation(value, full['minimum_h2_h3_db'],
                                     value >= full['minimum_h2_h3_db']),
            'nominal': observation(value, full['nominal_h2_h3_target_db'],
                                   value >= full['nominal_h2_h3_target_db']),
        }
    return {"constraint_id": circuit.policy_id, "constraint_fingerprint": circuit.policy_fingerprint,
            "coverage": coverage, "summary": summary,
            "threshold_observations": thresholds,
            "threshold_policy_scope": "full_lpf",
            "threshold_evidence_scope": "finite_grid_with_local_refinement" if refine else "finite_grid",
            "component_policy_pass": component['component_policy_pass'],
            "component_policy": component, "forward_sampled_checked": False,
            "points_per_interval": points_per_interval, "segments": results,
            "local_extrema_checked": refine, "tolerance_hz": tolerance_hz if refine else None,
            "independent_mna_checked": True, "rf_dense_evaluation_completed": False,
            "optimization_converged": None, "physical_validation_checked": False,
            "finite_grid_only": True, "continuous_band_proven": False,
            "rf_compliance_certified": False, "candidate_promotion_blocked": True}
