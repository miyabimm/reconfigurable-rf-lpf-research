# #519 Schur / 固定S2P感度のA/B診断 — 採否は独立レビュー待ち

## 20 seed追加比較後の結論

PR #520 追加指示による20 seed・同一評価数／同一時間近似の結果は [追加報告](report20.md) と [results20.json](results20.json)。**前回の3 seedだけによる不採用判断は暫定に修正する。** A・B・A+Bの採否はこの追加結果と数値/STOP検証を合わせた独立レビュー後に判断し、本番srcは変更しない。以下の3 seed記録・当時の判断は履歴として保持する。

## 以下は当初の3 seed時点の判断と範囲

**当時はA、B、A+Bとも本番に反映しなかった。** 固定入力と実Runnerのplain時間は短縮したが、探索軌跡・品質が変わった。特にAのみのseed 1010は目的0.599720→99.604943、Terminal最大違反0.303338→3.394940 dBで、Issueの顕著な悪化に該当する。Bのみも3 seedとも目的が悪化し、1001では0.480294→0.623251、restart 4→31。少数seedの非収束探索でありBの一般的悪化や数値式の誤りを証明するものではないが、同等性が不明なため速度だけで採用しなかった。A+Bは1010で17.293180に悪化。正式EXP・新探索・科学条件変更ではない。

#518マージ後baseline `be0bdb2bf3662512b30408091efc3906389c1f6e`、本番srcの差分なし。`probe.py` の診断時だけのモンキーパッチでbase/A/B/ABを独立に比較。関数名は本番のまま、forwardは不変、Aは内部ノードなしなら従来式、Bは片側固定を使う。一般productはbaseline参照にのみ使用。4モードを本番に残さない。探索の収束や物理実装可能性を主張しない。

## 条件・再現

RF-T010 trial effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、base RF-T008、4L2C/25変数、6設定28区間、Search 70、Terminal 476、seed 1001/1010/1020、TRF exact、ftol=1e-6、x_scale=1、restart_sigma=.1、max_evaluations=5000、checkpoint 1000、独立MNA [0,111]。Plan、開始点、bounds、bands/S2PのSHAは `results.json` に記録。Search grid SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、Terminal `28ee5b630e4842b183a7c36fd610cc32e2509c0044c6a5848ce2fbd147a22e29`。Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、WSL2、BLAS/OMP/MKL各1、CPU固定なし。測定中のtracked fileはbaselineと同じで診断スクリプトは未追跡。`probe.py` SHA-256 `d92d835c5c11a72636b84cb35a0092f52ef0a81f5200194809bd25dbdaaf398f`、`runner.py` `56e9c272c59555766e49efef95598a45dd2b6448558d595d26054132511584e1`、`trace.py` `85f5856d297ddef426aaf3b2a5389bf4c47c6c94ff01fa0ecbdc619312726e51`、`vectors.json` `485bfd244c06ea706b7d688555f2fe2c924ea928981080e7f92db3717f9a23c9`。

