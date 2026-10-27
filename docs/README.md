# 研究文書

日常的に参照する文書を以下に限定します。正式RF数値は[レジストリ](../data/constraints/registry.json)が選ぶ版、帯域は[bands.csv](../data/bands.csv)、固定外部S2Pは正式制約の指定ファイルが正本です。

| 目的 | 文書 |
|---|---|
| 研究・開発運用と承認境界 | [運用指示](chatgpt_project_instructions.md) |
| 開発状況・次のゲート | [ロードマップ](roadmap.md) |
| RF仕様の読み方 | [仕様](specification.md) |
| トポロジー・数値解析・技術研究の出典 | [研究手法](methods.md) |
| 代表候補と独立検証の出典 | [結果](results.md) |
| 二段階SLSQP運用 | [SLSQP](slsqp_iteration_policy.md) |
| 新規EXPの保存・承認ゲート | [実験保存ポリシー](governance/phase2_experiment_storage_policy.md) |

実験原本・候補の完全ベクトルは[EXP](../experiments/README.md)から確認します。過去の進捗・削除審査・時点別の手続き記録は[Issue #170](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/170)、関連PRとGit履歴で追跡します。固有の理論導出・数値証拠は出典を評価せず機械的に削除しません。
