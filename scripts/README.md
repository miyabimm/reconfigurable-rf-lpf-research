# scripts/：探索・検証・監査の用途別案内（Phase 2）

> 実行前に制約ID・コード・データ・実行状態を確認すること。以下の説明は**閲覧用索引**であり、個々のrunnerが正式RF-F003を実装済みとの主張ではない。新規実験の計算にはmainでの事前EXP番号予約・照合が必要。

## 主要スクリプトの案内

| 系統 | スクリプト | 主な役割 |
|---|---|---|
| RF候補の台帳監査 | [audit_research_catalog.py](audit_research_catalog.py) | 登録候補・元証拠と条件IDの健全性を監査 |
| 候補・RF数値監査 | [audit_results.py](audit_results.py) | manifest／候補等を監査。EXP-047原manifestは非標準のまま保持し、[出典固定の索引専用アダプター](../src/lpf/legacy_manifest_adapter.py)で例外的に照合。新規runの厳格検証は維持 |
| 条件別パレート報告 | [report_research_pareto.py](report_research_pareto.py) | 既定は現行の旧系統台帳。`--catalog data/catalog/phase2_candidate_catalog_20261017.csv`指定で2026-10-17固定**24候補・10条件群**を出力 |
| 実験inventory | [audit_experiment_inventory.py](audit_experiment_inventory.py) | EXPごとの登録・実行状態・証拠整合を確認 |
| 事後検証overlay | [audit_validation_overlays.py](audit_validation_overlays.py) | 元実験と後日の独立検証を区別・点検 |
| 候補のPCB可変Cルール | [verify_no_pcb_tunable_candidates.py](verify_no_pcb_tunable_candidates.py) | 対象条件の候補種別制限を検証 |
| 統合24候補の派生生成・照合 | [build_phase2_candidate_catalog.py](build_phase2_candidate_catalog.py) | 旧14件固定CSV＋最新10件の不変出典をSHAで検証して生成、`--check`は再生成せず一致判定 |
| 歴史的W0データ・リンク監査（現在の常用対象外） | [旧tree監査](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3/scripts/audit_phase2_cleanup_w0_tree.py)、[旧link監査](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3/scripts/audit_phase2_cleanup_w0_links.py) | 2026-10-17の固定コミットを基準とした一時監査。必要時は[Step Cの復元案内](../docs/phase2_stepC_dated_audit_retirement_20261018.md)で元版を取得 |

## 共通実装と実験固有スクリプトの区別

共通の有限グラフ選別は[legacy_graph_search.py](../src/lpf/legacy_graph_search.py)、物理結合配置の検査は[coupling_layout.py](../src/lpf/coupling_layout.py)、設定ハッシュと原子的JSON保存は[checkpoint_io.py](../src/lpf/checkpoint_io.py)に配置。過去の`experiments/matching_limit/`側にある旧import名は互換ファサードであり、新しい共通機能の実装先ではない。従来のP4-A有限選別予算は正式RF制約ではない。

`curate_exp062.py`～`curate_exp065.py`、`review_rft008_exp062_065.py`、`full_lpf_checkpoint_import.py`は**実験固有または過去データ再現用**であり、今後の汎用RF探索入口ではない。元データと計算時点の再現性・参照先を個別に確認するまで無差別に削除しない。新規Pi Code専用の実装はまだない。

## 過去の管理スクリプト（mainから退役）

2026-10-15の出典棚卸し・46ファイル保全分類を生成した旧ツールは、研究原本を維持したまま既定のリポジトリから退役。必要時は [build_reference_inventory.py](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f0337963688d2a7155b8e28488d6723f2578e73e/scripts/build_reference_inventory.py) と [triage_unlinked_evidence.py](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f0337963688d2a7155b8e28488d6723f2578e73e/scripts/triage_unlinked_evidence.py) を固定コミットから取り出す。旧報告書・分類CSV・原実験データは削除しない。

## 新規EXP保存ゲート（main運用中）

EXP-050以降の開始前・保存完了・PR監査は [保存ポリシー](../docs/governance/phase2_experiment_storage_policy.md) と scripts/audit_new_experiment_storage.py を参照する。対象はEXP-050以降の新規runのmanifestとstorage_record。EXP-001～049（完了済みEXP-048/049を含む）は既存のまま保護し、書き換えない。

~~~bash
python scripts/audit_new_experiment_storage.py preflight EXP-NNN
python scripts/audit_new_experiment_storage.py finalize EXP-NNN
python scripts/audit_new_experiment_storage.py audit
~~~

## プログラム実行の前提

通常のリポジトリ環境は `uv.lock` に固定されたuvで管理される。たとえば既存回帰を実行する場合はルートで次の操作を行う。

```bash
uv sync --frozen
uv run --frozen python scripts/audit_results.py
uv run --frozen python -m unittest discover -s tests -v
```

2026-10-17の[旧失敗run](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39015048662)はEXP-047の原manifest不足を検出した当時の証拠。その後[統合PR #71の全回帰CI](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39028160775)は**マージ前SUCCESS（325テスト）**。これは数値探索の完全再演・原実行SHA復元・物理実装の証明ではない。

## 保全と変更のルール

探索・検証スクリプトの変更に伴って原checkpointや実行済み結果を改変しない。新条件の数値を算出する場合は、コードSHA・制約SHA・bandsと固定S2P・格子・独立検証を記録する。Phase 3は明示承認まで停止。

[全体README](../README.md) ／ [実験原本の案内](../experiments/README.md) ／ [結果の入口](../docs/results/README.md)
