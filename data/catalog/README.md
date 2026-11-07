# Phase 2：2026-10-17固定カタログ

**履歴時点の検索用派生データです。現行の候補一覧・RF条件の正本ではありません。** 現行RF正式版は[registry](../constraints/registry.json)、最新EXP状態は[experiment_index.csv](../experiment_index.csv)を参照してください。この固定版には旧EXP45件／試験RF-T005までの索引を保持しています（2026-10-28 mainの現役索引は66件／RF-T008まで）。時点固定の相違を「欠落」として補完しないでください。

## 必要な出典と検索索引

| ファイル | 用途 |
|---|---|
| [旧14候補](research_candidate_register_20261017.csv)、[当時の制約](constraints_registry_20261017.json)、[当時のEXP索引](experiment_index_20261017.csv) | 再生成時にGit blob SHAで固定した履歴入力。現行台帳で置き換えない |
| [RF-T005/RF-F003 Pareto元スナップショット](../pareto_snapshots/rf_t005_rf_f003_20261017.json) | trial 6件とformal 4件の保存候補 |
| [候補24件CSV](phase2_candidate_catalog_20261017.csv) | 上記14+10件の**派生検索ビュー**。元checkpoint、source SHA、収束・検証状態への入口 |
| [回路構造24件CSV](phase2_topology_search_20261017.csv) | 候補IDで結合する構造・結合符号の**派生検索ビュー** |

- **条件を混合しない:** RF-F003（formal、可変C最大2）とRF-T005（trial、最大3）は別の比較群。制約ID／実効SHA、目的、H2/H3閾値、`threshold_classification`、格子と独立MNAの証拠深度を照合する。旧14件の欠損値は補間しない。
- **原本は変えない:** RF-F003の4GJM候補は、原検証JSONの面積6の誤記を派生CSV側で**6⅔**に訂正。元ファイルには手を加えていない。SHA一致は新規のRF再計算やEM実証を意味しない。
- **構造も限定的:** 旧14件の`unknown`は未抽出の意味。EXP-042の接続をEXP-047の関連記録から採る場合は独立確認済みと扱わない。数値kの符号は物理巻線極性・製造可能性の証明ではない。

再生成の照合（新規最適化は実行しない）：

```bash
python scripts/build_phase2_candidate_catalog.py --check
python scripts/build_phase2_topology_search.py --check
```

### 再生成可能なレポートは保存しない（Issue #352）

集計JSON2件とMarkdown表2件は上記の不変入力・CSVから再生成できるため、通常treeでの二重保管を廃止しました。
CSV2件は検索・比較コードの入力として残し、元入力3件・Pareto・EXPの保存ベクトルとSHA固定証拠は維持します。
既定の生成／`--check` は追跡CSVだけを対象にします。全レポートが必要な場合は一時出力先を明示します：

```bash
out=$(mktemp -d /tmp/lpf-catalog-reports-XXXXXX)
uv run --frozen python scripts/build_phase2_candidate_catalog.py --output-dir "$out"
uv run --frozen python scripts/build_phase2_topology_search.py --output-dir "$out"
uv run --frozen python scripts/build_phase2_candidate_catalog.py --output-dir "$out" --check
uv run --frozen python scripts/build_phase2_topology_search.py --output-dir "$out" --check
```

出力は `$out/data/catalog/` と `$out/docs/results/`。相対リンクで指す原証拠は元リポジトリにあり、
出力だけで自己完結した証拠checkoutにはなりません。
整理前の逐語原文は `git show a86f47b:<元path>` で復元できます。
研究の説明は[保存結果の入口](../../project/results.md)、構造の証拠限界は本ページを使用します。
Phase 2を継続し、Phase 3は未承認です。
