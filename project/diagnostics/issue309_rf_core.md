# Issue #309 — Stage 2 共通RFコア

## スコープ

#306 v1.0 / #309 のソフトウェア実装。RF条件、既存EXP、探索予算・順位・Runnerは変更しない。
正式RF-F003と明示opt-in RF-T005/T006/T007/T008を同じAPIで構築する。
Stage 3の要求コンパイル・格子生成・性能閾値判定、Stage 4のRunner接続は未実装のまま。

## APIと責務

```python
import numpy as np
from lpf.constraint_versions import load_constraint
from lpf.rf_core import build_rf_model, EvaluationGrid
from lpf.rf_core.independent import validate_response
from lpf.search.component_constraints import validate_values

policy = load_constraint('RF-T008', allow_trial=True)  # F003はopt-in不要
model = build_rf_model(definition, policy)  # 既存CircuitDefinitionを入力
# 以下は呼出側の確定済みサンプル配列。RFコアは点数・要求を決めない。
grid = EvaluationGrid(frequency_hz, setting_indices, segment_ids)
evaluator = model.evaluator(grid)
validate_values(definition, model.schema, x, policy)  # 設計合法性はsearch側
response = evaluator.evaluate(x)
# 未検証のresponseを独立検証済みへ書き換えない。別記録を返す。
evidence = validate_response(model, x, response, atol=1e-9)
```

- `RFModel`は接続・Q・schema・承認policyのJSON snapshot/fingerprintのみ保持。xや候補履歴は保持しない。
- 承認済み現役schema 2とのfingerprint照合により、旧ID/schema・未知/改変モデルを拒否。
  trialの明示opt-inは既存`load_constraint(..., allow_trial=True)`で実施する。
- 新builderはRF-ID別forward/adapterを生成しない。既存の部品metadata・接続検査・T008 layout・T007寄生枝生成を再利用。
  T007の0.5 pF/Q40はschemaの定数枝、T008のIC固定C/Q60はx内の設定不変な探索変数。可変C/Q35と区別する。
- `EvaluationGrid`の3配列はコピー後にimmutable bytesをbackingに持つ。sample順序、重複周波数、各区間の独立identityを保持する。
  `setting`は既存CASES順0..5、`segment` 0..27は`rf/bands.csv`の行番号。
  呼出側が確定する追加区間は28以上のIDを使用可能（T006端点テストでは28）。
  任意のcross-setting格子も受け付ける。canonical settingや区間内所属の要求解釈・全区間網羅の強制はStage 3/呼出側の責務であり、この数値型では行わない。
- 公開応答は同一格子の`s: complex128[N,2,2]`、4個の`float64[N]`、policy ID/SHAと格子参照。
  GT/GAを重複保持しない。応答配列もimmutable。`independent_mna_checked=False`はforwardだけでは変化しない。
- 数値SPD安全性は既存kernelで維持するが、設計bounds/SPD認定や性能閾値・順位をコアへ移管しない。

## 数値規約

両port電流はネットワークへ流入する向き。peak phasorを使い、`Z=(Zs,Zl)`について

```
a = (V + Z I) / (2 sqrt(Re Z))
b = (V - conj(Z) I) / (2 sqrt(Re Z))
b = S a
P_into_network = (|a|² - |b|²)/2
```

現役の参照は入力50 Ω、出力60−j40 Ω。**元Touchstoneは50 Ω参照のまま**読み、完成外部2-portでpower-wave変換する。
指定Thevenin source・loadではa2=0、利用可能source powerに対して

- `GT=|S21|²`、`IL=-10 log10(GT)`。
- sourceを固定し出力を共役整合できるavailable powerは`GA=GT/(1-|S22|²)`、`APL=-10 log10(GA)`。
- `InRL=-20 log10(|S11|)`、`OutRL=-20 log10(|S22|)`。

GAとGTは一般に異なる。理想throughでも現在の複素loadはsourceと不整合なのでILは0でなく、APLは0。
テストはthroughおよび既知の直列20 Ω抵抗について、直接のインピーダンス/電力式からS11/S22/GT/GAを確認する。
損失なしthroughでは複素参照でも`Sᴴ S=I`を確認。

