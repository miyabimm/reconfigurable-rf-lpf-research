#!/usr/bin/env python3
"""Reproducible Pareto groups from curated Phase 2 records, without RF simulation.

Comparison is strictly within the same policy fingerprint, objective, 30/35-dB
requirement, and raw-feasibility evidence class. No claim of global optimality.
"""
import argparse
import csv
import io
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("comparison_key", "catalog_id", "constraint_class", "constraint_id",
          "objective", "requirement_db", "threshold_classification",
          "chip_area_units", "worst_il_db", "min_h2_db", "min_h3_db",
          "il_0p30_met_on_recorded_grid", "pareto_within_group",
          "independent_replay_overlay", "checkpoint_path")


def _rows(root, path):
    with (root / path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def dominates(a, b):
    aa, ai = float(a["chip_area_units"]), float(a["worst_il_db"])
    ba, bi = float(b["chip_area_units"]), float(b["worst_il_db"])
    return aa <= ba and ai <= bi and (aa < ba or ai < bi)


def make_report(root=ROOT, catalog_path="data/research_candidate_register.csv"):
    """Report a selected curated catalog; default remains the historical 14-row source.

    Historical 2026-10-17 unified catalog has been retired in Issue #397.
    Explicit --catalog paths can still be used for present curated CSV inputs.
    """
    root = Path(root)
    records = _rows(root, catalog_path)
    overlays = {x["candidate_id"]: x for x in
                _rows(root, "data/research_validation_overlays.csv")}
    if not records or len({x["catalog_id"] for x in records}) != len(records):
        raise ValueError("Empty or duplicated candidate IDs")
    groups = defaultdict(list)
    for row in records:
        numeric = [float(row[col]) for col in (
            "chip_area_units", "worst_il_db", "min_h2_db", "min_h3_db", "requirement_db")]
        if not all(map(math.isfinite, numeric)):
            raise ValueError("Non-finite candidate metric")
        if not row["comparison_key"]:
            raise ValueError("Comparison key missing")
        groups[row["comparison_key"]].append(row)

    view = []
    summaries = []
    for group, subset in sorted(groups.items()):
        identities = {(r["constraint_class"], r["constraint_id"],
                       r["effective_constraint_sha256"], r["objective"],
                       r["requirement_db"], r["threshold_classification"])
                      for r in subset}
        if len(identities) != 1:
            raise ValueError("Mixed policy, objective, target or class in " + group)
        kind, cid, digest, obj, target, evidence = next(iter(identities))
        front = [r for r in subset if not any(
            dominates(other, r) for other in subset if other is not r)]
        for r in sorted(subset, key=lambda v: (
                float(v["chip_area_units"]), float(v["worst_il_db"]), v["catalog_id"])):
            strict_meets = (
                float(r["worst_il_db"]) <= 0.30 and
                min(float(r["min_h2_db"]), float(r["min_h3_db"]))
                >= float(r["requirement_db"]))
            view.append({
                "comparison_key": group, "catalog_id": r["catalog_id"],
                "constraint_class": kind, "constraint_id": cid,
                "objective": obj, "requirement_db": target,
                "threshold_classification": evidence,
                "chip_area_units": r["chip_area_units"],
                "worst_il_db": r["worst_il_db"],
                "min_h2_db": r["min_h2_db"], "min_h3_db": r["min_h3_db"],
                "il_0p30_met_on_recorded_grid": str(strict_meets).lower(),
                "pareto_within_group": str(r in front).lower(),
                "independent_replay_overlay": (
                    overlays[r["catalog_id"]]["replay_validation_status"]
                    if r["catalog_id"] in overlays else "not_in_overlay"),
                "checkpoint_path": r["checkpoint_path"],
            })
        summaries.append({
            "key": group, "constraint_class": kind,
            "constraint_id": cid or "historical_unresolved",
            "effective_constraint_sha256": digest, "objective": obj,
            "requirement_db": target, "classification": evidence,
            "count": len(subset),
            "front": sorted(r["catalog_id"] for r in front),
            "min_area": min(float(r["chip_area_units"]) for r in subset),
            "min_il": min(float(r["worst_il_db"]) for r in subset),
        })
    summary = {
        "phase": "Phase 2", "comparison_scope": "curated_registered_candidates_only",
        "candidate_count": len(view), "comparison_group_count": len(summaries),
        "groups": summaries, "global_optimum_proven": False,
        "continuous_band_certification": False, "physical_validation": False,
        "formal_strict_rf_f002_il0p3_met": any(
            x["constraint_id"] == "RF-F002" and
            x["threshold_classification"] == "strict_finite_grid" and
            x["il_0p30_met_on_recorded_grid"] == "true" for x in view),
        "formal_strict_rf_f003_il0p3_met": any(
            x["constraint_class"] == "formal" and
            x["constraint_id"] == "RF-F003" and
            x["threshold_classification"] == "strict_finite_grid" and
            x["il_0p30_met_on_recorded_grid"] == "true" for x in view),
        "catalog_path": catalog_path,
    }
    return view, summary


def as_csv(view):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(view)
    return out.getvalue()


def as_markdown(summary):
    lines = [
        "# Phase 2 面積–IL Pareto（登録済み候補限定）", "",
        "台帳に登録した数値結果の集計であり、新しい最適化や独立回路計算は実施していない。"
        "制約ID、実効SHA、目的、減衰要求、判定区分が異なる候補は比較しない。", "",
        f"登録候補: {summary['candidate_count']} 件 / 比較区分: "
        f"{summary['comparison_group_count']} 件。下表は区分内の面積–IL非劣後候補であり、"
        "大域最適性や連続帯域を保証しない。", "",
        "| 制約（種別） | H2/H3要求 | 元数値の成立区分 | 件数 | 非劣後の候補ID | 最小チップ面積 | 最小IL [dB] |",
        "|---|---:|---|---:|---|---:|---:|",
    ]
    for g in summary["groups"]:
        lines.append(
            f"| {g['constraint_id']} ({g['constraint_class']}) "
            f"| {g['requirement_db']}dB | {g['classification']} "
            f"| {g['count']} | {', '.join(g['front'])} "
            f"| {g['min_area']:.6f} | {g['min_il']:.9f} |")
    lines.extend([
        "", "## 比較条件・限界", "",
        "- strict_finite_grid: 保存された有限格子の生H2/H3が要求値以上。",
        "- tolerance_only: 生値が要求値より小さく、solverの数値許容差内のみ成立。"
        "strictとの区分間Pareto比較は禁止。",
        "- reported_finite_grid: 元研究の報告区分。EXP-016の4件については"
        "後からCIで独立再計算が成功しているが元実行状態の証拠は変えない。",
        "- RF-T004の3可変C試験結果をRF-F002正式2可変C結果と混同しない。",
        "- RF-T005の3可変C試験結果をRF-F003正式2可変C結果と混同しない。",
        "- 2026-10-17の統合候補は不変snapshot由来。元checkpointのblob SHAを"
        "統合catalog生成時に確認するが、新しいRF数値解析を実行したわけではない。",
        "- historical_onlyは旧モデルの参考値。現行制約の順位付けに使わない。",
        "- 検証格子と証拠深度が異なる場合、厳密な相互優劣は"
        "同一格子・独立検証で再確認するまで確定しない。",
        "- チップ面積は正式な上限ではない。SRF、Q(f)、EM、温度、公差、"
        "PCB/IC面積、結合の物理実現性は検証していない。", "",
        f"入力: {summary['catalog_path']} と"
        " data/research_validation_overlays.csv。", "",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--catalog", default="data/research_candidate_register.csv",
                        help="curated CSV source; default data/research_candidate_register.csv")
    args = parser.parse_args()
    view, summary = make_report(catalog_path=args.catalog)
    for p, data in (
            (args.csv, as_csv(view)),
            (args.summary, json.dumps(summary, ensure_ascii=False, indent=2) + "\n"),
            (args.markdown, as_markdown(summary))):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data, encoding="utf-8")
    print("PASS: source-restricted Pareto", summary["candidate_count"],
          "candidates,", summary["comparison_group_count"], "groups")
    print("Strict formal RF-F002 IL <= 0.30dB achieved:",
          summary["formal_strict_rf_f002_il0p3_met"])
    print("Strict formal RF-F003 IL <= 0.30dB achieved:",
          summary["formal_strict_rf_f003_il0p3_met"])


if __name__ == "__main__":
    main()
