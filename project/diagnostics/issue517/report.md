# #517 TRF 計測診断（試験条件、採用提案ではない）

## 範囲・再現

正式EXP・新規本番探索ではない。RF-T010 trial effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、base RF-T008、4L2C・25変数、6設定28個別区間、Search 70／Terminal 476、既存bounds・開始点・固定S2P。TRF exact、ftol=1e-6、x_scale=1、restart_sigma=0.1、予算5000、checkpoint 1000、独立MNA Terminal [0,111]。seedは**計測前に**既存20個の前・中・後から1001/1010/1020を固定。開始SHAは#513と照合。Plan・grid・bounds・S2P・bands SHA、環境と各結果は [`results.json`](results.json)。測定HEAD `a0143b391450bb58a5e25c5f1395a0d148c26b99`、最終RF/Runner計測変更のdirty patch SHA `e34a91f4415c3eff253556e2aa54f0b57918166db5f930ebd3d65d4f81e7fda9`。先行計測のSHAは `656088d2ac9b8b19c9dd7f70504b24104b70666a1fe6280784a006641dd37529` で、最終計測と混同しない。Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、WSL2、BLAS/OMP/MKL各1 thread、CPU固定なし。

`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --frozen python` を前置し、`measure.py /tmp/<fresh>`、`detail.py /tmp/<fresh>`、`verify_trace.py /tmp/<fresh>`、`optimizer_trace.py /tmp/<fresh>` を実行。`measure.py` は同一Planの完全Runner warmup後、seed別にplain/deepを交互3ペア、固定vector replayはwarmup後10ペア。`measure.py /tmp/<fresh> 1001` は同条件の追加3ペア。初回測定は完全Runner warmupがなかったため別途 `initial` に保存し主表から除外。先行の `warmed` でも1001に約10%の速度変動があり、`repeat1001` を追加；原因は未特定。その後plain経路の不要な計時呼出しを除去し、`final` の全測定・traceを実施した。先行値も捨てずにJSONへ残す。replayには外れ値がある。時間差を高速化の実測値と解釈しない。

## 壁・CPUと計時負荷

単位秒、各3回の中央値 [最小, 最大]。Runner全体（Plan凍結、Terminal、保存・照合込み）。

| seed / 計測 | plain wall | deep wall | plain CPU | deep CPU |
|---|---:|---:|---:|---:|
| 1001 final | 21.271 [21.240,21.363] | 21.924 [21.900,21.954] | 21.168 [21.153,21.179] | 21.786 [21.710,21.843] |
| 1010 final | 21.620 [21.465,21.780] | 22.028 [21.998,22.564] | 21.450 [21.278,21.669] | 21.932 [21.914,22.459] |
| 1020 final | 21.518 [21.467,21.584] | 22.169 [22.022,22.191] | 21.342 [21.285,21.445] | 22.015 [21.922,22.066] |

最終runの中央値差は約0.4〜0.7秒（約2〜3%）だが外乱と混在するため純粋な計時負荷の厳密値ではない。固定初期vector replayのplain壁中央値 [範囲] msは1001 3.389 [3.201,7.502]、1010 3.361 [3.258,3.402]、1020 3.327 [3.233,3.386]；deepは各3.703 [3.488,6.561]、3.543 [3.471,4.528]、3.474 [3.396,3.565]。この短時間測定から負荷率を推定しない。CPU・全回はJSON。固定vectorと実探索の時間を混同しない。

## 実Runnerの内訳・評価数

`rf_evaluate` はforward＋感度を含み、node、cascade等のdeep領域は**その子**。同一runのsolver−RFは残差生成・callback・cache・SciPy・timer等の混合でありSciPyと断定しない。たとえば1010 final deep 1回目はsolver 21.491秒、RF 18.134秒、node感度2.547秒、cascade感度2.562秒（前後2回の合計）、残差/Jac生成・checkpoint等はJSONの別領域。親子を加算しない。decode、L/k、node、forward cascade、powerおよび下位領域のcount/timeもJSONにある。TRFのSchur/Y-to-Sは独立関数を呼ばないためdeepの関数計測だけでは分離されず、下記の別traceを使う。

