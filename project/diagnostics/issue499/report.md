# Issue #499: 独立TRF試作・有限格子pilot

## 範囲と入力

正式EXPではない。Runner/CLI、既定Hybrid、RF条件や目的を変更せず、独立APIと単一局所runのみ。RF-T010 **trial** effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、4L2C/25変数、seed 1013、6設定・28個別区間、Search 70点、Terminal 476点、外部S2P。Plan `0e2d62841f286281eb9b2c662382a50238f865193b16eafabf6aa3227ba18d90`、開始vector `6e06d271e0ea54eecb547cfff045a6edda4850bfaa1f9c23bf9f3037ab867131`。grid・bands・S2P・開始vector・全パラメータ・環境・実行時sourceのSHAは `pilot.json` に記録。実行時の基点は `42a3fbc4a9a1fb079df88e9774bae8ab5ea35971`、実装はdirtyであり、同JSONの4 source SHAとcommit `7fb9de03` のファイルを照合できる。その後solver入力の幅overflow拒否のみ追加したが、pilotは再実行していない。Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、BLAS等1 thread、WSL2。pilotは単独で1回だけ実施した。

## 微分・テスト

- `tests/test_issue499_sensitivity.py`：RF-T010 70点、2つの有効vector（seedと微小摂動）全25列。既存scalar forwardを独立基準に、正規化座標中心差分 `h=1e-6, 3e-6` と解析dIL/dz、dm/dz、active residual Jacobianを比較。事前閾値 `rtol=1e-4, atol=1e-5`。kink回避を確認。各列を最も近いbox端から幅の1e-5内側に置き、box内の2次片側差分 `h=1e-6` も同閾値で比較。2つの内点で複素S・IL・APL・両RLも既存forwardと `rtol=atol=1e-12` で比較。設定外の可変C列の厳密ゼロ、SPD違反、S21=0の失敗も確認。
- nodal L/k/Cの物理単位差分、人工残差の固定列・境界初回・fun/jac共有・max_nfev停止・例外も確認。折点m=0の導関数は存在せず、実装はゼロを選択。S21ゼロ・特異/非有限感度をfloorやゼロ微分に置換しない。
- 実行済み: `test_issue499*.py` 6件、`test_issue309_rf_core.py` 8件、`test_hybrid_optimizer.py` 14件、`test_issue458_profile.py` 5件、`test_issue479_rf_batch.py` 5件、`test_issue476_rf_cache.py` 5件、`test_issue495_physical_reuse.py` 3件、`test_phase2_branch_mna.py` 6件、全PASS。これはCIや独立レビューではない。

## 単一TRF pilot

`max_nfev=100`、TRF/linear/exact、再開なし。開始Search目的 `28654.23931390905`、最終SciPy目的 `449.30525530561306`、既存 `squared_terms/aggregate` の別計算 `449.305255305613`（丸め差）。`nfev=100`, `njev=93`, 実感度評価100、requested/computed 7000 samples、wall 0.659秒・CPU 0.659秒。終了は **max_nfev超過による非収束**、success=false。初回評価vector、best/final vectorと全Terminal複素S・IL・APL・両RLは `pilot.json`。TRFの停止条件とRF forward上限は別物。

Terminal signed max margin `+7.3865385965989745 dB`（未適合）。全L行列最小固有値 `6.098518221677506e-09 H`、6設定component policy pass、Terminal grid上の受動性・電力保存チェック実行。独立MNA 2点 `[0,111]` でS・IL・APL・両RLの最大差は各点それぞれ約 `1.06e-13`、`7.86e-13`（許容 `1e-9`）。MNAは2点のみ。finite-grid結果であり、正式適合・連続帯域・物理実現性の証明ではない。Q(f)、SRF、EM、許容差、実測は未検証。

## 同一点のコスト

`cost.py` / `cost.json`: 同seed固定x、warmup各1回除外、順序交互10回ずつ、単一thread、評価器構築外。解析RF感度1回に対し、既存RF batch/partial経路のbase+25片側プローブ1組を直接構成（**Hybrid全体の実行時間ではない**）。requested/computedは解析 `70/70`、partial `1820/1120`、forward候補数はそれぞれ `1/26`（base含む）。wall中央値 [最小,最大] は解析 `4.319 [4.153,4.809] ms`、partial `3.019 [2.871,3.478] ms`、CPU中央値 `4.321/3.022 ms`。別実行のtracemalloc peakは `1,991,248/1,648,974 bytes`、RSS全体やネイティブ全割当の保証ではない。ロード平均(1分)は測定中約0.543、CPU固定なし・WSL外部の干渉不明。従ってこの条件で解析kernelは速くなく、一般的なsolver優劣や本格探索速度を推定しない。`pilot.json` 内の別測定はtracemallocを計時中に有効にした参考値で、plain結果と混同しない。

## 残る注意

独立レビュー・CI未確認。極小S21や特異点近傍の条件数に対する広範な安定性、境界とSPD制約が同時に厳しい領域の網羅、複数seed、連続周波数、製造実装は未検証。Schurのforward解などは微分で再利用するが、L行列の `solve(H, B.T)` は感度用に1回再計算する（25回forwardではない）；更なる共通solve再利用は未実施。`least_squares_local` は汎用予算管理Runnerではなく、callbackの例外を成功に変換せず送出する。pilotは例外ならSTOPとして記録する設計。解析経路は新規試作であり既存Runnerのデフォルト経路に接続しない。
