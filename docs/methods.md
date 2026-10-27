# 回路解析・探索手法の所在

**研究手法と出典の案内です。**本ページは手法・理論研究の出典リンクを集めるのみで、元ファイルは移動していない。各文書の作成時のRF条件、実行済み検証と未実行計画、回路解析と物理実験の区別を確認する。

## 統合済みの共通回路計算基盤

[PR #164](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/164)で共通回路レイヤーの実装を統合しました。現在の公開入口は[`api.py`](../src/lpf/phase2_models/api.py)、巻線方向・結合符号とL/C接続の構造は[`circuit_layout.py`](../src/lpf/phase2_models/circuit_layout.py)、旧EXPのゼロ枝変換は通常APIと分離した[`vector_migration.py`](../src/lpf/phase2_models/vector_migration.py)です。[公開APIテスト](../tests/test_phase2_public_circuit_api.py)と[構造テスト](../tests/test_phase2_circuit_layout.py)に実装上の不変条件を保持します。

全6設定・不連続28区間、L結合のSPD、固定／可変Cの接続・OFF状態、およびRF条件IDを混同しません。共通forward APIの一致は、外部S2Pを含む独立MNAの全面検証やRF要求適合を意味しません。旧Stage 1の判断経緯・DoDは[Issue #163](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/163)、[Issue #165](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/165)、PR #164、元設計文書の[固定履歴版](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs)から追跡できます。

## 共通回路モデル・実装方法

| 対象 | 元ファイル | 読み方 |
|---|---|---|
| 共通回路モデルとR2作業 | [R2引継ぎ](r2_handoff.md)、[R2独立確認JSON](r2/EXP015_COMMON_MODEL_AUDIT.json) | 旧RF-F001／試験条件に関する保存検証。現行RF-F003性能実績ではない |
| コイル系列ルール | [inductor_series_policy](inductor_series_policy.md) | Q仮定・LQP02HV/HQ系列の当時の設計方針 |
| 探索手法から得た知見 | [topology_search_lessons](topology_search_lessons.md) | 過去時点の探索改善・制約上の限界 |

## 磁気結合と伝送零点の基礎研究

これらの文書は2026-10-16時点の理論検討です。**正式RF-F003全系の数値最適化・製作・3D EM検証とは区別**してください。

- [T型3コイルの磁気結合とQの基礎](phase2_t_coupled_inductor_q_foundations_20261016.md)
- [T型の一様モードと固有モード](phase2_t_coupled_inductor_uniform_mode_20261016.md)
- [T型の平面配置・幾何学的結合](phase2_t_coupled_inductor_planar_geometry_20261016.md)
- [T型結合ペアの検討](phase2_t_two_pair_coupling_20261016.md)
- [T型高電流モード](phase2_t_shunt_high_current_modes_20261016.md)
- [T型の通過帯シャント電流比較](phase2_t_shunt_current_matched_passband_20261016.md)
- [π型伝送零点の再配置](phase2_pi_notch_retarget_20261016.md)
- [π型2組結合の検討](phase2_pi_two_pair_coupling_20261016.md)
- [T/π型の共通条件損失比較](phase2_t_pi_common_conditions_loss_comparison_20261016.md)

## 正本と証拠に戻る

- [現行正式RF-F003 JSON](../data/constraints/formal/RF-F003.json)、[試験RF-T005](../data/constraints/trial/RF-T005.json)。
- [2026-10-17の3L/4L保存候補・制約別パレート](pareto_rf_t005_rf_f003_20261017.md)。
- [旧資料の分類・処置](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/170) と [W3固有情報の保全](archive/w3_consolidated_documents_20261017.md)。

**本索引は研究の新たな数値解析や実験結果を提供しません。**
