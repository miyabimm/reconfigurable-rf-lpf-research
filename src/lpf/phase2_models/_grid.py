"""Legacy three-inductor sampled evaluator."""
import numpy as np
import csv
from lpf.rf_core._grid import ROOT, CASES, validated_band_segments
from lpf.port_parasitics import get_two_port_s, s_to_abcd
from lpf.constraint_versions import rf_input_file

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


class SampledExternalEvaluator:
    """28-interval sampling and frozen input/output S2P; no topology assumed."""

    def __init__(self, policy, points, *, extra_frequencies=()):
        if type(points) is not int or points < 1:
            raise ValueError("points must be an integer >= 1")
        with rf_input_file(ROOT, policy["bands_file"]).open(newline="", encoding="utf-8") as f:
            records = list(csv.DictReader(f))
        segments = validated_band_segments(records)
        extras = [[] for _ in segments]
        seen = set()
        for item in extra_frequencies:
            try:
                seg, mhz = item
            except (TypeError, ValueError) as exc:
                raise ValueError("Expected (segment_id, frequency_MHz)") from exc
            if (type(seg) is not int or not 0 <= seg < len(segments) or
                    isinstance(mhz, (bool, str, bytes))):
                raise ValueError("Invalid segment or frequency")
            try:
                mhz = float(mhz)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Invalid frequency") from exc
            _, _, low, high = segments[seg]
            key = (seg, mhz)
            if (not np.isfinite(mhz) or not low <= mhz <= high or key in seen or
                    mhz in np.linspace(low, high, points)):
                raise ValueError("Duplicate or out-of-interval frequency")
            seen.add(key)
            extras[seg].append(mhz)
        frequency, setting, role, segment = [], [], [], []
        for seg, (case_index, role_index, low, high) in enumerate(segments):
            grid = list(np.linspace(low, high, points)) + sorted(extras[seg])
            frequency.extend(grid)
            setting.extend([case_index] * len(grid))
            role.extend([role_index] * len(grid))
            segment.extend([seg] * len(grid))
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
