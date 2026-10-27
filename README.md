# Reconfigurable RF LPF Research

6つのLTEバンド設定に対応する、再構成可能な受動RFローパスフィルタの研究・数値解析用リポジトリです。

## 現在の入口

| 確認対象 | 正本・入口 |
|---|---|
| 正式なRF数値条件 | [制約レジストリ](data/constraints/registry.json)のactive正式JSON（現在RF-F003） |
| 周波数帯・固定寄生 | [bands.csv](data/bands.csv)／[固定S2P](data/parasitics/) |
| 仕様の意味・制約の解釈 | [設計仕様](docs/specification.md) |
| 現在地と次の開発ゲート | [ロードマップ](docs/roadmap.md)／[Issue #163](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/163) |
| 保存済み研究成果 | [結果一覧](docs/results/README.md)／[実験索引](data/experiment_index.csv) |
| 実験原本・検証根拠 | [experiments](experiments/README.md) |
| 研究運用ルール | [プロジェクト運用指示](docs/chatgpt_project_instructions.md) |
| 文書・データ整理 | [Issue #170](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/170) |

RF-F003（正式）とRF-T005/T006/T007/T008（試験）は別の条件です。異なる実効制約ID・SHA、評価格子、検証水準を混ぜて最良値を比較しません。有限探索のbest-foundは大域最適性や実装性能の証明ではありません。

## 開発と実験

共通RF解析は[src/lpf](src/lpf/)、テストは[tests](tests/)、実験単位の原本は[experiments/chatgpt_topology_search/runs](experiments/chatgpt_topology_search/runs/)で管理します。作業はIssue → 実装・検証 → Draft PR → 独立レビュー → 承認範囲でマージの順です。

新規EXPは[mainの中央予約台帳](data/experiment_number_registry.csv)への予約・照合後に開始し、[実験保存規則](docs/governance/phase2_experiment_storage_policy.md)に従って証拠を保全します。新しいPi Codeローカル探索実行器は未実装です。過去の研究・開発経緯は[文書索引](docs/README.md)、原EXP、Issue・PR・Git履歴から参照します。
