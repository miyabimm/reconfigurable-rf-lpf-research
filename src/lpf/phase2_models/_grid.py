"""Phase-2 sampled S2P evaluation infrastructure.

Reusable forward evaluator only; archived EXP code and independent MNA remain
separate evidence. Frequencies are finite samples of all 28 band intervals.
"""
from pathlib import Path
import csv
import numpy as np
from lpf.port_parasitics import get_two_port_s, s_to_abcd
from lpf.constraint_versions import rf_input_file

ROOT = Path(__file__).resolve().parents[3]
CASES = ("B71", "B12", "B28", "B13+B14", "B26", "B8")
THREE_L_EDGES = ((0, 1), (1, 2), (1, 3))
THREE_L_FIXED_EDGES = ((0, 1), (1, 2), (3, -1))

def incidence(edges, nodes=4):
    result = np.zeros((nodes, len(edges)))
    for j, (a, b) in enumerate(edges):
        result[a, j] = 1.
        if b >= 0:
            result[b, j] = -1.
    return result

THREE_L_BL = incidence(THREE_L_EDGES)

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


class SampledExternalEvaluator:
    """28-interval sampling and frozen input/output S2P; no topology assumed."""

    def __init__(self, policy, points):
        if type(points) is not int or points < 1:
            raise ValueError("points must be an integer >= 1")
        with rf_input_file(ROOT, policy["bands_file"]).open(newline="", encoding="utf-8") as f:
            records = list(csv.DictReader(f))
        frequency, setting, role, segment = [], [], [], []
        for seg, (case_index, role_index, low, high) in enumerate(
                validated_band_segments(records)):
            frequency.extend(np.linspace(low, high, points))
            setting.extend([case_index] * points)
            role.extend([role_index] * points)
            segment.extend([seg] * points)
        self.f = np.asarray(frequency, float)
        self.omega = 2e6 * np.pi * self.f
        self.setting = np.asarray(setting, int)
        self.role = np.asarray(role, int)
        self.segment = np.asarray(segment, int)
        self.pre = np.asarray([s_to_abcd(get_two_port_s(
            policy, "input_parasitic", float(mhz * 1e6), root=ROOT))
            for mhz in self.f])
        self.post = np.asarray([s_to_abcd(get_two_port_s(
            policy, "output_parasitic", float(mhz * 1e6), root=ROOT))
            for mhz in self.f])
        self.cache_x = self.cache_il = None

class ThreeLGrid(SampledExternalEvaluator):
    """Inherited sampling and 3L-LQP02 coupling matrices for RF-T008."""

    def matrices(self, x):
        inductances = np.asarray(x[:3], float)
        matrix = np.diag(inductances.copy())
        for (i, j), k in zip(((0, 2), (2, 1)), x[6:8]):
            matrix[i, j] = matrix[j, i] = k * np.sqrt(inductances[i] * inductances[j])
        lossy = np.diag(inductances / 25.) + 1j * matrix
        return THREE_L_BL @ np.linalg.solve(lossy, THREE_L_BL.T), matrix, lossy

    def summary(self, x):
        values = self.il(x)
        indices = []
        for role in range(3):
            subset = np.flatnonzero(self.role == role)
            indices.append(int(subset[np.argmax(values[subset]) if role == 0
                                      else np.argmin(values[subset])]))
        return {
            "worst_IL_db": float(values[indices[0]]),
            "min_H2_db": float(values[indices[1]]),
            "min_H3_db": float(values[indices[2]]),
            "locations": [{"case": CASES[self.setting[i]], "MHz": float(self.f[i]),
                           "segment": int(self.segment[i])} for i in indices],
            "L_matrix_min_eig_nH": float(np.linalg.eigvalsh(self.matrices(x)[1])[0]),
        }
