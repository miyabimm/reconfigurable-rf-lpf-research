"""Phase-2 sampled S2P evaluation infrastructure.

Reusable forward evaluator only; archived EXP code and independent MNA remain
separate evidence. Frequencies are finite samples of all 28 band intervals.
"""
from pathlib import Path
import csv
import numpy as np
from lpf.port_parasitics import get_two_port_s, s_to_abcd

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

class SampledExternalEvaluator:
    """28-interval sampling and frozen input/output S2P; no topology assumed."""

    def __init__(self, policy, points):
        if points < 1:
            raise ValueError("At least one frequency point is required")
        with (ROOT / "data/bands.csv").open(newline="", encoding="utf-8") as f:
            records = list(csv.DictReader(f))
        if len(records) != 28:
            raise ValueError("Unexpected number of band intervals")
        frequency, setting, role, segment = [], [], [], []
        for seg, row in enumerate(records):
            sampled = np.linspace(float(row["low_mhz"]), float(row["high_mhz"]), points)
            frequency.extend(sampled)
            setting.extend([CASES.index(row["case"])] * points)
            role.extend([0 if row["type"] == "pass" else
                         1 if row["region"] == "H2" else 2] * points)
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
