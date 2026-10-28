# 回路解析・探索手法の所在

**研究手法と出典の案内です。**本ページは手法・理論研究の出典リンクを集めるのみで、元ファイルは移動していない。各文書の作成時のRF条件、実行済み検証と未実行計画、回路解析と物理実験の区別を確認する。

## 統合済みの共通回路計算基盤

[PR #164](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/164)で共通回路レイヤーの実装を統合しました。現在の公開入口は[`api.py`](../src/lpf/phase2_models/api.py)、巻線方向・結合符号とL/C接続の構造は[`circuit_layout.py`](../src/lpf/phase2_models/circuit_layout.py)、旧EXPのゼロ枝変換は通常APIと分離した[`vector_migration.py`](../src/lpf/phase2_models/vector_migration.py)です。[公開APIテスト](../tests/test_phase2_public_circuit_api.py)と[構造テスト](../tests/test_phase2_circuit_layout.py)に実装上の不変条件を保持します。

全6設定・不連続28区間、L結合のSPD、固定／可変Cの接続・OFF状態、およびRF条件IDを混同しません。共通forward APIの一致は、外部S2Pを含む独立MNAの全面検証やRF要求適合を意味しません。旧Stage 1の判断経緯・DoDは[Issue #163](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/163)、[Issue #165](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/165)、PR #164、元設計文書の[固定履歴版](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs)から追跡できます。

## 共通回路モデル・実装方法

| 対象 | 元ファイル | 読み方 |
|---|---|---|
| 共通回路モデルとR2作業 | [R2引継ぎ](r2_handoff.md)、[R2独立確認JSON](r2/EXP015_COMMON_MODEL_AUDIT.json) | 旧RF-F001／試験条件に関する保存検証。現行RF-F003性能実績ではない |
| コイル系列の過去の設計仮定 | 下記「過去のLQP02HV/HQ設計仮定」を参照 | 2026-10-12時点の承認・数値モデルの履歴。現在の正式制約はregistryが優先 |
| 探索手法から得た知見 | [topology_search_lessons](topology_search_lessons.md) | 過去時点の探索改善・制約上の限界 |

## 過去のLQP02HV/HQ設計仮定と出典

2026-10-12の当時の承認ルールは、LQP02HVの定数Q=25・0.4～27 nH・チップ面積コスト1を優先し、必要な場合にLQP02HQの定数Q=20・0.2～56 nH・コスト1を追加するというもの。HVのみとHQ併用を分け、HQの本数・最大L・総L・全6設定の最悪ILとH2/H3を比較する方針だった。**これは当時の計算モデル・探索方針であり、現行RF-F003の数値正本でも、Q(f)・SRF・部品実測の保証でもない。** 現行の制約ID・物理範囲は必ず[active registry](../data/constraints/registry.json)の指定JSONから解決する。

旧チェックポイントEXP011-01（L1=56 nHをQ25と扱う）およびEXP014-02（L1=28.56046 nHをQ25と扱う）等は旧仮定の履歴として維持し、現条件への性能達成実績に読み替えない。[EXP-015](../experiments/chatgpt_topology_search/runs/EXP-015/README.md)を後続の当時の検証記録として区別する。当時の優先順位・留保事項を含む[原文（main固定コミット、Git blob `6eb073fc1b1a27e2bc45433e6d238d54e6606857`）](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/52a57cd5fe2e598267e9116fb78131d237f6f711/docs/inductor_series_policy.md)は読み取り専用で復元可能。

## 凍結EXPから共通評価器への移行（実装履歴）

[PR #162](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/162)の共通forward評価器は、以下の凍結ソースを**変更せず**に再利用するための実装。現行の共通回路公開API・接続制約は本ページ冒頭および[PR #164](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/164)を参照。

| 凍結EXPソース | 共通評価器 |
|---|---|
| EXP-042 `optimize.py` | `lpf.phase2_models.exp042` |
| EXP-055 `adapt_f003_4l.py` | `lpf.phase2_models.exp055` |
| EXP-058 `sweep_area3.py` | `lpf.phase2_models.exp058_area3` |
| EXP-058 `sweep_area4.py` | `lpf.phase2_models.exp058_area4` |
| EXP-058 `sweep_area4l_gjm.py` | `lpf.phase2_models.exp058_area4l_gjm` |

当時の検証は保存ベクトルと28不連続区間×3点・全6設定、固定入出力S2P、RF-T007の接地DTC付属0.5 pF/Q40、RF-T008 v3のIC固定Q60・可変Q35を区別する有限サンプルの数値パリティと、別経路の7×7/9×9枝電流MNA。PR #162の記録はこの比較範囲を超えた高密度帯域保証を意味しない。

EXP-050、056/057、059～067の保存済みスクリプトに残るEXP間直接importは**SHA固定された歴史原本**であり、新規EXPの実装入口として許可しない。実験ソースの書換えはmanifestの出典SHAを破壊し得る。共有モジュールのforward一致は独立MNA・電力収支の代替ではなく、元の最適化の再実行、RF-F003正式適合、EM・SRF・Q(f)・製作可能性を証明しない。[実装メモ原文（main固定コミット、Git blob `6b9ce1382a94ebb208059eafd7129a2fd74bb4c7`）](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/52a57cd5fe2e598267e9116fb78131d237f6f711/docs/phase2_shared_evaluator_imports_20261027.md)と[凍結比較テスト](../tests/test_phase2_shared_exp_evaluators.py)を併せて参照する。

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
