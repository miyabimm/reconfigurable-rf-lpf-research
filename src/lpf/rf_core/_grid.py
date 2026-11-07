"""Phase-2 sampled S2P evaluation infrastructure.

Reusable forward evaluator only; archived EXP code and independent MNA remain
separate evidence. Frequencies are finite samples of all 28 band intervals.
"""
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
CASES = ("B71", "B12", "B28", "B13+B14", "B26", "B8")
def validated_band_segments(records):
    """Validate the canonical 28 intervals; never reinterpret unknown labels.

    Returns (setting_index, role_index, low_MHz, high_MHz) per row. This
    checks the *meaning* of every CSV row before any frequency samples or
    external S2P arrays are allocated.
    """
    if len(records) != 28:
        raise ValueError("Unexpected number of band intervals")
    # One UL, DL, H2 and H3 interval per physical band. B13+B14 has
    # two individually named subbands in the existing CSV note column.
    expected = {
        (case, region, subband)
        for case in CASES
        for region in ("UL", "DL", "H2", "H3")
        for subband in (case.split("+") if "+" in case else ("",))
    }
    segments = []
    seen = set()
    for index, row in enumerate(records):
        case, region, kind = row.get("case"), row.get("region"), row.get("type")
        if case not in CASES:
            raise ValueError(f"Unknown band case at segment {index}")
        if (kind == "pass" and region in ("UL", "DL")):
            role = 0
        elif kind == "stop" and region == "H2":
            role = 1
        elif kind == "stop" and region == "H3":
            role = 2
        else:
            raise ValueError(f"Invalid band type/region at segment {index}")
        key = (case, region, row.get("note", ""))
        if key not in expected or key in seen:
            raise ValueError(f"Unknown or duplicate band subband at segment {index}")
        seen.add(key)
        try:
            low = float(row["low_mhz"])
            high = float(row["high_mhz"])
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"Invalid frequency endpoints at segment {index}") from exc
        if not (np.isfinite(low) and np.isfinite(high) and 0 < low < high):
            raise ValueError(f"Invalid band frequency range at segment {index}")
        segments.append((CASES.index(case), role, low, high))
    if seen != expected:
        raise ValueError("Missing required band case/region/subband intervals")
    return tuple(segments)