主forwardは既存nodal stampと共有Schur reductionを使用し、core Y→50 Ω S→2固定S2PとのRedheffer積→power-wave変換を行う。
既存ABCDの伝送admittance割り算による伝送零点拒否を新経路へ持ち込まないため、外部cascadeはSで接続する。
既存IL専用経路のABCD/floor挙動は歴史的呼出側のため変更せず、新経路と明確に分離する。
新経路は`1e-300` floorなし。厳密なゼロ伝送/反射のdBは`+inf`として返し、NaN・特異求解・非有限forwardは例外。
log-amplitudeで計算するため、例えば`|S21|=1e-200`のILは4000 dB（gainの二乗underflowによる偽の零点ではない）。
`1-|S22|²<=0`では有限なavailable gainを定義できず、明示例外とする。

## 独立検証

`rf_core/independent.py`は2つの外部Thevenin駆動境界条件で既存branch-current MNAを直接求解する。
固定S2Pは直接Yに変換し、主forwardのnodal/Schur/S cascade/ABCDを利用しない。
入出力V/IからSを復元し、available gainは出力Thevenin impedanceと開放電圧から別計算する。
既存`evaluate_independent_sample`のGT/IL・素子別/固定S2P損失・電力収支も再利用する。

`validate_response`は全sampleのS/IL/APL/InRL/OutRLを絶対tol=1e-9（Sは無次元、各指標はdB）で比較。
passivity `min eig(I−SᴴS)>=−1e-10`、個別損失`>=−1e-12 W`、電力収支残差`<=1e-12 W`を確認する。
非SPD、unproven role、非受動、非有限、不一致、S2P SHA改竄をPASSにしない。
不正shape/dtype/NaN応答も拒否。実施済みsample数・実測最大絶対差・tolを別記録に返す。
これらは限られた格子の数値監査であり、部品合法性、性能合否、連続周波数、EM/SRF/Q(f)/公差/実測を認定しない。

## 検証と再現

Python 3.12 / `uv sync --frozen`。詳細はPRの実行結果とHEADを参照。

```bash
OPENBLAS_NUM_THREADS=1 PYTHONPATH=tests uv run --frozen python -m unittest test_issue309_rf_core -v
```

新規6テスト内で次を実行：

- 5条件×canonical全28区間×2端点（280 sample）：shape/dtype、格子identity、既存ABCD IL parity、独立MNA全指標。
- T008全6設定×28個別区間×2端点（336 sample）：cross-settingの独立MNA監査。
- T006全6設定×3/6 GHz両端（12 sample）：S2P利用と独立MNA、6 GHz超外挿拒否。
- 解析through/抵抗、GT≠GA、複素参照共役/受動性/電力、厳密零点とunderflow回避、特異性、S2P改竄、非SPD、不一致・非受動、未知/旧policy、series role拒否。
- forwardをpatchで禁止した状態の独立MNA、policy/格子/応答の凍結、複数x後の再現。

通常smokeは`.github/workflows/audit.yml`の通常実行run steps（手動integrationを除く）、
sparseは`.github/workflows/pi-sparse-rf.yml`のRFテストで再現。
新テストを両CIへ登録。新EXP・本番探索・dense/連続帯域保証は実行しない。

## 対象effective SHA（変更なし）

| ID | SHA256 |
|---|---|
| RF-F003 | `e12c42b11d12db7f20983c48cfa441ea96e362e533450d5862aa8a271c82af86` |
| RF-T005 | `413c1f2979926dd8bc56fe6730603864f6c582e2a72ec3f7bb0ab1ba81a7becd` |
| RF-T006 | `1d22e01d6da243bed24970de90a496e8f2d38b11bd5a5fae78e001398f647e1c` |
| RF-T007 | `5452690de1c8590f1f7c306f76e41692e1885ac190da3cef050f1d926145c944` |
| RF-T008 | `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532` |

数値正本は引き続きregistryと現役JSON。本表はこの実装のレビュー対象を記録したもので、独立したRF数値権限ではない。
