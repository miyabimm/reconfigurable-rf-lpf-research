# Issue #501: 解析RF Jacobianの行列演算診断

## 対象と再現

正式EXPではない。対象はRF-T010 **trial** effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、4L2C/25変数、6設定・28個別区間、Search 70点・Terminal 476点、seed 1013、固定S2P。Plan `0e2d62841f286281eb9b2c662382a50238f865193b16eafabf6aa3227ba18d90`。格子、vector、bands/S2P SHA、ソースSHA、thread、環境は各JSONに記録。基準main `58573e2573867dc095e38d8995c29626d9ec32cd`、B採用後 `c0f339ca82489e58324e435698197f6400b5d997`、C採用後の測定HEAD `9b84d434254726396164b919b8cba64b178bdd4a`。Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、WSL2、BLAS等各1 thread。NumPy build情報は `numpy-config.txt`。

`bench.py BASE OUTPUT` はbaselineのクラスメソッドをgitから読み、作業treeの同メソッドと同一プロセス・評価器で交互に切替。各vector/版20回、warmup除外、評価器生成除外。Python peakは別途tracemallocで取得（RSS/native全体ではない）。x0と幅の±0.001の線形摂動の2 vector。各段階のJSONに全wall/CPU/loadとメモリを収録。候補の再現にはBはcommit `c0f339ca`、Cは `9b84d434` の各ソースを使う。A1は基準の `dK = -B @ np.linalg.solve(H, dH @ X)` を `dK = -X.T @ dH @ X` に差し替えたもの（共役なし、ソースSHAはJSON）。B/Cは採用済み前段に対する単独追加効果。`pilot_ab.py OUTPUT` は旧新交互の単一局所runであり正式Runnerではない。各コマンドは `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --frozen python` を前置する。

## Step 0: 区間診断

`trace.py` / `trace.json` はbaselineを20回、rootの行区間に経過時間を**一度だけ**割当（子関数はその呼出行に含む）。深いtraceの負荷を含みplain比較には使わない。主な1回平均はL-k matrices 0.118 ms、forward node 0.091、forward Schur solve 0.041、Y→S solve 0.036、forward cascade 2回計0.066、forward power-wave 0.168、node感度 0.553、Schur感度solve 0.940＋更新0.448、Y→S感度solve 0.628、cascade感度2回計0.527、wave感度solve関連2行計0.627 ms。残りはdecode、配列準備・検査・output等。行内の演算とsolveは分離できず、inclusive区間を重複加算していない。特に複数方向solveの削減を優先し、cascade全面改稿は行わない。

## 段階別採否とplain測定

数値テストPASSの後、各々交互測定。以下はwall中央値 [最小,最大] ms（2 vectorの順）。CPU中央値・全行・loadはJSON。値は外乱や周波数変動でばらつき、別実行間の絶対値を直接比較しない。

- **A1 不採用**：`a1.json` 基準 4.287 [4.237,4.890] / 4.354 [4.227,6.364]、候補 4.284 [4.197,5.286] / 4.345 [4.197,5.394]。`a1-repeat.json` では 4.457 / 4.652 対 4.434 / 4.891、外れ値最大10.141 ms。差は小さく不安定で採用条件の実測改善を確認できず戻した。
- **A2 見送り**：forward Xの再利用は感度経路のAPI追加等が必要。A1の追加効果自体が小さく不安定で、forward matrices全体も上記traceで0.118 ms程度、重複する単一小solveだけの削減はさらに小さい。複雑さに対し確実な効果が見込めない。実装・性能PASSとは主張しない。
- **B 採用**：`b.json` 基準 5.010 / 5.028、候補 4.904 / 4.864；`b-repeat.json` 基準 5.049 / 5.001、候補 4.726 / 4.904。対応する交互ペアの差の中央値はそれぞれ約118/102、177/111 µs。ばらつきは大きいが両vector・再測定で同方向。`[sample,direction,internal,2]` を `[sample,internal,direction*2]` にtranspose/reshapeし、周波数単位でsolve後に戻す。broadcast係数の繰返しsolveを避ける代わりにpacked RHSのコピーが発生。tracemalloc peakは約1.99→2.33 MBに増加。
- **C 採用**：Bに対する `c-repeat.json` は基準 5.016 [4.789,6.818] / 4.992 [4.774,5.825]、候補 4.325 [4.231,5.230] / 4.338 [4.237,4.652]。`c.json` も同方向（外れ値最大12 ms超）。Y→Sと転置したwave方程式に同様のpackingを適用。B後からのpeak増加は実質なし。
- **D 見送り**：cascade感度2回はtrace計0.527 msで複数solveより支配的ではなく、B/Cで改善を確認したため対象外。

最終全体 `final.json` は基準 4.982 [4.287,7.457] / 5.040 [4.313,6.163]、候補 4.166 [3.671,4.624] / 4.188 [3.676,4.829] ms。CPU中央値は基準4.985/5.043、候補4.169/4.191 ms。Python peak 約1,991,216→2,327,424 bytes。測定中loadavg(1分)約0.16、CPU固定なし。別測定 `hybrid-kernel.json` はx0解析3.872 [3.361,4.767]、既存base+25 partial FD 3.147 [3.018,3.581] ms（10回交互、70対1120 computed samples）。今回の解析kernelは3.019 ms目標に到達していない。これはHybrid solver全体の比較ではない。

## 数値・STOPとsolver pilot

`test_issue499_sensitivity.py` は2つのRF-T010 vector全Search70点×25列を、独立scalar中心差分2刻み、境界近傍片側差分、margin/Jac、S/IL/APL/両RL、設定外C厳密ゼロで確認。既存SPD違反・S21ゼロに加え、3つのpacked感度solveの失敗・非有限感度とforward Schur失敗・非有限sample indexを注入してSTOPを確認。forwardを先に完了する順序・同じ例外コードは維持。浮動小数点演算順は変化し得るが、現テスト範囲でRF許容 `rtol=atol=1e-12`、dIL/dz `rtol=1e-4, atol=1e-5` を満たす。病的な条件数の全域・複合故障の例外優先順位は網羅していない。

`pilot-ab.json` と追加再測定 `pilot-ab-v2.json` はwarmup後、旧→新→新→旧の同条件run。各100 nfev、93 njev、実感度評価100、7000 samples、max_nfevで**非収束**。後者のwallは旧0.6147/0.6278秒、新0.5768/0.5346秒（CPUや全軌跡はJSON）。旧新ともSearch目的449.305255305613、最大違反+7.38654 dB、Terminal目的2905.092565944296、最大違反+7.38654 dB。旧新の観測100点のvectorと目的はこの環境でbit一致（差最大0）。Terminal全476点の受動性・電力保存チェックPASS、SPD最小固有値6.0985e-9 H、6設定component policy PASS。独立MNAはindex 0/111の2点のみでS/IL/APL/両RL最大差7.86e-13以下。physical検査のpromotion blockersはそのままであり、2点MNAを全点独立検証とはしない。pilotの同一点結果・速度は複数seedや探索全体へ一般化しない。

ローカルPASS: `test_issue499*.py` 9件、`test_issue309_rf_core.py` 8件、`test_hybrid_optimizer.py` 14件、`test_issue458_profile.py` 5件、`test_issue479_rf_batch.py` 5件、`test_issue476_rf_cache.py` 5件、`test_issue495_physical_reuse.py` 3件、`test_phase2_branch_mna.py` 6件。CI・独立レビューは別途確認。連続周波数、広範な悪条件、SRF、Q(f)、EM、許容差、製造・実測は未検証。finite-grid pilotはRF適合や物理実現性を証明しない。
