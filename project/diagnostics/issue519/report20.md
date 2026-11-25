# PR #520 追加指示：20 seed 品質・時間効率比較

## 判断のための要約

**20 seed診断後、ユーザーがA+B採用を決定し、本番反映した。変更後の独立レビュー待ち。** 本番経路の検証は [production_report.md](production_report.md)。以下は診断時点の記録である。20 seedでは同一5000 forwardのSearch J対応勝/負はA 12/8、B 7/13、AB 12/8、時間近似ではA 12/8、B 8/12、AB 14/6だった（小さい方を勝ち、同数なし）。各中央値・平均は大きな外れ値に影響され、対応勝数も品質分布を十分に要約しない。いずれも非収束の有限探索20点であり、一般的な優劣や統計的有意性は主張しない。過去のseed 1010でのAの大きな悪化と他seedの改善も維持されている。

再現コマンド中の `compare20.py`・`observer20.py`・`regression20.py` は本番AB反映前のコードに依存するため、固定commit `b87d4c1ea3a10a1d50be6f8754902521a6979506` のcheckoutで実行する。現HEADで旧baselineを自動再構成しない。前回3 seed固定点比較・個別値・rawは[従前報告](report.md)と[results.json](results.json)に保持。今回の全run結果、全指標の中央値・平均・最良/最悪・四分位、各対応差分・勝負同、全checkpoint SHA、入力SHA、実費用およびobserver軌跡は[results20.json](results20.json)。Search Jは70点の正の違反の二乗和、Terminal Jは476点の同じ二乗違反和であり、Terminal最大符号付き違反[dB]とは別。両gridの点数と構成が違うのでJの大きさを直接比較しない。

## 条件、事前校正、再現

baselineは #518マージ後main `be0bdb2bf3662512b30408091efc3906389c1f6e`。追加作業前にfetchした最新mainも同SHA、運用正本は変更なし。測定時の作業HEAD `8e3a60e86d82373e775b0be0b50782478fcf021d` は診断資産のみの差分で本番srcはbaselineと同じ。RF-T010 trial effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、base RF-T008、#513/514既存seed 1001–1020の全初期vector SHAを照合、bounds・S2P・6設定28独立区間、Search70/Terminal476、TRF exact・ftol=1e-6・x_scale=1・restart_sigma=.1、checkpoint1000、Terminal MNA [0,111]。格子、bounds、bands/S2P、plan、開始点、環境と個別raw SHAはJSON。Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、WSL2、BLAS/OMP/MKL各1、CPU固定なし。`compare20.py` SHA-256 `ff7268aad171f8a0ee7568348d7bfed0d16a5658f6ce5ca43a7517f2973fd4b6`、実験式 `probe.py` は前回と同じ。

