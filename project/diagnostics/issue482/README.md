# Issue #482: SciPy workers / Hybrid RF A/B（開発診断）

正式EXPではない。比較元 `main` = `5c00f6ddb1e63fd104f55c091c2c31bd065fcdca`。測定時は同HEAD上の未commit差分（source identity `2a5ae4aa66e83dbd23d02bd09df1da9f4d89930f126f8d2cefc853e0d966ed40`、dirty patch SHA `564c32099088cd9071d46e6c2149c7f588ae6f0d2b9c706146c8ca198294af28`）。実行コードfingerprintと完全rawは `/tmp/issue482-ab-x3f7fox8/` に保持（system temp、永続保証なし）。測定後にテストと報告を追加した。PR HEADはGitHubを参照。

Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、Linux WSL2 x86_64、OPENBLAS/OMP/MKL各環境変数1（実thread数・CPU周波数固定は未検証）。RF-T010 effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、base RF-T008 rev3、固定S2P・seed1013・初期vector・25変数/同じ物理boundsは [#470](../issue470/README.md) のconfig/starts。Search 70点・6設定/28不連続区間 SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、Terminal 476点 SHA `28ee5b630e4842b183a7c36fd610cc32e2509c0044c6a5848ce2fbd147a22e29`。コードと条件：

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
uv run --frozen python project/diagnostics/issue482/benchmark.py
uv run --frozen python project/diagnostics/issue482/gradient.py
uv run --frozen python project/diagnostics/issue482/local_ab.py
```

## 数値・予算・保存

`local_ab.py` はHybrid最初の局所runだけを比較し、終了時にrestart前で止める。名目上限30,000、実際は両モード29,874 Search vector × 70 samples、953 iterations。SciPy自身の `nfev=29874, nit=953, status=0, success=True, message=CONVERGENCE: RELATIVE REDUCTION OF F <= FACTR*EPSMCH` は両者・Hybrid記録と一致。全29,874の入力順vector・目的値の最大差0、終了vector一致、best objective `301.1529908327058`、Terminal signed max margin `5.854485405284301 dB`。Terminal全S・IL・APL・両RLの最大差0。単一局所runのSciPy収束であり、Hybrid全体の収束・RF適合や最適性を意味しない。先行10,000名目上限比較では逐次10,000で中断、batchは最終群を完了し10,010、共通10,000候補の最大差0；batchのSciPy statusは評価数上限、逐次は途中中断でstatusなし。10,000までのbest/Terminal Jは一致した。

312名目上限のplain/timed/memory全14 runは各Search 312、Terminal 1（22,316 RF samples）、MNA 2点。両方式とも予算停止、nit 5、statusなし、Search best `2622.4619123260527`、Terminal J `10.316915763755865 dB`。各receipt/ledgerはRunnerで検証され、Terminal vector・全S/IL/APL/RLは両方式一致。Terminal格子受動性/電力保存および2点独立MNAは各runでpass。scalar Plan SHA `be37f8001bebb0186622b6538b5f9ff0669d5f288082261ba290f9320a1cc91b`、batch Plan SHA `7e0c50b9165eab9e7a4091e1af246b6cc9b6ee0e0e95c9a44245a582d5605e8d`（opt-inと予約が異なる）。

自由座標dの場合batchは最大 `N+max(d-1,0)` をSearchに、Terminalを別に予約する。残数1で25 probesを開始したテストはN=2に対し26 Search forwards、27をTerminal込みで予約・receipt照合。不足は実行前STOP。正常batchではRF一括計算後、SciPyのfunを候補順に1回ずつ呼び共通目的処理を通す。checkpointは途中ではなくグループ/局所run境界でbestを保存、最終vectorも保存する。逐次は従来の厳密上限・checkpointを維持。

異常時、RF Coreは失敗バッチを内部で逐次replayして最初の例外を得る。Workerは成功候補を観測するため更に順次replayし、失敗候補までを各1論理forwardとして計上、確定bestを局所run終了時にcheckpointする。したがって**実計算RF sample数は論理課金数を超え得て、失敗箇所次第で一定ではない**。異常jobは全予約をunknownとして保持しreceiptを発行しない。先行バッチや内部replayは別論理forwardとして二重課金しない。injected failureで先行観測、sample_indexとcheckpointを検証したが、全障害形態を網羅しない。

## 速度

warmup各1回除外、plain 4回ずつAB/BA交互、Runner全体wall（Plan/source確認、checkpoint、Terminal、receiptを含む）。全実測秒：

| 順 | scalar | batch |
|---|---:|---:|
| 0 | 0.641326 | 0.603777 |
| 1 | 0.633475 | 0.604771 |
| 2 | 0.662163 | 0.615334 |
| 3 | 0.712795 | 0.592848 |
| 中央値 | 0.651744 | 0.604274 |

中央値比1.079倍、約7.3%短縮。短時間・4反復のため一般化不可。別のtimed各1回はSearch RF合計156.194 ms（312 scalar calls）対70.709 ms（12 scalar + 12 batch calls）、inclusive計時でplainとは別。tracemalloc単独実行peakは4,958,213対4,941,385 bytes（NumPy追跡分を含むがRSSではない）。

最初の数値勾配1組（基点のobjective callbackから25番目probe callbackまで、setup・基点を除く、各callbackの計時負荷を含む）の別計測、warmup各1回、AB/BA交互6値 [ms]：scalar `14.8445, 11.6051, 11.4772, 11.6568, 12.6087, 11.6103`、batch `6.9269, 6.1540, 6.2026, 6.1119, 6.1860, 7.3501`。全体性能へRFcore単体の速度比を流用しない。

**提案:** 現時点では明示opt-inで独立レビュー、既定はfalseのまま。限定条件で速度改善と候補順同値が観測されたが、他seed/トポロジー/ハードウェアや障害の網羅は未検証。有限格子の数値観測であり連続帯域、EM、SRF、Q(f)、公差、実測は未検証。詳細な実測rawは上記tmpに残存する。

## 回帰

`test_issue482_batch_fd` 5（合成目的・予算・固定座標・例外、実RF/receipt、response/both cache）、`test_hybrid_optimizer` 11、`test_issue448_common_runner` 5、`test_issue479_rf_batch` 5、`test_issue476_rf_cache` 5、`test_issue309_rf_core` 8、`test_phase2_branch_mna` 6、`test_issue419_power_probe` 4、`test_issue450_minimax` 11、`test_issue458_profile` 5、`test_issue313_preflight` 10、storage audit を実行しPASS。CIとChatGPT独立レビューは別判定。
