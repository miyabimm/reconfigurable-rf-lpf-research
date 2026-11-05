"""LQP02 series-specific design-Q and inductance bounds for new Phase 2 candidates.

The official machine-readable policy is data/design_constraints.json.
Historical candidates without explicit series labels MUST NOT be silently
certified under a revised component model.
"""
from __future__ import annotations

import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONSTRAINTS = ROOT / "data" / "design_constraints.json"


def load_policy(path: Path | str = CONSTRAINTS) -> dict:
    """Read the active LQP02 family policy (never hardcode legacy Q=25)."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return d["components"]["LQP02"]


def select_series(inductance_nh: float, *, series: str | None = None,
                  policy: dict | None = None) -> dict:
    """Return series and Q for a new inductor design.

    HV is preferred at <=27 nH; HQ is allowed to 56 nH at Q20.
    An explicitly specified HQ at lower values still has Q20.
    This is a constant-Q Phase 2 analysis assumption, not an SRF certificate.
    """
    p = policy if policy is not None else load_policy()
    value = float(inductance_nh)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"Invalid inductance: {inductance_nh!r}")
    series_data = p["series"]
    if series is None:
        hv = series_data["LQP02HV"]
        series = ("LQP02HV" if hv['bounds']['min'] <= value
                  <= hv['bounds']['max'] else "LQP02HQ")
    if series not in series_data:
        raise ValueError(f"Unknown LQP02 series {series!r}")
    spec = series_data[series]
    # SI-H to nH conversion can move exact endpoints by a few ULPs
    # (e.g. 56e-9*1e9 > 56). Tolerate only roundoff, not a real overrun.
    lo = spec['bounds']['min']
    hi = spec['bounds']['max']
    within = (lo <= value <= hi or
              math.isclose(value, lo, rel_tol=1e-13, abs_tol=1e-13) or
              math.isclose(value, hi, rel_tol=1e-13, abs_tol=1e-13))
    if not within:
        raise ValueError(f"{series} cannot use {value} nH; "
                         f"range {spec['bounds']['min']}.."
                         f"{spec['bounds']['max']} nH")
    return {
        "series": series,
        "L_nH": value,
        "Q": spec["q"],
        "area_units": spec["area_units"],
        "preferred_HV_27nH_or_less": series == "LQP02HV",
        "high_inductance_SRF_risk": value > 27,
        "physical_SRF_verified": False,
    }


def audit_saved_candidate(candidate: dict, *, policy: dict | None = None) -> dict:
    """Audit saved numerical assumptions, without altering historical results.

    A missing explicit physical series label always requires migration.
    A historical uniform Q25 with any L>27nH is incompatible with the
    current series-specific Q rule, even if the original MNA was correct.
    """
    p = policy if policy is not None else load_policy()
    components = candidate.get("components", {})
    q_group = components.get("LQP02", {})
    group_q = q_group.get("Q", q_group.get("q")) if isinstance(q_group, dict) else None
    if group_q is None and "LQP02_Q25" in components:
        group_q = 25
    data = candidate.get("topology", {}).get("inductors", [])
    records = []
    for item in data:
        L = item.get("L_nH")
        if L is None:
            continue
        declared = item.get("series")
        q = item.get("Q", group_q)
        try:
            chosen = select_series(L, series=declared, policy=p)
            q_mismatch = q is not None and abs(float(q) - chosen["Q"]) > 1e-9
            status = ("old_Q_incompatible" if q_mismatch
                      else "series_label_missing" if not declared
                      else "model_compatible_srf_unchecked")
            expected = chosen["Q"]
        except (ValueError, TypeError) as exc:
            status, expected = "outside_supported_range", None
            records.append({"id": item.get("id"), "L_nH": L, "status": status,
                            "detail": str(exc)})
            continue
        records.append({"id": item.get("id"), "L_nH": L,
                        "declared_series": declared, "expected_series": chosen["series"],
                        "recorded_Q": q, "expected_Q": expected, "status": status,
                        "SRF_checked": False})
    statuses = {r["status"] for r in records}
    return {
        "candidate_id": candidate.get("id", candidate.get("candidate_id", "unknown")),
        "inductors": records,
        "new_policy_validated": bool(records) and statuses == {"model_compatible_srf_unchecked"},
        "needs_reoptimization": bool({"old_Q_incompatible", "outside_supported_range"} & statuses),
        "needs_series_annotation": "series_label_missing" in statuses,
        "srf_or_implementation_validated": False,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Audit old saved LQP02 candidates")
    parser.add_argument("candidates", nargs="+")
    args = parser.parse_args()
    for name in args.candidates:
        print(json.dumps(audit_saved_candidate(json.loads(Path(name).read_text())),
                         ensure_ascii=False, indent=2))
