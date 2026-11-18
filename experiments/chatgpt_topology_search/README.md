# ChatGPT回路探索 — EXP記録・歴史資料の入口

このディレクトリの[`runs/EXP-NNN/`](runs/)は正式実験の記録と過去研究の証拠を置く領域です。**新しい開発Runの自動生成先ではありません。** 以前の`config.json`／`circuit.json`／`optimize.py`／`results.json`／`summary.md`の一律作成テンプレート、`matching_limit/`を現役探索Runnerとする案内は廃止しています。保存済みの歴史的ファイルは元のRF条件・ソース・検証状態の証拠として読みます。

## 現行の実行入口

- **RF-T009試験profileの逐次開発Run:** [`scripts/run_rf_search.py develop`](../../scripts/README.md#rf-t009-開発run)。全seed×armの入力・Plan・予算を凍結し、Search→Terminalの結果をGit管理外の開発rawとして記録します。正式EXPへの自動登録・G0予約・正式G2認定は行いません。
- **正式RFの数値正本:** [`rf/constraints/registry.json`](../../rf/constraints/registry.json)の`active_formal_id`（現在RF-F003）、[bands](../../rf/bands.csv)とSHA固定[S2P](../../rf/parasitics/)。RF-T009は別登録の[試験`rf_performance_profile`](../../project/minimax_profile.md)であり、正式RFの性能条件とは混同しません。旧`data/design_constraints.json`は互換参照であり正本ではありません。
- **新規正式EXP:** [運用正本](../../project/instructions.md)・[G0〜G5保存ポリシー](../../project/experiment_storage_policy.md)・[外部管理手順](../../project/campaign_workflow.md)に従い、main番号予約、完全checkout、RF ID/実効SHA、全6設定の完全vector、ソース/格子/seed・実行/検証状態・選別証拠を残します。新形式の正式Campaign G2は未接続です。

過去のEXP manifestや記録済み条件は、現行RF-T009仕様に合わせて遡及変更しません。歴史的な候補値を現行正式RF適合とみなさず、研究上の代表成果と限界は[methods](../../project/methods.md)・[results](../../project/results.md)、残存原本は[EXP索引](../../data/experiment_index.csv)とGit固定履歴で確認します。
