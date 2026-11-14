# Issue #419 — power-response診断：両候補とも本番不採用

## 結論

RF-T008 rev3 **trial opt-in/full_lpf**の固定100 vectorでは、A（V/I配列を代数整理）は完全forwardの改善を示さず、B（無スケーリング2×2直接解）は改善方向だが大きな外乱があった。さらに**両案とも有限な極端値で現行STOP契約と異なる**。したがって効果・安全性の採用条件を満たさず、`src/`は変更しない。A+BやSolverの比較は行わない。Bの観測は一般的な性能改善の証明ではない。#417のdeep 12.705 msをplain削減可能量とはみなしていない。

## 識別子・方法

- 測定時main/候補の本番HEADはともに `523f3ab8d0d89323fd521c9b6738728f8babc54b`、本番差分なし。source identity `b701aee50fa2a506eaef942109fb93a96fe8405e7c0b1e7715b539f6293e467e`、`model.py` SHA `0e1152cb0b466b9cbc29d8200e3ab30a35db972fbaa07300594102867589e497`。候補は診断driver内だけで、同一ソースの関数を生成して差し替え。計測driver SHA `c096bda549c8dec5ee5a643bcd29eada99cb4614ed2eb7928e34cd6c34bf1354`。#418は測定時未マージDraft。
- RF-T008 effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、active正式RF-F003 `e12c42b11d12db7f20983c48cfa441ea96e362e533450d5862aa8a271c82af86`には速度・RF適合を一般化しない。Plan `8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e`、grid `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、6設定・28別区間・70点、固定S2Pと複素参照Zを含む。
- bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、入力S2P `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、出力S2P `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`、starts seed1002 SHA `63b671ea269656843df118230b7d920e91515188235809b6dd0efd667ac997ab`。固定vectorファイル `e87355eb364073a5743062e8e4ee7c90c3012cbfb5e38bef6283860381736ba0`、100 vector個別SHA照合。各processで旧forwardから先に収集した100個のS配列連結SHA `1512e77f269a1524727c1bd8d9e420a541714ccdb9caae3f00b2b9da2713bb02`は全78 processで一致。
- Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、OpenBLAS 0.3.34.106.0、WSL2共有host Ryzen 7 PRO 4750G、affinity CPU 0、OPENBLAS/OMP/MKL各1 thread。CPU占有・温度・他負荷は未制御。各runは別process、同一入力100回warmup後、旧新を隣接ペアで順序交互。外れ値を含む。setupはS収集100 forwardを含みwall 0.686–0.805秒、CPU 0.686–0.804秒で測定区間外。

## 同一batchのplainと内部計時

値はms/100回。対応差は候補−旧の**各ペア内**差。winsは候補が速い組数。CPU中央値も併記。全runのwall/CPU/setup、順序、計器値、数値比較は[compact JSON](issue419_runs.json)（SHA `f7a07b956da7e1e5e5fc55575f15198ed38a0d23eb0e139dc96169cd30c8240c`）。元の未圧縮JSON SHA `7a6108f9a883b1182d0eb8e987597ecace0962e8bf9443945fed2d3229e84233`。

| plain | old wall / CPU中央値 | candidate wall / CPU中央値 | 対応差中央値 [min,max] | wins |
|---|---:|---:|---:|---:|
| 単独 A | 11.880 / 11.880 | 12.244 / 12.244 | +0.295 [−9.506,+0.796] | 3/8 |
| 単独 B | 12.284 / 12.284 | 11.027 / 11.027 | −1.005 [−2.041,+6.226] | 6/8 |
| 完全forward A | 49.785 / 49.777 | 51.828 / 51.775 | +1.451 [−38.709,+28.509] | 2/8 |
| 完全forward B | 49.929 / 49.764 | 48.506 / 48.498 | −1.667 [−28.578,+0.906] | 6/8 |

単独は収集済みSから完全な`power_response`を100回、forwardは実際の`RFEvaluator.evaluate()`を100回。前者にRF forwardは含まない。旧Aの87.929 ms、新Aの77.758 ms、旧Bの76.762 ms等の外れ値も保持。A/Bは異なるbatchの旧と比較しており相互順位は未確定。候補Bの有効性はSTOP差で否定されるので速度再測定は採用の根拠にならない。

