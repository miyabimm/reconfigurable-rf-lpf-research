# scripts/：探索・検証・監査の用途別案内（Phase 2）

> 実行前に制約ID・コード・データ・実行状態を確認すること。以下の説明は**閲覧用索引**であり、個々のrunnerが正式RF-F003を実装済みとの主張ではない。新規実験の計算にはmainでの事前EXP番号予約・照合が必要。

## 主要スクリプトの案内

| 系統 | スクリプト | 主な役割 |
|---|---|---|
| RF候補の台帳監査 | [audit_research_catalog.py](audit_research_catalog.py) | 登録候補・元証拠と条件IDの健全性を監査 |
| 候補・RF数値監査 | [audit_results.py](audit_results.py) | manifest／候補等を監査。EXP-047原manifestは非標準のまま保持し、[出典固定の索引専用アダプター](../src/lpf/legacy_manifest_adapter.py)で例外的に照合。新規runの厳格検証は維持 |
| 条件別パレート報告 | [report_research_pareto.py](report_research_pareto.py) | 現存する`data/research_candidate_register.csv`などを明示的に読み取る汎用の同条件別解析器。旧24候補固定カタログは削減済み |
| 候補のPCB可変Cルール | [verify_no_pcb_tunable_candidates.py](verify_no_pcb_tunable_candidates.py) | 対象条件の候補種別制限を検証 |
| 歴史的W0データ・リンク監査（現在の常用対象外） | [旧tree監査](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3/scripts/audit_phase2_cleanup_w0_tree.py)、[旧link監査](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3/scripts/audit_phase2_cleanup_w0_links.py) | 2026-10-17の固定コミットを基準とした一時監査。必要時は[時点固定の監査案内](../project/legacy_git_replay.md)で元版を取得 |

## MinimalWorker開発ベンチ

[benchmark_minimal_worker.py](benchmark_minimal_worker.py) は正式Job・EXPではない。例（trialを明示した既存Plan、出力先は呼出側で確保）：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --frozen python scripts/benchmark_minimal_worker.py \
  --config project/diagnostics/issue377/baseline.yaml \
  --starts project/diagnostics/issue401_starts_1002.json \
  --arm hybrid --seed 1002 --mode plain > result.json
```

`--mode timed` はL1/L2、`deep` はL3も記録。plainは計器を設置しない。stdout JSONをrunごとに保存し、失敗時のstderr・終了コードも別に保管する。source identityとscript SHA、Plan・RF入力・grid・starts/vector SHA、solver、環境・affinity・inclusive timersを記録する。任意の `--expected-source-sha256` / `--expected-script-sha256` はRF前に不一致を拒否する。`solver_s` は `worker.solve()` のみ（Hybrid単独ではない）、`total_s` はsetup＋solve、best_xの追加評価 `observation_s` / `observation_forward_count` はその外でsolver nfevに含まれない。dense・独立検証・保存台帳は実施しない。比較手順と限界は[methods](../project/methods.md#minimalworker性能診断の運用401408)参照。

## 共通実装と実験固有スクリプトの区別

旧有限グラフ選別は[legacy_graph_search.py](../src/lpf/legacy_graph_search.py)、設定ハッシュと原子的JSON保存は[checkpoint_io.py](../src/lpf/checkpoint_io.py)にある。旧matchingの結合・可変C layout実装は現役APIから退役し、現行treeにない。元commitと元パスは[履歴索引](../archive/issue343/README.md)を参照し、`git show <元commit>:<元パス>`で取得する。変更していない`experiments/matching_limit/`の旧facadeからは現checkoutでimportできず、再現には元commitの環境が必要。P4-A有限選別予算は正式RF制約ではない。

`full_lpf_checkpoint_import.py`は**実験固有または過去データ再現用**であり、今後の汎用RF探索入口ではない。RF-T008の旧`curate_exp062.py`～`curate_exp065.py`と`review_rft008_exp062_065.py`は、参照する派生集計と合わせて[Issue #397](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/397)で退役した。元処理の逐語原文は[削減前の固定Git履歴](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/762b58d8de97717e3ab651da8ec47ee6daa868c7/scripts)でのみ参照できる。新規Pi Code専用の実装はまだない。

## 過去の管理スクリプト（mainから退役）

2026-10-15の出典棚卸し・46ファイル保全分類を生成した旧ツールは、研究原本を維持したまま既定のリポジトリから退役。必要時は [build_reference_inventory.py](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f0337963688d2a7155b8e28488d6723f2578e73e/scripts/build_reference_inventory.py) と [triage_unlinked_evidence.py](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f0337963688d2a7155b8e28488d6723f2578e73e/scripts/triage_unlinked_evidence.py) を固定コミットから取り出す。当時の旧報告・分類CSVは[固定Git履歴](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/246444b93fb6e6b082af6ece3c5bfc7bcaff05c9/data)から参照しますが、現行正式EXPの原記録やRF保存ゲートは不変更です。

## 新規EXP保存ゲート（main運用中）

EXP-050以降の開始前・保存完了・PR監査は [保存ポリシー](../project/experiment_storage_policy.md) と scripts/audit_new_experiment_storage.py を参照する。対象はEXP-050以降の新規runのmanifestとstorage_record。EXP-001～049（完了済みEXP-048/049を含む）は既存のまま保護し、書き換えない。

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

[全体README](../README.md) ／ [実験原本の案内](../experiments/README.md) ／ [結果の入口](../project/results.md)
