# #519 A+B 本番反映と最終検証

## 採用決定・境界

2026-11-26 JSTにユーザーはIssue #519およびPR #520の追加指示で、20 seed比較と限界を踏まえてA+B本番採用を決定した。20 seed比較ではA単独の品質分布が良好な指標もあった一方、A+Bは同一5000 forwardでRunner wall中央値24.111→19.778秒、時間近似でSearch JとTerminal最大違反が各14/20 seed改善。B固有の系統的品質劣化の原因は確認されていない。探索の丸め分岐は観測されたが品質差の因果や統計的同等性を証明していない。全条件・全20 seedは予算停止で未収束、有限格子適合0/20。[前報](report20.md)・元rawは保持する。

実装・テスト・検証スクリプトのcommit **`36feec16f3025ed84f15cfe1f03cd18888e01441`**、測定時の親HEAD `b87d4c1ea3a10a1d50be6f8754902521a6979506`、未commit実装の `src/lpf/rf_core/model.py` SHA-256 `7c042e891a13f77ecc77f529e7fd630cc9932e362f60d9e2185a6cd1ea0db00a`（実装commitと同じ内容）。測定前にfetchした最新mainは `be0bdb2bf3662512b30408091efc3906389c1f6e`、`project/instructions.md` はmainと同じ。RF-T010 trial effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、base RF-T008。固定S2P、6設定28区間、Search70/Terminal476、既存bounds/starts・TRF設定・予算・保存契約を変えていない。正式EXPは実施しない。

## 本番差分

`src/lpf/rf_core/model.py` のSchur感度に複素**非共役**対称縮約 `T.T @ dY @ T` を適用し、内部ノードなしは既存 `dR=dY[:,:,:2,:2]` のまま。感度Schur solveのみ除去、forwardと後続の2 packed solveを維持。`_cascade_jacobian` は左右の片側固定式、前段 `da=None`・後段 `db=None`、forward cascade・分母検査・伝送ゼロの扱いは不変。旧汎用積微分とゼロ配列を除去。該当callerは前後2箇所のみ、deep wrapperは同名を維持。旧切替・新設定・追加cacheはない。演算式と順序は診断ABの `probe.py` と同一。

## 固定vector・Runner同値性

`verify_production.py` はGit固定object `b87d4c1ea3a10a1d50be6f8754902521a6979506` の旧model sourceから当時の診断ABを一時的に構成し、probeのSHAを照合してから本番に戻して比較する。9固定vector（1001/1010/1020各初期、既存3000/5000 checkpoint）でS、IL、APL、両RL、全IL Jacobian、残差と残差Jacobianは**全要素bit一致**。これは9点の同一環境での観測であり、全回路の連続域を保証しない。vectorおよび各出力SHAは [production_verification.json](production_verification.json)。

同じ3 seedについて、本番パスをobserverなしのplain Runnerで各5000 forward実施し、保存済み20 seed診断AB rawと比較。step全体はlocal wall/CPUのみを除いて一致、選択vector・nfev/njev・local/restart・終了理由は一致。Terminal全体（全476点のS/指標・物理・外部受動性/電力保存・独立MNA [0,111]）と各checkpointのsequence・forward数・observationは一致。source provenanceが異なるためcheckpointファイル全byteやresult raw SHAの一致を要求していない。

| seed | Search J | nfev / njev | restart | 本番wall秒 | Terminal MNA |
|---|---:|---:|---:|---:|---|
|1001|0.19810037984156206|5000 / 4095|3|17.870|pass|
|1010|17.29317989136568|5000 / 4261|28|18.024|pass|
|1020|124.71956801107635|5000 / 4358|18|17.959|pass|

別のintrusive観測3 runで各5000入力vector列のSHAが以前の診断AB traceと完全一致（[production_trace.json](production_trace.json)）。観測実行の時間をplain時間に混ぜない。これらの値は予算停止の試験条件runであり、科学的収束・RF適合ではない。plain 3本は交互旧新計測やwarmupを行っていないため速度採用の根拠は前報のpaired計測であり、このwall値は補助記録。

再現（`verify_production.py` は比較対象の過去rawを要し、存在しなければPASSできない）:

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
uv run --frozen python project/diagnostics/issue519/verify_production.py /tmp/issue519-production-NEW /tmp/issue519-compare20-2026
uv run --frozen python project/diagnostics/issue519/verify_production_trace.py /tmp/issue519-production-trace-NEW
```

## 回帰・消費・限界

- `test_issue499_sensitivity.py` 6件PASS：全列FD・境界片側差分・設定外Cゼロ、SPD、forward Schur異常とsample index、zero transmission、**残存2 packed solve**各々の例外・NaNを本番経路で確認。
- `test_issue519_sensitivity.py` 6件PASS：実RF nodal stampの2 port主小行列を使う内部ノードなし**投影fixture**のforward・全列FD、非相反／反射・伝送ゼロを含む左右固定cascadeの方向差分、cascade forward先行STOP、forward有限な極小分母での旧式と同じ有限/非有限mask、NaN/inf/1e308感度、deep hookの正常・例外復元。
- `test_issue503_trf_runner.py` 7件PASS、通常CI FULL選択と保存auditもローカルPASS。PRのGitHub CI・独立レビューは別判断。全故障組合せ・全極端条件でのSTOP同等性、連続帯域、EM・SRF・Q(f)・許容差・実測は未検証。
- 今回はplain 3 + intrusive trace 3 jobs、Search 30000 forward・Terminal 6 forward、合計30006 RF forward / 2102856 samples、MNA 12点。固定vectorは旧新18 forward / 1260 samples。通常テストと監査の計算量は未集計。
- rawとcheckpointは `/tmp/issue519-production-2026/`、`/tmp/issue519-production-trace-2026/` に残す。前回の `/tmp/issue519-compare20-2026/` など既存rawも削除しない。ローカルCIログ `/tmp/issue519-production-ci.log`、監査ログ `/tmp/issue519-production-audit.json`。worktree／追加checkoutは作成していない。
