#!/usr/bin/env python3
"""Phase 2 W2: read-only, source-pinned structural search index.

Never modify original vectors, RF specifications or the frozen 24-row catalog.
Physical feasibility and electrical coupling dot conventions are not proved.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_CATALOG = "data/catalog/phase2_candidate_catalog_20261017.csv"
SNAP = "data/pareto_snapshots/rf_t005_rf_f003_20261017.json"
OUT = "data/catalog/phase2_topology_search_20261017.csv"
SUMMARY = "data/catalog/phase2_topology_search_20261017_summary.json"
REPORT = "docs/results/phase2_topology_search_20261017.md"
FIELDS = ["catalog_id", "constraint_class", "constraint_id", "experiment_id",
          "num_inductors", "topology_family", "electrical_inductor_edges",
          "electrical_edges_provenance", "reported_physical_inductor_order",
          "physical_order_provenance", "coupling_pair_order", "coupling_signs",
          "signed_coupling_pairs", "coupling_sign_provenance",
          "source_checkpoint", "source_git_blob_sha1",
          "additional_source", "additional_source_git_blob_sha1",
          "structural_evidence_state", "physical_realization_verified", "caveat"]
EDGE = re.compile(r"\b(L\d+|Ls)\((\d+),(\d+)\)")


def source_bytes(root, rel, sha):
    p = Path(rel)
    if not rel or p.is_absolute() or ".." in p.parts or "\\" in rel:
        raise ValueError("Invalid original source path")
    actual = (root / p).resolve()
    if not actual.is_relative_to(root.resolve()) or not actual.is_file():
        raise ValueError("Original source path absent")
    data = actual.read_bytes()
    actual_sha = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\x00" + data).hexdigest()
    if actual_sha != sha or not re.fullmatch("[0-9a-f]{40}", sha):
        raise ValueError("Git source blob mismatch: " + rel)
    return data


def read_rows(root, path):
    with (root / path).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def edges_from_text(text):
    matches = EDGE.findall(text)
    if len(set(t[0] for t in matches)) != len(matches):
        raise ValueError("Repeated graph label")
    return ";".join(label + ":" + u + "-" + v for label, u, v in matches)


def signs_for_pairs(pairs, values):
    if len(pairs) != len(values):
        raise ValueError("Malformed k vector")
    signs = []
    for value in values:
        n = float(value)
        if not math.isfinite(n) or abs(n) > 0.10000001:
            raise ValueError("Invalid numerical k")
        signs.append("+" if n > 1e-12 else "-" if n < -1e-12 else "0")
    return ";".join(signs), ";".join(a + ":" + b for a, b in zip(pairs, signs))


def build(root=ROOT):
    root = Path(root)
    prior = read_rows(root, BASE_CATALOG)
    if len(prior) != 24 or len(set(x["catalog_id"] for x in prior)) != 24:
        raise ValueError("Archived 24-row catalog identity changed")
    snap = json.loads((root / SNAP).read_text(encoding="utf-8"))
    current = {x["id"]: (group, x)
               for group in snap["conditions"] for x in group["candidates"]}
    if len(current) != 10:
        raise ValueError("Archived RF-T005/RF-F003 source count changed")

    cross = current["F003_4L_A5p333_EXP047"][1]["source"]["complete_parameter_vector"]
    cross_report = json.loads(source_bytes(root, cross["path"], cross["blob_sha"]))
    reported_4l_edges = edges_from_text(cross_report["topology"])
    if reported_4l_edges != "L0:0-1;L1:1-3;L2:1-4;L3:1-2":
        raise ValueError("Related EXP-047 topology evidence changed")
    output = []
    for base in prior:
        identifier = base["catalog_id"]
        row = dict.fromkeys(FIELDS, "")
        for col in ("catalog_id", "constraint_class", "constraint_id", "experiment_id"):
            row[col] = base[col]
        row["source_checkpoint"] = base["checkpoint_path"]
        row["source_git_blob_sha1"] = base["checkpoint_git_blob_sha1"]
        row["physical_realization_verified"] = base["physical_realization_verified"] or "unknown"
        if identifier not in current:
            row.update({
                "topology_family": "historical_unclassified",
                "electrical_inductor_edges": "unknown",
                "electrical_edges_provenance": "not_extracted",
                "reported_physical_inductor_order": "unknown",
                "physical_order_provenance": "not_extracted",
                "coupling_pair_order": "unknown",
                "coupling_signs": "unknown",
                "signed_coupling_pairs": "unknown",
                "coupling_sign_provenance": "not_extracted",
                "structural_evidence_state": "historical_not_yet_normalized",
                "caveat": "Source graph may exist, but W2 has not extracted it. Unknown does not mean electrically absent.",
            })
            output.append(row)
            continue
        group, entry = current[identifier]
        if base["constraint_id"] != group["constraint_id"]:
            raise ValueError("Snapshot group/candidate constraint mismatch")
        src = entry["source"]["complete_parameter_vector"]
        if src["path"] != row["source_checkpoint"] or src["blob_sha"] != row["source_git_blob_sha1"]:
            raise ValueError("Original source identity diverges from catalog")
        data = json.loads(source_bytes(root, src["path"], src["blob_sha"]))
        n = int(base["num_lqp02hv"])
        if n not in (3, 4):
            raise ValueError("Not a 3L/4L candidate")
        row["num_inductors"] = str(n)
        row["topology_family"] = "3L_shunt_L" if n == 3 else "4L_EXP042_related"
        row["electrical_inductor_edges"] = "unknown"
        row["electrical_edges_provenance"] = "not_stated_in_own_checkpoint"
        row["reported_physical_inductor_order"] = "unknown"
        row["physical_order_provenance"] = "not_stated"
        caveats = []
        if n == 3:
            pairs = ["L0-Ls", "Ls-L1"]
            if "L_edges" in data:
                if data["L_edges"] != [[0, 1], [1, 2], [1, 3]]:
                    raise ValueError("Unrecognized three-inductor graph")
                row["electrical_inductor_edges"] = "L0:0-1;L1:1-2;Ls:1-3"
                row["electrical_edges_provenance"] = "own_structured_edges"
                if data.get("coupled_L_pairs") != [[0, 2], [2, 1]]:
                    raise ValueError("Unrecognized 3L coupling pairs")
                row["reported_physical_inductor_order"] = ";".join(data["physical_L_order"])
                row["physical_order_provenance"] = "own_label_order"
            elif "topology" in data:
                row["electrical_inductor_edges"] = edges_from_text(data["topology"])
                row["electrical_edges_provenance"] = "own_prose"
            ks = data["vector"][6:8]
        else:
            pairs = ["L0-L1", "L1-L3", "L3-L2"]
            if data.get("topology"):
                row["electrical_inductor_edges"] = edges_from_text(data["topology"])
                row["electrical_edges_provenance"] = "own_prose"
            else:
                row["electrical_inductor_edges"] = reported_4l_edges
                row["electrical_edges_provenance"] = "related_EXP047_only_not_independently_confirmed"
                row["additional_source"] = cross["path"]
                row["additional_source_git_blob_sha1"] = cross["blob_sha"]
                caveats.append("Related EXP-047 report names EXP-042 family; edges not explicitly checked in this own checkpoint.")
            if "physical_inductor_order" in data:
                row["reported_physical_inductor_order"] = ";".join(data["physical_inductor_order"])
                row["physical_order_provenance"] = "own_label_order"
            elif "L_order" in data:
                row["reported_physical_inductor_order"] = data["L_order"].replace("-", ";")
                row["physical_order_provenance"] = "own_label_order"
            if "candidates" in data:
                select_id = entry.get("selected_candidate_id")
                selected = next((p for p in data["candidates"] if p["id"] == select_id), None)
                if selected is None:
                    raise ValueError("Archived selected nested candidate not found")
                ks = selected["params"]["k_adjacent_L0_L1_L1_L3_L3_L2"]
            else:
                ks = data["vector"][8:11]
        sign_seq, signed = signs_for_pairs(pairs, ks)
        row["coupling_pair_order"] = ";".join(pairs)
        row["coupling_signs"] = sign_seq
        row["signed_coupling_pairs"] = signed
        row["coupling_sign_provenance"] = "own_numerical_parameter_vector"
        row["structural_evidence_state"] = (
            "labeled_from_original_checkpoint"
            if row["electrical_edges_provenance"].startswith("own_")
            else "related_family_reference_or_partial"
        )
        caveats.append("Signed numerical k and reported order are NOT verified physical dot or EM realization.")
        row["caveat"] = " ".join(caveats)
        output.append(row)
    summary = {
        "phase": "Phase 2", "source_catalog": BASE_CATALOG,
        "status": "read_only_derived_search_index",
        "total_records": len(output),
        "new_t005_records": 6, "new_f003_records": 4,
        "historical_14_unclassified": 14,
        "evidence_states": dict(sorted(Counter(x["structural_evidence_state"] for x in output).items())),
        "source_sha_checks": 11,
        "original_source_files_changed": False,
        "rf_simulations_newly_executed": False,
        "physical_realization_verified_by_this_index": False,
        "notes": [
            "Signed k derives only from original parameter vectors.",
            "EXP-042 electrical edges use an explicitly marked related EXP-047 family reference.",
            "Historical 14 source graphs are not normalized; blank metadata is not evidence of absence.",
            "No independent graph equivalence, coil dot convention or physical EM verification is claimed.",
        ],
    }
    return output, summary


def render():
    rows, summary = build()
    csv_io = io.StringIO(newline="")
    writer = csv.DictWriter(csv_io, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    md = [
        "# Phase 2 W2: トポロジー・結合符号の検索索引（2026-10-17）", "",
        "**既存24候補を出典SHAで参照する派生索引。新たなRF解析結果ではありません。**",
        "正式RF-F003と試験RF-T005を分け、kの符号・コイル順を元の報告ラベルとして記録する。",
        "結合の物理的同時実現性、EM、SRF、Q(f)、公差の検証ではない。", "",
        "| ID | 制約 | 回路系列 | 接続の出典種別 | コイル順ラベル | k符号ペア |",
        "|---|---|---|---|---|---|",
    ]
    for x in rows:
        if x["structural_evidence_state"] == "historical_not_yet_normalized":
            continue
        md.append("| " + x["catalog_id"] + " | " + x["constraint_id"] + " | " +
                  x["topology_family"] + " | " + x["electrical_edges_provenance"] + " | " +
                  x["reported_physical_inductor_order"] + " | " + x["signed_coupling_pairs"] + " |")
    md += [
        "", "## 利用方法と限界", "",
        "- [構造CSV](../../data/catalog/phase2_topology_search_20261017.csv)のcatalog_idを",
        "  [元24候補性能CSV](../../data/catalog/phase2_candidate_catalog_20261017.csv)へ結合する。",
        "- topology_family、electrical_inductor_edges、reported_physical_inductor_order、signed_coupling_pairsで検索できる。",
        "- 旧14候補の値は未抽出であり、回路構造が存在しないという意味ではない。",
        "- related_EXP047_only_not_independently_confirmedは別EXPの同一系列記述であり、",
        "  個別checkpointsで接続が証明された意味ではない。",
        "- kの符号は数値ベクトルの正負であり、実PCBでの磁気結合の向き・実現性を証明しない。",
        "", "再生成: python scripts/build_phase2_topology_search.py [--check]", "",
        "**研究Phase 2継続。Phase 3へは移行していません。**", "",
    ]
    return {OUT: csv_io.getvalue(),
            SUMMARY: json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            REPORT: "\n".join(md)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument('--output-dir', type=Path,
                        help='export CSV, JSON and Markdown under this disposable directory; '
                             'default maintains only the tracked CSV')
    args = parser.parse_args()
    for rel, content in render().items():
        if args.output_dir is None and rel != OUT:
            continue
        p = (args.output_dir or ROOT) / rel
        if args.check:
            if not p.is_file() or p.read_text(encoding="utf-8") != content:
                raise SystemExit("W2 stale derived data: " + rel)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
    print("W2 structure search index verified" if args.check else "W2 structure search index written")


if __name__ == "__main__":
    main()
