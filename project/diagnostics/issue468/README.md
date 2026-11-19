# Issue #468: Hybrid 収束と L1/L2 時間診断

## 条件と入力照合

開発診断であり正式EXPではない。実行ソース `f29049f5296f3e91b69d2a18b0989c63af4ee9d3`、source SHA `f9592df27eb092d8a4b4d4849ea3513f6d880e4d4d30a70fb38fb8e7e8a3d0d7`、Plan SHA `7d49e1a5316bef3bebead6b7e4c50c9fd4d134497303ab18c5da18d8ae7e1f20`。RF-T010 effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、base RF-T008 rev3 `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。25変数・全物理bounds・Hybrid sum（正違反量二乗和）・sigma 0.1、Search 70点、Terminal 476点、独立MNA `[0,111]`、checkpoint 1000 forward。6設定・28区間、外部S2Pを含む。

実行前に旧Plan canonical SHA `dc477e77ed0633047345e04f450ccd2df84bfdd3ddbb0a3395bfed1a8d0e69dd`、#461と#465双方の対象Job receipt記載全ファイルのバイト数・SHA、input vector、#465 `paired.csv`とSHAを照合した。1008初期SHA `5a0ba8c5b2a3e87bd13775a3191825d15260302c73a9d057e7403fe1cda343a8`、1013初期SHA `6e06d271e0ea54eecb547cfff045a6edda4850bfaa1f9c23bf9f3037ab867131`。固定入力と予算の事前凍結を確認後、既存CLIで各1 Jobのみ逐次実行。計時あり、exit 4（双方未収束）、run完了。上限／実消費はSearch 200,000 forward、Terminal 2、RF requested 14,000,952 samples、MNA 4 samples。予約の解放・不明はいずれも0。異常STOP、再試行なし。

原本・receipt・診断JSON・固定入力・CLI stdout/stderrは `/tmp/issue468-diagnostics-uf83ft3k/` に保持（システム一時領域、永続性保証なし）。各receiptの全記載ファイルの長さとSHA、plan/source、初期vector、予算、Terminal最大margin、物理boundsとSPD、Terminal有限格子passivity/power、独立MNA spotを照合。#465の対応Jobと最終vector SHA・Terminal Jは完全一致。これはplain/timedの速度同等性ではない。

## 局所収束の観測

| seed | run数 | nfev（run順） | nit（run順） | 成功／予算切れ | Terminal J [dB] |
|---|---:|---|---|---:|---:|
| 1008 | 12 | 1794, 4368, 2548, 2756, 1664, 1638, 1924, 2574, 3276, 3900, 2106, 71452 | 49, 149, 85, 82, 50, 49, 55, 81, 110, 121, 65, 2382 | 11／1 | 4.3610526691 |
| 1013 | 3 | 29874, 24648, 45478 | 953, 924, 1313 | 2／1 | 0.7477583470 |

`sum(nfev)=100000` は両stepで一致。成功は全件 L-BFGS-B の `RELATIVE REDUCTION OF F`、linesearch失敗0。最後のrunはいずれも `status=null`、success false、`evaluation_budget_exhausted`；その終点は最後の評価点であり、局所収束解ではない。run開始→終了objective [dB²] は1008で `(44408.87→5143.05), (34156.54→6659.29), (18221.50→6659.63), (18383.68→6652.28), (17515.82→6654.69), (29557.48→6654.66), (29017.18→6653.03), (17268.39→6656.31), (16680.32→6652.54), (17148.75→6652.28), (17648.41→6653.85), (29861.74→128.77)`、1013で `(28654.24→301.15), (18169.98→1322.21), (25034.85→2.93)`。Search目的とTerminal Jは別量。

局所run終了点の境界近傍座標数は1008が `[10,19,15,17,15,15,18,13,13,18,11,7]`、1013が `[9,17,0]` /25。物理bounds幅で正規化して `numpy.isclose`（atol 1e-8、既定rtol 1e-5）を0または1と比較した参考値であり、物理的な実現性を意味しない。完全vectorはraw参照。

## 時間（inclusive、重複あり）

| seed | Job [s] | Search [s] | solver [s] | Search RF evaluate [s] | RF/Search | checkpoint [s] | Terminal RF [ms] |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1008 | 66.023 | 65.642 | 65.621 | 57.034 | 86.9% | 0.907 (100回) | 5.013 |
| 1013 | 66.985 | 66.567 | 66.528 | 57.817 | 86.9% | 0.931 (101回) | 4.880 |

局所run wall [s]（run順）は1008 `[1.349,2.828,1.606,1.707,1.066,1.029,1.293,1.657,2.049,2.519,1.287,47.231]`、1013 `[20.161,16.372,29.995]`。最後は予算切れイベント。L1/L2はinclusiveで足し合わせない。RF/Searchは包含区間の比であり他の残余全部をSciPy・数値勾配とは同定できない。CLI全体実wall 133.79秒。L3未計測。

非RF偽関数200,000回、warmup後の交互6組ではplain中央値0.0464秒、timed中央値0.4369秒、差約1.95 μs/呼出（他処理との同時実行によるばらつきあり）。実RFの全体overheadやplain速度の推定ではない。環境: WSL2 Linux x86_64、Ryzen 7 PRO 4750G、16論理CPU、Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1。OMP/MKL/OPENBLAS thread環境変数は未設定、実thread数未確認。異環境の過去1330秒/20 seedと速度優劣は比較しない。

後続候補（優先順はレビュー後に決定）: (1) RF evaluator内部を同じCLIでL3計測してホット領域を特定、(2) 数値勾配の評価重複と局所run内の費用を分離、(3) 収束・境界偏りを維持するOptimizer改善の検討。今回の計測だけで品質を変えず高速化できるとは証明できない。

有限格子の観測に限り、連続周波数保証、密格子、EM、SRF、Q(f)、製造ばらつきや実測は未検証。タイマーの失敗／未観測の意味と使い方は `scripts/README.md` 参照。ChatGPTの独立レビュー待ち。