まず各モード1本の完全Runner warmup（集計除外）、次に1001/1010/1020各4モードの5000 forward plain校正をseed別に順序変更して実行。校正の候補ごとの `baseline wall / candidate wall` 3値の中央値×5000を最寄り100に丸め、**品質runの前に** A=5600、B=5100、AB=6300 と凍結。候補の結果に基づく選別ではない。Bの校正比は1.025〜1.073とばらつきがあり、実測の同一時間近似精度に限界がある。固定評価数は全条件5000、追加候補時間近似は各固定予算。baseは同一forward runを兼用し、異なるseedでは品質反復を行わない。固定評価の4条件は20 seed全体で各順序位置5回の巡回配置、時間近似3条件も巡回配置。固定試行後に時間近似を実施するため、順序・時間変動の交絡は残る。時間はPlan構築・Terminal・保存を含むplain wall/process CPU、厳密な同一停止時刻ではない。

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
uv run --frozen python project/diagnostics/issue519/regression20.py
uv run --frozen python project/diagnostics/issue519/compare20.py /tmp/issue519-compare20-NEW
uv run --frozen python project/diagnostics/issue519/observer20.py /tmp/issue519-observer20-NEW
uv run --frozen python project/diagnostics/issue519/analyze20.py /tmp/issue519-compare20-NEW /tmp/issue519-observer20-NEW /tmp/issue519-results20-NEW.json
```

`compare20.py` は新規 `/tmp` に書き、校正結果と凍結予算を逐次保存してから品質runを開始する。異常runは削除・除外せず保存する。再現時には同じ予算が再選択されるとは限らず、校正結果を別記録すること。`analyze20.py` は156校正/品質runすべてのreceiptの全ファイルhash、plan/開始vector/費用、Terminal受動性・電力保存・物理・MNAを検査し、今回PASS。MNA raw出力を独立に再計算したわけではない。

## 同一評価数 5000

数値は20 seed分布の中央値 [第1四分位, 第3四分位]。最小・最大・平均と全seed値はJSON。

| 条件 | Search J | Terminal J | Terminal max margin dB | 対応Search J 勝/負/同 | wall秒 |
|---|---:|---:|---:|---:|---:|
|base|3.196 [0.587,122.903]|26.687 [4.872,855.894]|0.676 [0.320,4.254]|—|24.111 [23.519,25.401]|
|A|2.171 [0.530,36.206]|18.134 [4.401,233.197]|0.505 [0.322,1.890]|12/8/0|21.716 [21.100,22.652]|
|B|6.410 [0.618,125.503]|49.943 [5.136,895.816]|0.926 [0.329,4.212]|7/13/0|22.415 [21.832,23.244]|
|AB|14.707 [0.564,198.182]|110.762 [4.686,1364.516]|1.325 [0.319,5.054]|12/8/0|19.778 [19.144,20.535]|

対応Search J差（候補−base）の中央値はA -0.272、B +0.033、AB -0.039。対応Terminal max margin勝/負はA 12/8、B 7/13、AB 10/10。対応wall差中央値[範囲]秒はA -2.631 [-4.233,-0.909]、B -1.948 [-3.924,-0.223]、AB -4.663 [-6.230,-0.053]。全20ペアで各候補のwallは短かったが、評価列は同じではない。baseのworst IL/min H2/min H3中央値は1.426/29.929/29.966 dB、Aは1.255/29.902/29.988、Bは1.676/29.592/29.948、ABは2.075/29.380/29.407。各runのnfev=5000、njev・restart分布と対応差はJSON。

## 同一時間近似

基準は上表と同じbase run。候補の凍結forward予算は校正済みで、壁時間の厳密一致ではない。

| 条件 / forward上限 | Search J中央値 [Q1,Q3] | Terminal J中央値 | Terminal max margin中央値 dB | 対応Search J 勝/負/同 | 対応wall差中央値 [範囲] 秒 |
|---|---:|---:|---:|---:|---:|
|A / 5600|0.774 [0.522,21.123]|6.443|0.349|12/8/0|-0.379 [-2.750,2.549]|
|B / 5100|6.410 [0.614,125.503]|49.944|0.926|8/12/0|-1.260 [-2.953,2.559]|
|AB / 6300|7.233 [0.516,125.139]|56.759|0.887|14/6/0|+0.300 [-2.469,4.587]|

対応Terminal max margin勝/負はA 12/8、B 7/13、AB 14/6。wall差のばらつきとBの早め終了、ABの遅め終了を踏まえ、時間近似に厳密な公平性を主張しない。後から予算を変更していない。結果はseed順、OS負荷、未収束と評価予算に依存し、他の条件・seedへの一般化はできない。

全140品質runおよび16校正/warmup runは正常終了・評価予算到達、異常STOPなし。全140品質runで有限格子適合数0、6設定のcomponent policy・外部受動性/電力保存・Terminal独立MNA 2点は記録上PASS。物理実装性、連続周波数、SRF、Q(f)、EM、許容差や実測の保証ではない。

## 追加STOP・観測

`regression20.py` 5件PASS：実RF nodal stampの2 port主小行列を使った**投影fixture**で内部ノードなし、A/ABの残存2 packed solveとB/baseの3 solveそれぞれの例外・NaN注入、node感度のNaN/inf/1e308注入、candidate deep hookの正常/例外復元、forwardが有限な合成2-portで分母虚部1e-16〜1e-300と伝送ゼロの有限/非有限mask旧新比較。後者は1e-160以下の感度で非有限になり、検査した左右固定各4成分の旧新maskは一致。これは極端値の全STOP・全物理回路を保証しない。以前の候補別全列FD・設定外C厳密ゼロ・SPD・forward Schur・zero transmission検査も保持。実回路の内部ノードなしモデル全域や全故障優先順位は未網羅。

別のintrusive observerで1001/1010/1020×4条件×5000 forwardを実行し、毎評価の真のSearch Jを計算して100 forwardごとにbest-so-farと経過時間を記録、最終bestがsolver選択Jと一致。observer elapsedには追加計算を含むためplain wallと混ぜない。周期checkpointの現在値はbest-so-farとして扱っていない。

## 消費と検証

今回の校正16本、品質140本、observer 12本で Search 880000 forward、Terminal 168 forward（合計880168 RF forward）、61679968 RF samples、独立MNA 336点。別途スモークでSearch 5 + Terminal 1 forward、826 samples、MNA 2点。有限差分・回帰・通常CIのforward/sample数は未集計。新正式EXP・探索科学条件・本番保存契約の変更なし。

ローカル通常CI FULL選択・保存監査、#499（6件）、#503（7件）、今回regression20（5件）PASS。前回の無選別unittest discoverの旧履歴19 errorsは[前報](report.md)参照、今回これを全テストPASSとはしていない。PRのCIと独立レビューは別の判断。

rawおよびcheckpointは `/tmp/issue519-compare20-2026/`、`/tmp/issue519-observer20-2026/`、スモーク `/tmp/issue519-compare-smoke-g3_96f9y/` に残す。ローカルCI/監査ログ `/tmp/issue519-extra-ci.log`、`/tmp/issue519-extra-audit.json` も残存。前回のrawは変更・削除していない。計測器の作成した `__pycache__` は無視ファイルであり、worktreeや別checkoutは作成していない。
