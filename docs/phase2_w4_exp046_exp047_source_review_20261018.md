# Phase 2 W4：EXP-046・EXP-047研究証拠の出典・訂正・再現性監査（2026-10-18）

> W4実験・workflow整理の**非破壊レビュー**。研究Phase 2継続、Phase 3未承認。正式RF-F003と試験RF-T005の数値結果を混同しない。実験原本削除・既存候補改変・数値最適化再実行は行わない。

## スコープと方法

- 起点main：`abde1a1df3c768c479abcfd5941741a82b8c6483`（PR #86統合後）。
- [過去の225件個別W4台帳](../data/repository_reviews/w4_unindexed_225_review_20261017.csv)から、EXP-046の**35件**とEXP-047の**96件**、合計**131ファイル**を対象に抽出。
- [読取専用の出典検証スクリプト](../scripts/audit_w4_exp046_exp047_sources.py)で、全131パスの元Git blob SHA・実ファイルバイト数が固定台帳と一致することを検査する。旧46件もSHA不変であることを確認。
- 元manifest、後日の訂正説明、既存の候補台帳・パレート台帳を別々に読む。manifestにファイル名があることは元in-chat実行時にそのファイルがロードされたことの**証明ではない**。JS構文が解析可能なことも数値実行の証明ではない。
- 調査済みの元RFモデル（入力／出力の固定S2P、6設定28不連続区間、50Ω源／60−j40Ω負荷等）と出典の明示のみを確認する。数値結果を今回再計算しない。

## EXP-046：RF-T005試験条件の4L探索

- [元manifest](../experiments/chatgpt_topology_search/runs/EXP-046/manifest.json)は**部分完了**、試験RF-T005。archived source SHA `0774f3025e7ad5b1a7c782fdf0fc6b8b828d0af5` は**実行時のクリーンコミットであるとは検証されていない**。 `code.working_tree_dirty=true`、`random_seed=null`、`environment=null`のまま保持。
- [日付付き元README](../experiments/chatgpt_topology_search/runs/EXP-046/README.md)に初期探索の厳格30dB未達と、後続の別4Lトポロジーで一部30dB達成という**時点が異なる両方の記録**が残る。古い「すべて未達」見出しだけを取り出して現在の結論としない。
- 独立MNAの保存結果は28区間×1001点の主式評価に対する**84点の独立枝電流MNA**であり、独立式が1001格子すべてで実行されたとは扱わない。
- **訂正系列：** `independent_verified_1001.json`の容量損失の電力会計式に誤りがあり、[corrected版](../experiments/chatgpt_topology_search/runs/EXP-046/independent_verified_1001_corrected.json)が訂正根拠。保存説明ではIL/H2/H3は非影響だが、**古い容量損失診断値は正式引用しない**。両方を歴史出典として保持。
- 面積・ILの既存優位点EXP-042があるため、EXP-046の記録を実験結果が無いとみなしたり、正式RF-F003と混在させない。

## EXP-047：正式RF-F003の2可変C研究

- [元manifest](../experiments/chatgpt_topology_search/runs/EXP-047/manifest.json)は非標準の局所in-chat結果報告。`github_actions_search_executed=false`。元optimizerのGitコミット・seed・環境・作業ツリー状態は[元blob固定の索引専用adapter](../data/validation/exp047_legacy_manifest_adapter_20261017.json)で**unknown**のまま。厳格な実行manifestに昇格しない。
- **部品Qバグの歴史区分：** [元README](../experiments/chatgpt_topology_search/runs/EXP-047/README.md)が明記する初期`Q[5]=80`は削除済みCv1への適用で、正しいGJM Cf1は`Q[1]=80`。元manifestの`execution.q_bug_excluded_files`に列挙された5つの元ファイルは、**正式RF-F003のQモデルに適合した性能順位には使わない**。訂正前の探索が無効という意味で原本を削除しない。
- 参考元コードと元独立検証JSONを保持する。正式RF-F003の保存済み候補は[2026-10-17パレート台帳](../data/pareto_snapshots/rf_t005_rf_f003_20261017.json)の**4件**。候補JSONのGit blob SHA・[候補catalog](../data/catalog/phase2_candidate_catalog_20261017.csv)と参照先の対応を監査する。確認できるのは**記録の同一性・出典**であり、数値の新規RF独立検証ではない。
- 修正Q80後の28×1001有限格子、84点独立MNAという既存報告に、連続帯域極値・Q(f)/SRF/EM・公差／温度・同時結合物理性の保証はない。

## GitHub Actionsで実行した監査結果（2026-10-18）

[W4 EXP-046・EXP-047原本出典CI](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39093528326) **SUCCESS**。実行checkoutで元blob 131件／旧46件全件の照合に成功し、同時に正式4候補の記録先Git SHAを照合した。個票の[固定CSV](../data/repository_reviews/w4_exp046_exp047_131_20261018.csv)と[集計JSON](../data/repository_reviews/w4_exp046_exp047_summary_20261018.json)をGitに保存。後続CIで同じ131件に対するCSVのバイト完全一致を再検査する。

| 出典分類 | EXP-046 | EXP-047 | 合計 |
|---|---:|---:|---:|
| 元のin-chat JavaScriptプログラム | 個別CSV参照 | 個別CSV参照 | **54件** |
| 元数値結果・診断JSON | 個別CSV参照 | 個別CSV参照 | **75件** |
| 時系列解釈README | 1 | 1 | **2件** |
| **元ファイル計** | **35件** | **96件** | **131件** |

- **EXP-046**：元manifestのworking_tree_dirty=true、seed／環境null、archive SHAは実行状態の確定SHAではないことを固定。容量電力会計の**訂正前・訂正後2ファイル**を履歴として保全。GitHub Actionsの元探索再実行や未収束点の排除をこの監査では行っていない。
- **EXP-047**：元manifestは非標準。旧adapterと元manifestのSHA一致。元optimizer commit・seed・環境はすべてunknown。元manifestのQインデックス誤割当リスト**5原本**を正式RF-F003性能順位から除外する分類を記録（原ファイルの削除はしない）。manifestがいう検証済みの**6候補**と、現行正式パレート採録**4候補**の区別を維持し、その4件の元ファイルのGit blob SHAとカタログ参照を確認。
- 判定：元原本**131件保持**、旧46件全件保持、原本削除承認0、実削除0、数値最適化再実行0、新規独立MNA実行0。**W5で読み取り専用の全体ゲート監査に進むことは可能**だが、W4の実験原本・workflow削除やW4完全終了は未承認である。

## 判定／完了ゲート

**今回確定するもの：** 131元blobのSHA同一性、過去の訂正前後区分、manifest欠損を欠損のまま記録、4個の正式RF-F003候補の元Git出典チェック。調査結果は固定CSV・JSONへ保存する。各ファイルを「索引未登録＝削除可能」と分類しない。

**未解決：** 旧Code Mode動的実行環境・S2P実体のリプレイ／元seed、EXP-047厳格manifest欠損、Q修正前後の独立再計算、公差、物理実装、古いworkflowの停止影響。このためW5は**削除作業ではなく読み取り専用の完了度監査のみ**実行可。研究成果の削除は個別の所有者承認・代替出典検証・独立PRを条件とする。旧46件・D-005～007は保全継続。