全入力は #517 の開始点と、それぞれ既存runの3000/5000 checkpoint vector。`vectors.json`のSHA検証後、9固定点×各候補についてwarmup後20ペア交互plainを測定。実Runnerは各seed・各モードの全予算warmup後、各候補につきbaselineと3ペア交互。通常評価を計時しdeep/traceは使わない。実Runner別途12本にvector hash観測を挿入（時間測定には使用しない）。`results.json` は全測定、paired差、各seed/modeの選択vector・checkpoint・28区間Terminal IL範囲・物理/MNAとhashを含む。基準と候補の繰返し結果は時間を除き同一であることを `collect.py` が確認した。

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
uv run --frozen python project/diagnostics/issue519/probe.py kernel /tmp/issue519-kernel-NEW.json
uv run --frozen python project/diagnostics/issue519/numerics.py /tmp/issue519-numerics-NEW.json
uv run --frozen python project/diagnostics/issue519/runner.py /tmp/issue519-runner-NEW
uv run --frozen python project/diagnostics/issue519/trace.py /tmp/issue519-trace-NEW
uv run --frozen python project/diagnostics/issue519/collect.py /tmp/issue519-kernel-NEW.json /tmp/issue519-numerics-NEW.json /tmp/issue519-runner-NEW /tmp/issue519-trace-NEW /tmp/issue519-results-NEW.json
```

出力は新規パスのみ使用。rawにはcheckpoint等があるため自動削除しない。

## 性能と探索品質

固定点の各20ペア差（候補−baseline、ms、各固定点の中央値の範囲）は A -0.582〜-0.412、B -0.384〜-0.258、AB -0.889〜-0.771。実Runner全体（Terminal/保存込）の3ペア差中央値 [範囲]、秒:

| seed | A | B | A+B |
|---|---|---|---|
|1001|-2.502 [-2.578,-2.360]|-1.698 [-1.897,-1.605]|-4.113 [-4.131,-4.099]|
|1010|-2.593 [-2.865,-2.553]|-1.819 [-2.869,-1.794]|-4.193 [-4.371,-3.815]|
|1020|-2.366 [-2.517,-2.217]|-2.106 [-2.310,-1.785]|-6.279 [-7.558,-4.521]|

1020 ABのbaselineに25–26秒台の外乱があり、その中央値を純粋な改善率とみなさない。全runの壁/CPUはJSON。評価列・探索経路は異なり、Runner時間差は厳密な同一演算の差ではない。

| seed | base J / max margin dB | A | B | AB |
|---|---|---|---|---|
|1001|0.480294 / 0.312675|0.532914 / 0.318853|0.623251 / 0.327424|0.198100 / 0.190810|
|1010|0.599720 / 0.303338|99.604943 / 3.394940|0.609309 / 0.323321|17.293180 / 1.415108|
|1020|124.966940 / 4.272222|35.401123 / 2.423141|126.401944 / 4.370402|124.719568 / 4.252552|

全runは5000評価予算停止・未収束、Search samples 350000、Terminal 476、MNA 2。nfevは全5000、njev/local/restartと選択vector・checkpointはJSON。各modeの5000入力vector列SHAはbaselineと異なり、最初の相違は2回目の評価（0始まりindex 1）。固定点の微小なJac丸め差が最初のstepに影響し以後非線形探索が分岐することと整合するが、個々の巨大な目的差の因果を証明したわけではない。全Terminalは有限格子RF性能不適合、component policy・外部受動性/電力保存・2点独立MNAは各runの記録上PASS。非収束と有限格子の結果である。

## 数値・STOP

回路のL部分は実incidence B と対称Hから `B solve(H,B.T)`、Cは対称stamp和で複素対称、dHとC stampも対称。数値solveや積の順で厳密対称にはならない。9固定点で最大 `|Y-Y.T|=1.11e-16`、`|dY-dY.T|=5.55e-17`、内部Eの最大条件数は45.5〜650.8。旧Schur感度と転置縮約の最大絶対差 `2.52e-15`。強制対称化・共役転置・許容差緩和なし。これより悪条件の合法回路全域は未測定。

9点の各サンプル・全方向・全4成分の最大絶対差は dcore ≤7.90e-15、first/full/wave dS ≤8.19e-15。正規化IL Jac最大差 ≤1.10e-11、正規化残差Jac ≤1.82e-11（詳細はJSON）。全forward S/IL/APL/両RLはrtol=atol=1e-12で比較。診断の非相反ランダム2-portで、反射/伝送ゼロと分母約1e-8を含む左右固定全S微分を旧一般式と比較。分母近傍の絶対差は最大24.1と大きいが感度が約1e17のため最大値に対する相対差は3.82e-16；任意の極端な分母・overflowの同等性は未証明。伝送係数による除算や感度専用分母制限なし。

既存 `test_issue499_sensitivity.py` 6件、`test_issue503_trf_runner.py` 7件PASS。A/B/AB各診断パッチについて既存FD 2刻み・境界片側・全列、設定外Cゼロ、SPD/ゼロ伝送、forward Schurエラーとsample indexを含む5件を個別に実行しPASS。baseline packed solve注入テストはそのまま保持。Aの残存2 solve注入、内部ノードなし、異常overflow・非有限伝播、全故障優先順位の候補別厳密同等性は未実施であり、候補のSTOP契約PASSとは呼ばない。deep hook復元の既存baseline回帰PASS、候補でのdeep比較は未実施。

通常CI相当の `CI_EVENT=workflow_dispatch CI_FULL=true ... scripts/select_ci_tests.py` と保存auditはPASS。一方、別途実行した無選別 `unittest discover -s tests -v` は509件中19 errors（廃止旧 `lpf.port_parasitics`、履歴専用RF-F001等）；通常CIの選別対象外の旧履歴testを含み、全test PASSとはしない。ログ `/tmp/issue519-unittest.log`、CIログ `/tmp/issue519-ci.log`。

## 消費・限界

Runnerはwarmup 12 + plain 54 + intrusive trace 12 = 78 jobs、Search 390000 forward / 27300000 samples、Terminal 78 forward / 37128 samples、独立MNA 156点。固定vector比較は1116 forward / 78120 samples。数値スクリプトは9点のnode/感度計算を3回実行、合成cascade 2側。上記以外に通常テスト・候補別FDテストの計算量は未集計。正式EXPなし。初回実行の診断scriptエラー2件（vector SHA関数・sourceインデント、Runner実行前）を修正後に計測した。

`/tmp/issue519-runner-2026/`、`/tmp/issue519-trace-2026/` にraw run/checkpoint、`/tmp/issue519-kernel-1.json`、`/tmp/issue519-numerics{,-2,-3}.json`、上記2ログが残る。既存#517の一時データには触れていない。実機、EM、SRF、Q(f)、連続周波数、全物理条件は未検証。結果は指定の3 seed/有限格子に限る。