| seed | nfev / njev | 実RF＋感度 | fun/jac cache hit | 局所run / restart | Search目的 | 終了 |
|---|---:|---:|---:|---:|---:|---|
| 1001 | 5000 / 4042 | 5000 | 4042 | 5 / 4 | 0.480294 | 予算到達・未収束 |
| 1010 | 5000 / 4112 | 5000 | 4112 | 6 / 5 | 0.599720 | 予算到達・未収束 |
| 1020 | 5000 / 4581 | 5000 | 4581 | 18 / 17 | 124.966940 | 予算到達・未収束 |

cache hitは別のintrusive診断でfun/jac呼出数から実RF呼出数を引いた観測値。各run 5000×70 Search samples＋Terminal 476、Terminal MNA 2点。全点でforwardと感度を計算。nfev−njevの比19.16%、17.76%、8.38%は感度要求差であり実時間短縮率ではない。#514の全20seed集計100000/84360の15.64%とも対象が違う。

Search進行の1000評価ごとの `margin>0` 点数（70点中、中央値 [最小, 最大]）:

| seed | 1–1000 | 1001–2000 | 2001–3000 | 3001–4000 | 4001–5000 |
|---|---|---|---|---|---|
| 1001 | 53 [45,70] | 35 [28,63] | 36 [32,70] | 36 [31,55] | 39 [33,70] |
| 1010 | 60 [28,70] | 35 [29,68] | 36 [31,70] | 66 [65,67] | 67 [43,70] |
| 1020 | 68 [40,70] | 37 [37,70] | 37 [32,68] | 37 [37,37] | 38 [36,70] |

集計全期間の非正margin割合は順に43.0%、23.2%、35.9%。全初期点は70違反点。局所restartで分布が大きく変わる。ヒストグラムはJSON、これもpoint数であって時間削減率ではない。

## 演算の所在と包含関係

`detail.py` は初期固定vector上で関数ごと別々に10回 `sys.settrace`。1関数内の行区間は排他的だが呼出先を包含し、別関数の結果は足せない。trace overheadを含み、Runner実時間との直接比較不可。例としてseed1010、1回平均ms：forward decode 0.146、L/k 0.122、node 0.100、Schur solve 0.050、Y→S solve 0.033、cascade前後 0.042/0.032、power 0.144。node感度全体 0.518（その中でX solve 0.019、dK行 0.042、dY配列生成 0.167、C stampingや有限性検査を別行で計測）。Schur感度 rhs 0.267、solve 0.208、更新 0.429；Y→S感度 rhs 0.167、solve 0.145；cascade感度前/後 0.278/0.264；波変換 rhs 0.203、solve 0.156、IL感度 0.024。配列生成・検査や残りの行もJSONに記録。複数行式、ループと子関数は行境界依存であり対象演算の厳密な純粋時間ではない。

`optimizer_trace.py` は別途1001の実Runner 1本を行traceし、`calc` のcache比較0.064秒/9042回、正規化座標→物理0.116秒/5000回、Worker呼出20.193秒/5000回、callback 0.083秒/5000回、cache格納・Jac正規化0.080秒/5000回（各行は子を含む）。SciPy TRFが実際に呼んだ `scipy.optimize._lsq.trf.svd` のみ4037回・合計0.847秒、失敗0。これはtrace付き単一seedでありSVD以外のSciPy内部・BLASを含まず、未分類残差をSVDと呼ばない。局所run境界・restartの行もJSONに含む。#501では複数RHS solveを採用し、A1（対称性dK）は差が小さく不安定、A2（X共有）は見送り、cascade全面改稿も見送り済み。

## 次候補の順位（仮説、効果は非加算）

