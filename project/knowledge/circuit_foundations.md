# 共通回路モデルと独立MNA検証

**対象：** 現役RF Coreへの接続、旧モデル境界、独立枝電流MNAと電力・SPDの検査。旧研究条件の数値・仮説を現行RF-F003適合と混同しない。
**出典：** [旧methods原文](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/d536a3f1a1b79b8e9be3db4752f1a8b05fa60e65/project/methods.md)（PR #411以前のmain固定版）。内容は既存研究の移設であり、新規RF/MNA実行ではない。

## 統合済みの共通回路計算基盤

[PR #164](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/164)で共通回路レイヤーの実装を統合しました。その後の現役schema2の数値入口は[`rf_core/model.py`](../../src/lpf/rf_core/model.py)、設計合法性の窓口は[`search/component_constraints.py`](../../src/lpf/search/component_constraints.py)へ分離されています。巻線方向・結合符号とL/C接続の構造は[`topology_management/circuit_layout.py`](../../src/lpf/topology_management/circuit_layout.py)が正本です。旧`phase2_models/api.py`とゼロ枝変換`vector_migration.py`は#343/D4で退役済みです。[退役前固定原本](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/d3616b8/src/lpf/phase2_models)は歴史確認用であり、新規探索の入口ではありません。[現役RF coreテスト](../../tests/test_issue309_rf_core.py)と[構造テスト](../../tests/test_phase2_circuit_layout.py)に実装上の不変条件を保持します。

全6設定・不連続28区間、L結合のSPD、固定／可変Cの接続・OFF状態、およびRF条件IDを混同しません。共通forward APIの一致は、外部S2Pを含む独立MNAの全面検証やRF要求適合を意味しません。旧Stage 1の判断経緯・DoDは[Issue #163](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/163)、[Issue #165](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/165)、PR #164、元設計文書の[固定履歴版](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs)から追跡できます。

## 共通回路モデル・実装方法

| 対象 | 元ファイル | 読み方 |
|---|---|---|
| 共通回路モデルとR2作業 | [R2引継ぎ原文](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/3370ea4/docs/r2_handoff.md)、[R2独立確認JSON](../../docs/r2/EXP015_COMMON_MODEL_AUDIT.json) | 旧RF-F001／試験条件に関する保存検証。現行RF-F003性能実績ではない |
| コイル系列の過去の設計仮定 | 下記「過去のLQP02HV/HQ設計仮定」を参照 | 2026-10-12時点の承認・数値モデルの履歴。現在の正式制約はregistryが優先 |
| 探索手法から得た知見 | [topology_search_lessons原文](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/3370ea4/docs/topology_search_lessons.md) | 過去時点の探索改善・制約上の限界 |

## 過去のLQP02HV/HQ設計仮定と出典

2026-10-12の当時の承認ルールは、LQP02HVの定数Q=25・0.4～27 nH・チップ面積コスト1を優先し、必要な場合にLQP02HQの定数Q=20・0.2～56 nH・コスト1を追加するというもの。HVのみとHQ併用を分け、HQの本数・最大L・総L・全6設定の最悪ILとH2/H3を比較する方針だった。**これは当時の計算モデル・探索方針であり、現行RF-F003の数値正本でも、Q(f)・SRF・部品実測の保証でもない。** 現行の制約ID・物理範囲は必ず[active registry](../../rf/constraints/registry.json)の指定JSONから解決する。

旧チェックポイントEXP011-01（L1=56 nHをQ25と扱う）およびEXP014-02（L1=28.56046 nHをQ25と扱う）等は旧仮定の履歴として維持し、現条件への性能達成実績に読み替えない。[EXP-015](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/experiments/chatgpt_topology_search/runs/EXP-015/README.md)を後続の当時の検証記録として区別する。当時の優先順位・留保事項を含む[原文（main固定コミット、Git blob `6eb073fc1b1a27e2bc45433e6d238d54e6606857`）](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/52a57cd5fe2e598267e9116fb78131d237f6f711/docs/inductor_series_policy.md)は読み取り専用で復元可能。

## 凍結EXPから共通評価器への移行（実装履歴）

[PR #162](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/162)では以下の共通forward評価器へ移行しました。**下表の旧モジュールは後の#343/D4で退役済み**です。凍結EXP原本は変更せず、現役の数値入口は本ページ冒頭を参照します。

| 凍結EXPソース | 共通評価器 |
|---|---|
| EXP-042 `optimize.py` | `lpf.phase2_models.exp042` |
| EXP-055 `adapt_f003_4l.py` | `lpf.phase2_models.exp055` |
| EXP-058 `sweep_area3.py` | `lpf.phase2_models.exp058_area3` |
| EXP-058 `sweep_area4.py` | `lpf.phase2_models.exp058_area4` |
| EXP-058 `sweep_area4l_gjm.py` | `lpf.phase2_models.exp058_area4l_gjm` |

当時の検証は保存ベクトルと28不連続区間×3点・全6設定、固定入出力S2P、RF-T007の接地DTC付属0.5 pF/Q40、RF-T008 v3のIC固定Q60・可変Q35を区別する有限サンプルの数値パリティと、別経路の7×7/9×9枝電流MNA。PR #162の記録はこの比較範囲を超えた高密度帯域保証を意味しない。

EXP-050、056/057、059～067の保存済みスクリプトに残るEXP間直接importは**SHA固定された歴史原本**であり、新規EXPの実装入口として許可しない。実験ソースの書換えはmanifestの出典SHAを破壊し得る。共有モジュールのforward一致は独立MNA・電力収支の代替ではなく、元の最適化の再実行、RF-F003正式適合、EM・SRF・Q(f)・製作可能性を証明しない。[実装メモ原文（main固定コミット、Git blob `6b9ce1382a94ebb208059eafd7129a2fd74bb4c7`）](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/52a57cd5fe2e598267e9116fb78131d237f6f711/docs/phase2_shared_evaluator_imports_20261027.md)と[当時の凍結比較テスト](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/d3616b8/tests/test_phase2_shared_exp_evaluators.py)を併せて参照する。

## 独立枝電流MNAと検証レベル

Issue #163/#168の開発記録を統合します。現役実装・対応条件・完了ゲートは[roadmap](../roadmap.md)を確認し、旧WIPの「未実装／レビュー待ち」を現在の状態としません。

- hot-node電圧V、向き付きL電流I、incidence Bに対し `[Yc+Yterm, B; B.T, −Z] [V; I] = [J; 0]`、`Z=ω(diag(L/Q)+jM)`、`Mij=kij√(LiLj)`。Cは個別に`ωC/(1/Q−j)`でstamp。L方向反転では関連k符号も反転する。裸のsolverは部品適合ゲートではなく、`validate_components`等を別途実施する。
- 50Ω行／電流スケーリング後の条件数≥1e12、非有限、非SPDはfail closed。この条件数閾値は数値ガードでありRF制約や物理的不可能性ではない。
- 外部境界の独立解法はSHA確認済みRI S2Pを直接port Yへ変換し、源・負荷端点を消去する。forward LPFのnodal/Schur/ABCDを再利用しない。peak phasorの電力は`Re(VI*)/2`、1V peak Theveninの`Pavs=1/(8Re(Zs))`。上の旧RF-T003 **RMS**式と振幅規約を混ぜない。源抵抗損失を入力電力に含めず、S2P差分・L/C散逸・負荷を二重計上しない。
- 当時の5保存ベクトル×28区間×端点/中点=420 canonical sampleは**6×28の直積ではない**。最大IL差4.476419235288631e−13dB、電力残差5.833007687972014e−17W（元ローカル記録）。cross scanは診断であってcanonical RF判定ではない。局所極値refinementの成功も不可視ピークの不存在・連続区間保証にはならない。
- candidate-bound限定監査は部品／電気役割を再検査し、小格子のforward/MNA/powerを再計算して初めてprior recordと比較する。definition/vector/source/dirty state、policy、bands/S2P、環境、sample座標・許容差を結ぶ。保存record単独は認証でも元EXP出自の証明でもなく、dense/physical/owner証拠を代替しない。限定成功後に`not_checked`の二重表示を除くことと、昇格条件の緩和は別である。
- CI棚卸し#174の区別を維持する：凍結EXP対共通forward、公開API境界、独立MNA/外部電力は似たILを検査しても別の検出能力。非有限・SPD・符号・設定間固定値、S2P SHA/範囲/28区間欠落、ゼロ枝と寄生、出典/予約/保存整合性を保持する。人工的な特異行列・極深零点fixtureは失敗分類のテストで、物理的到達の証明ではない。裸solverの巨大有限入力を部品範囲外だけで契約外と断定しない。

旧T01〜T13と退役assertionの細目・当時のCI値は[固定開発文書](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/3370ea4/docs)にあり、現在のCI分類・モジュールは`scripts/select_ci_tests.py`とそのテストを正本とします。45/66 inventory不一致等の旧known FAILを、後日の文書整理で過去PASSにしません。