別processで旧/候補を各3回測った**単独関数内の非重複計器区間**（入力validateは区間外、各100回の合計中央値）は、旧 construct 2.994–3.051、solve 2.737–2.772、metrics/有限検査 5.208–5.394 ms。Aは3.303/2.674/5.502、Bは2.984/2.345/4.866 ms。これは細分した計時付き局所値でありplain forwardへ加算しない。計器付き全体の旧中央値12.225/12.470 ms対、別batchの旧局所plain中央値11.880/12.284 msは+0.345/+0.186 msだが、**対応測定ではなく外乱を含む概算校正**。B計器runには62.578 ms外れ値があり、純粋な計器負荷や速度率と断定しない。

## 数値・科学回帰

- 固定100 vectorで全複素S・IL/APL/両RL・worst IL・順序付きmandatory g 42個を旧新比較。`atol=1e-9, rtol=1e-11`以内、ビット一致を要求しない。最大絶対差 A: S `6.81e-16`、IL `5.33e-15`、APL `8.88e-15`、入力RL `2.13e-14`、出力RL `3.20e-14`、worst IL `5.33e-15`、mandatory `7.11e-15`。B: S `3.51e-16`、IL `5.33e-15`、APL `9.77e-15`、入力RL `1.07e-14`、出力RL `7.11e-15`、worst IL `5.33e-15`、mandatory `7.11e-15`。最大相対差はJSON参照（小さい分母では解釈に注意）。
- 代表index 0/49/99の各70点を両候補で独立branch-current MNAと照合、最大絶対差 A `2.23e-12`、B `2.22e-12`（基準1e-9）。独立側は新forward・`power_response`を呼ばず、固定S2P込みの外部passivity、各枝とS2P損失、電力残差、SPDを検査。これは全100 vectorや連続帯域の証明ではない。
- `test_issue419_power_probe.py`はゼロ透過/+inf、S21=1e-200、複素Z、入力非有限・非受動Z、reflection境界、singular/near-singular、全エラーコードと伝播を検査。`db_invalid`および一部の非有限solveは障害注入であり自然発生を主張しない。STOP差の代表（旧 / A / B）：`S=-I, Zs=Zl=1e-300` は `available_gain_undefined / wave_singular / available_gain_undefined`、`S=0, Zs=Zl=1e-308` は `available_gain_undefined / available_gain_undefined / wave_nonfinite`、`S=-I, Zs=Zl=1e-320` は `ok / wave_singular / wave_nonfinite`。全て有限、Re Z>0。Aは係数の丸めで残差を失い、Bは複素行列式の非スケーリング演算でoverflow/underflowする。これらは現行の許容入力に対する契約差であり、実RF試料の性能主張ではない。
- 既存のRF-F003/T005/T006/T007/T008モデル・全6設定/各別区間・T006追加帯域・H2/H3・固定S2P・SPD・異常伝播・独立MNA/電力・不変配列の関連回帰を実行。実行したtestファイルと結果はPRに列挙。旧`test_rft003_loss.py`は現行treeにない`data/validation/rft003_20261012/target30_results.json`を要求して失敗し、復元していない。任意の全入力、連続周波数、EM/SRF/Q(f)/公差/実測は未検証。

## 消費と再現

本suiteは78 process：各setupでS収集100 forward（7,800）、forward 32 processのwarmupと計測（6,400）、同値性2 processの旧新（400）、計 **14,600 forward / 1,022,000 requested samples**。局所plain/detail 44 processは各warmup+測定のpower_response 200回、**8,800局所呼出**（setupに含まれる呼出は別）。独立MNAは2候補×3 vector×70点、Solver 0。別途bring-upは失敗1回（setup 100+旧forward 1、inspect対象の修正前）と成功1回（setup 100+旧新200、MNA 210点）。既存unit testのforward数は上記に含めない。EXP・正式Campaign・探索は実施していない。

```bash
uv sync --frozen
uv run --frozen python project/diagnostics/issue419_probe.py --pairs 8 --output /tmp/issue419-replay-new.json
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --frozen python -m unittest discover -s tests -p 'test_issue419_power_probe.py' -v
```

出力先は未存在にする。driverは利用可能な最小CPUを選ぶので、別hostではaffinityを確認する。測定の忠実な再現には元HEAD `523f3ab8…`で本driverを使う（レポート提出commitのHEADではsource identityが変わる）。`issue419_runs.json`には全78 runの集計に必要なwall/CPU/setup・timer・比較結果を保持する。
