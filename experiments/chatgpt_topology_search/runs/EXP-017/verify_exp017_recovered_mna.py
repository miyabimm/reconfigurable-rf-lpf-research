#!/usr/bin/env python3
"""Independent branch-current 9x9 MNA replay of recovered EXP-017 RF-F002.

Uses the Git-tracked full 23-value vector and data/bands.csv, not the legacy
solver or its stored validation numbers. No optimization is performed.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
CANDIDATE = ROOT / "experiments/chatgpt_topology_search/runs/EXP-017/EXP017-LQW4-H30-NEAR.recovered.json"
SETTINGS = ("B71", "B12", "B28", "B13+B14", "B26", "B8")


def incidence(edges, nodes=5):
    result = np.zeros((nodes, len(edges)))
    for j, (a, b) in enumerate(edges):
        if a:
            result[a-1, j] = 1.0
        if b:
            result[b-1, j] = -1.0
    return result


def replay(points_per_csv_segment=1001, *, root=ROOT):
    if points_per_csv_segment < 3:
        raise ValueError("at least three points per CSV segment required")
    root = Path(root)
    path = root / CANDIDATE.relative_to(ROOT)
    candidate = json.loads(path.read_text(encoding="utf-8"))
    if (candidate["experiment_id"] != "EXP-017" or
            candidate["constraint_id"] != "RF-F002" or
            candidate["phase"] != "Phase 2" or
            candidate["requirement_db"] != 30 or
            candidate["effective_constraint_sha256"] !=
            "f20d27e93451dcec2f823e6f7c3731c06d843050c4d2ace8b0b46ded605542e2"):
        raise ValueError("Wrong experiment, formal constraint, or target")
    bands_bytes = (root / "data/bands.csv").read_bytes()
    if hashlib.sha256(bands_bytes).hexdigest() != candidate["bands_sha256"]:
        raise ValueError("Band specification changed")
    with (root / "data/bands.csv").open(newline="", encoding="utf-8") as file:
        bands = list(csv.DictReader(file))
    x = np.array(candidate["x_logL_logC_k_6x2Cv_epi"], dtype=float)
    if x.shape != (23,) or not np.all(np.isfinite(x)):
        raise ValueError("Lost EXP-017 full 23-element checkpoint")
    model = candidate["topology"]
    if (model["physical_order"] != [0, 1, 2, 3] or
            model["inductor_series"] != ["LQW04"] * 4 or
            model["variable_setting_order"] != list(SETTINGS) or
            model["source_node"] != 1 or model["load_node"] != 3 or
            model["variable_capacitor_edges"] != [[4, 0], [2, 3]]):
        raise ValueError("Recovered topology changed")
    L = np.exp(x[:4]) * 1e-9
    cap_fixed = np.exp(x[4:7]) * 1e-12
    cap_variable = x[10:22].reshape(6, 2) * 1e-12
    if np.any(cap_variable < 0) or np.any(cap_variable > 1.5e-12 + 1e-24):
        raise ValueError("IC variable capacitance exceeds formal RF-F002")
    if np.any(np.abs(x[7:10]) > 0.15 + 1e-12):
        raise ValueError("Chip-neighbor coupling limit exceeded")
    K = np.eye(4)
    for j in range(3):
        K[j, j+1] = K[j+1, j] = x[7+j]
    min_eig = float(np.linalg.eigvalsh(K).min())
    if min_eig <= 0:
        raise ValueError("Coupled inductance matrix not SPD")
    mutual = np.sqrt(np.outer(L, L)) * K
    B = incidence(model["inductor_edges"])
    A = incidence(model["fixed_capacitor_edges"] + model["variable_capacitor_edges"])
    Qc = np.asarray(model["fixed_capacitor_Q"] + model["variable_capacitor_Q"])
    Ql = np.asarray(model["inductor_Q"])
    if Ql.tolist() != [33] * 4 or Qc.tolist() != [80, 80, 40, 50, 50]:
        raise ValueError("Constant-Q model changed")
    src = 1 / 50
    load_admittance = 1 / (60 - 40j)
    source = np.zeros(9, complex)
    source[0] = src
    port = np.diag([src, 0, load_admittance, 0, 0]).astype(complex)
    ZperRad = np.diag(L / Ql) + 1j * mutual
    measurements = {"IL": [], "H2": [], "H3": []}
    by_setting = []
    worst_balance = worst_solver_difference = 0.0
    samples = 0
    for ci, setting in enumerate(SETTINGS):
        case_report = {"setting": setting}
        cc = np.r_[cap_fixed, cap_variable[ci]]
        Yc_perRad = (A * (cc/(1/Qc-1j))[None,:]) @ A.T
        for metric, regions in (("IL", ("UL", "DL")), ("H2", ("H2",)), ("H3", ("H3",))):
            curve, freqs = [], []
            for row in bands:
                if row["case"] != setting or row["region"] not in regions:
                    continue
                f = np.linspace(float(row["low_mhz"]), float(row["high_mhz"]), points_per_csv_segment)
                omega = f * (2 * np.pi * 1e6)
                mat = np.zeros((len(f), 9, 9), dtype=complex)
                mat[:, :5, :5] = port + omega[:,None,None] * Yc_perRad
                mat[:, :5, 5:] = B
                mat[:, 5:, :5] = -B.T
                mat[:, 5:, 5:] = omega[:,None,None] * ZperRad
                rhs = np.broadcast_to(source, (len(f), 9))
                solved = np.linalg.solve(mat, rhs[...,None])[...,0]
                v, i = solved[:,:5], solved[:,5:]
                power_load = np.abs(v[:,2]) ** 2 * load_admittance.real
                il = -10 * np.log10(power_load / (1 / 200))
                curve.append(il)
                freqs.append(f)
                power_reflected = np.abs(1 - 2 * v[:,0]) ** 2 / 200
                power_inductors = np.sum(np.abs(i) ** 2 * (omega[:,None] * (L/Ql)), axis=1)
                cap_drop = v @ A
                power_capacitors = np.sum(np.abs(cap_drop) ** 2 *
                                          omega[:,None] * np.real(cc/(1/Qc-1j)), axis=1)
                worst_balance = max(worst_balance,
                                    float(np.max(np.abs(1/200 - power_load - power_reflected
                                                        - power_inductors - power_capacitors))))
                # Independently formed five-node Schur complement as an extra cross check.
                nodal = port[None,:,:] + omega[:,None,None] * Yc_perRad[None,:,:]
                nodal += B[None,:,:] @ np.linalg.inv(omega[:,None,None] * ZperRad) @ B.T[None,:,:]
                voltage = np.linalg.solve(nodal, np.broadcast_to(source[:5], (len(f), 5))[...,None])[...,0]
                il_nodal = -10 * np.log10((np.abs(voltage[:,2])**2 * load_admittance.real)/(1/200))
                worst_solver_difference = max(worst_solver_difference,
                                             float(np.max(np.abs(il_nodal-il))))
                samples += len(f)
            full = np.concatenate(curve)
            at = int(np.argmax(full) if metric == "IL" else np.argmin(full))
            value = float(full[at])
            measurements[metric].append(value)
            case_report[metric] = {"value_db": value, "frequency_mhz": float(np.concatenate(freqs)[at])}
        by_setting.append(case_report)
    result = {
        "schema_version": 1,
        "phase": "Phase 2",
        "candidate_id": candidate["candidate_id"],
        "experiment_id": "EXP-017",
        "constraint_id": "RF-F002",
        "effective_constraint_sha256": candidate["effective_constraint_sha256"],
        "bands_sha256": candidate["bands_sha256"],
        "validation_kind": "independent_augmented_branch_current_9x9_mna_and_nodal_crosscheck",
        "numerical_scope": "Phase 2 constant-Q finite grid; no continuous-band or physical guarantee",
        "points_per_csv_band_segment": points_per_csv_segment,
        "evaluated_frequency_samples": samples,
        "worst_il_db": max(measurements["IL"]),
        "min_h2_db": min(measurements["H2"]),
        "min_h3_db": min(measurements["H3"]),
        "k_min_eigenvalue": min_eig,
        "max_power_balance_residual_W": worst_balance,
        "max_mna_nodal_il_difference_db": worst_solver_difference,
        "per_setting": by_setting,
        "strict_finite_grid_30db": min(measurements["H2"] + measurements["H3"]) >= 30,
        "il_le_0p30db": max(measurements["IL"]) <= 0.30,
        "physical_verification": "not_run",
        "original_453_optimization_attempts_reexecuted": False
    }
    if not (math.isclose(result["worst_il_db"], candidate["performance"]["worst_IL_db"],abs_tol=1e-7) and
            math.isclose(result["min_h2_db"], candidate["performance"]["min_H2_db"],abs_tol=1e-6) and
            math.isclose(result["min_h3_db"], candidate["performance"]["min_H3_db"],abs_tol=1e-5)):
        raise ValueError("Recovered full vector does not reproduce source metrics")
    if not (result["strict_finite_grid_30db"] and not result["il_le_0p30db"] and
            worst_solver_difference < 1e-7 and worst_balance < 1e-12):
        raise ValueError("Recovered RF-F002 numerical independent MNA validation failed")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--points", type=int, default=1001)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    result = replay(args.points)
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                                encoding="utf-8")
    print("PASS recovered EXP-017 independent RF-F002 9x9 MNA:",
          json.dumps({key: value for key, value in result.items()
                      if key in ("worst_il_db", "min_h2_db", "min_h3_db",
                                 "k_min_eigenvalue", "max_power_balance_residual_W",
                                 "points_per_csv_band_segment")}))


if __name__ == "__main__":
    main()