1. **E、まず固定S2P片側微分の局所最適化を検討**：前/後cascade感度の合計は固定vector traceで0.542 ms/評価という包含時間の上限。両側一般微分を使う現状と、片側が定数である代数を比較し、同一STOP・全列FDと交互plain実測が条件。配列やゼロ生成も対象だが、その全時間が除去可能ではない。固定情報・閾値の事前生成も小さな独立候補。H/B/X共有と複素対称 `-X.T @ dH @ X`（**非共役**）はX/dK行の計約0.061 ms/評価が粗い包含上限であり、#501の不安定結果を尊重、重複して最初に再実装しない。演算順変更・非有限検出の例外順に注意。
2. **C、25→共通13＋当該設定2方向**：感度方向演算の理論上40%を除去可能だが、forward・配列復元・共通処理は残り時間40%削減ではない。Schur、Y→S、cascade、waveに及ぶため実装範囲と密70×25復元の検証が必要。設定外C列の厳密ゼロ、全点全列の非有限STOP・丸め・障害優先順位を守る方法を先に設計。
3. **A、fun/jac分離**：棄却点での感度省略対象は観測419〜958/5000評価（8.38〜19.16%）だがforward全点とcache中間状態が残る。現在は棄却点でもゼロ伝送・非有限Jac・感度solve失敗で直ちにSTOPする。これを後送り/省略すると探索継続やcheckpoint/選択vectorが変わるため現行契約のままの短縮とは言えない。契約の別途判断が先。
4. **B、非正margin点の感度省略**：対象点比23.2〜43.0%だが分布は局所restartで激変し、固定費や全点forwardは残る。非正点のゼロ伝送・非有限感度・感度solve失敗を見逃すため現行STOPを弱める。点抽出・再配置費も未測定。A/C/Dと同じ計算を削るので単純加算不可。
5. **D、IL/S21専用随伴**：理論的には全S行列・全方向の中間配列を避けられるが、forward/チェックは残り上限の定量は未測定。導出・数値条件・非有限検査・STOP同等性の負荷が大きい。CやBと重複するため、小さいEで不十分な場合に別設計。
6. **F、exact/SVD→lsmr**：観測SVD単体は上記0.847秒/trace runで支配的とは示されず、solver設定変更は今回禁止。SciPy内部の残りも未分類であり後続候補に留める。

## 同等性・制限・消費

3 seedそれぞれで、別のhash観測runにより全5000回の入力vector・外部S/IL/APL/両RL・Jacの連続列がplain/deepでbyte SHA一致。計時交互runでも結果（局所run wall/CPUのみ除外）と全checkpoint原byteがseed内一致し、予算・restart・目的・選択vector・Terminal結果を含む。hash観測自体は両方に追加負荷を持ち、時間計測には使わない。Terminalは全476点の外部受動性・電力保存チェック、独立MNA [0,111] PASS、全3 seed有限格子の性能閾値は不適合。SPD・非有限・zero transmission・感度solve等のSTOPは既存テストで確認、全故障組合せ・連続周波数、SRF、Q(f)、EM、許容差、実測は未検証。

この診断スクリプト群の消費（先行・最終の両方を含みテストを除く）はRunner 87 jobs：Search 435,000 RF＋感度forward、Terminal 87 forward／41,412 samples、MNA 174点。固定replay/trace追加294 forward／20,580 samples。合計435,381 forward、30,511,992 RF samples。全Runnerは保存照合完了・予算停止であり科学的収束ではない。実行失敗はなし。未分類SciPy内部、正確な候補速度、全域のSTOP同等性は未測定。注：`initial` はRunner warmupなしであり、捨てずに参考データとして残した。

結果rawはGit外 `/tmp/issue517-diagnostic-2026/`、`/tmp/issue517-warmed-2026/`、`/tmp/issue517-repeat1001-2026/`、`/tmp/issue517-detail-2026/`、`/tmp/issue517-tracecheck-2026/`、`/tmp/issue517-optimizer-2026/`、`/tmp/issue517-final-2026/`、`/tmp/issue517-final-detail-2026/`、`/tmp/issue517-final-trace-2026/`、`/tmp/issue517-final-optimizer-2026/` に残存、再起動後の保存は保証しない。これらにはrun/checkpointが含まれるため自動削除しない。Gitにはコンパクト集計のみ保存。全20 seed再比較、正式EXP、性能改善本体・solver変更は実施していない。
