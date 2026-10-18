"""Finite-grid Phase 2 trial-only extra stopband check at the external RF ports.

Caller supplies the LPF-only 2-port ABCD matrix for each existing band setting.
RF-F003 fixed input/output S2Ps, source/load and -10log10(Pload/Pavs)
are applied by port_parasitics.external_transducer_gain. No optimization,
EM, continuous-frequency extremum, or independent MNA is performed here.
"""
import math

from .port_parasitics import external_transducer_gain


def evaluate_trial_additional_stopband(policy, make_lpf_abcd):
    """Sweep every required frequency for all six settings; return actual worst.

    The caller must *not* pass a whole-system ABCD matrix: the two immutable
    parasitic S2Ps are cascaded inside external_transducer_gain.
    """
    spec = policy.get("trial_additional_stopband")
    if (policy.get("active_constraint_status") != "trial"
            or not isinstance(spec, dict)
            or spec.get("applicable_objective") != "full_lpf"):
        raise ValueError("No authorized additional full-LPF trial stopband")
    if not callable(make_lpf_abcd):
        raise ValueError("An LPF-only ABCD callback is required")
    freqs = range(spec["low_hz"], spec["high_hz"] + 1, spec["sample_step_hz"])
    points = len(freqs)
    per_setting = {}
    worst = None
    for setting in spec["settings"]:
        lowest = (float("inf"), None)
        for frequency_hz in freqs:
            lpf_abcd = make_lpf_abcd(setting, frequency_hz)
            gain = external_transducer_gain(policy, frequency_hz, lpf_abcd)
            if not math.isfinite(gain) or gain <= 0 or gain > 1 + 1e-8:
                raise ValueError("Invalid external transducer gain during trial stopband")
            attenuation = -10.0 * math.log10(gain)
            if attenuation < lowest[0]:
                lowest = (attenuation, frequency_hz)
        per_setting[setting] = {
            "minimum_attenuation_db": lowest[0],
            "worst_frequency_hz": lowest[1],
            "passes_minimum": lowest[0] >= spec["min_attenuation_db"],
        }
        if worst is None or lowest[0] < worst["minimum_attenuation_db"]:
            worst = {"setting": setting, "frequency_hz": lowest[1],
                     "minimum_attenuation_db": lowest[0]}
    return {
        "constraint_id": policy["active_constraint_id"],
        "minimum_required_db": spec["min_attenuation_db"],
        "frequency_low_hz": spec["low_hz"],
        "frequency_high_hz": spec["high_hz"],
        "step_hz": spec["sample_step_hz"],
        "points_per_setting": points,
        "total_points": points * len(spec["settings"]),
        "settings": per_setting,
        "worst": worst,
        "passes_minimum": worst["minimum_attenuation_db"] >= spec["min_attenuation_db"],
        "finite_grid_only": True,
        "independent_validation": "not_run",
    }


def summarize_full_lpf_trial_feasibility(policy, *, worst_il_db, min_h2_db,
                                        min_h3_db, additional_stopband=None):
    """Do not allow an RF-T006 pass based solely on historical H2/H3 results."""
    for val in (worst_il_db, min_h2_db, min_h3_db):
        if type(val) not in (int, float) or not math.isfinite(val):
            raise ValueError("Full-LPF metrics must be finite")
    full = policy["evaluation"]["full_phase2"]
    inherited_ok = min_h2_db >= full["minimum_h2_h3_db"] and min_h3_db >= full["minimum_h2_h3_db"]
    extra_spec = policy.get("trial_additional_stopband")
    if extra_spec is not None:
        if (not isinstance(additional_stopband, dict)
                or additional_stopband.get("constraint_id") != policy["active_constraint_id"]
                or additional_stopband.get("minimum_required_db") != extra_spec["min_attenuation_db"]
                or additional_stopband.get("frequency_low_hz") != extra_spec["low_hz"]
                or additional_stopband.get("frequency_high_hz") != extra_spec["high_hz"]
                or additional_stopband.get("step_hz") != extra_spec["sample_step_hz"]
                or additional_stopband.get("points_per_setting") != (
                    (extra_spec["high_hz"] - extra_spec["low_hz"]) // extra_spec["sample_step_hz"] + 1)
                or set(additional_stopband.get("settings", {})) != set(extra_spec["settings"])
                or additional_stopband.get("finite_grid_only") is not True
                or type(additional_stopband.get("passes_minimum")) is not bool):
            raise ValueError("Complete RF-T006 stopband evidence is required")
        wideband_ok = additional_stopband["passes_minimum"]
    else:
        if additional_stopband is not None:
            raise ValueError("Unexpected additional trial stopband evidence")
        wideband_ok = None
    return {
        "constraint_id": policy["active_constraint_id"],
        "h2_h3_mandatory_pass": inherited_ok,
        "additional_stopband_mandatory_pass": wideband_ok,
        "mandatory_finite_grid_pass": inherited_ok and wideband_ok is not False,
        "nominal_il_goal_pass": worst_il_db <= full["nominal_max_il_db"],
        "nominal_h2_h3_goal_pass": (
            min_h2_db >= full["nominal_h2_h3_target_db"]
            and min_h3_db >= full["nominal_h2_h3_target_db"]),
        "continuous_band_proven": False,
    }
