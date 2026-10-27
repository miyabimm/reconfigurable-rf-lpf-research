"""Finite-grid independent RF diagnostics; not a certification or dense run."""
import csv
import math

import numpy as np
from scipy.optimize import minimize_scalar

from ._grid import ROOT, validated_band_segments
from .independent_rf import evaluate_independent_sample


def scan_independent_rf(circuit, vector, *, points_per_interval, coverage="canonical",
                        refine=False, tolerance_hz=1.0):
    """Evaluate canonical case settings or the diagnostic six-setting cross product.

    Local refinement only examines interior sampled extrema. It cannot guarantee
    detection of a feature invisible on the grid, nor continuous-band bounds.
    """
    if type(points_per_interval) is not int or points_per_interval < 2:
        raise ValueError("points_per_interval must be an integer >= 2")
    if coverage not in ("canonical", "cross"):
        raise ValueError("coverage must be canonical or cross")
    if not math.isfinite(tolerance_hz) or tolerance_hz <= 0:
        raise ValueError("tolerance_hz must be positive and finite")
    with (ROOT / "data/bands.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    segments = validated_band_segments(rows)
    full = circuit._adapter.policy["evaluation"]["full_phase2"]
    results = []
    for index, (canonical, role, low, high) in enumerate(segments):
        for setting in (range(6) if coverage == "cross" else (canonical,)):
            frequencies = np.linspace(low * 1e6, high * 1e6, points_per_interval)
            def sample(frequency):
                value = float(evaluate_independent_sample(circuit, vector, frequency, setting)["il_db"])
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
    return {"constraint_id": circuit.policy_id, "coverage": coverage,
            "points_per_interval": points_per_interval, "segments": results,
            "local_extrema_checked": refine, "tolerance_hz": tolerance_hz if refine else None,
            "independent_mna_checked": True, "rf_dense_evaluation_completed": False,
            "finite_grid_only": True, "continuous_band_proven": False,
            "rf_compliance_certified": False, "candidate_promotion_blocked": True}
