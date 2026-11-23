# Issue #509：TRF restart の基準開発診断

正式EXPではない。RF-T010 **trial**・seed 1013 のみ。探索中の Search 目的値（正の違反の二乗和）が各時刻までに最小の点を選び、探索後に Terminal 476点で J（最大 signed margin、低いほど良い）を評価した。**Terminal J 自体を用いて候補を選び直していない**。全イベントを保存していないため、別窓や、全観測点の中で Terminal J が真に最小の点は再集計できない。

| Search wall窓 | run1 J | run2 J | run3 J | Search目的 dB²の範囲 | 状態 |
|---|---:|---:|---:|---:|---|
| 1秒 | 7.386811 | 7.386811 | 7.386811 | 449.304889 | 観測 |
| 5秒 | 0.517100 | 0.517997 | 0.517899 | 2.309809–2.323270 | 観測 |
| 20秒 | 0.313397 | 0.313397 | 0.313397 | 0.481159 | 観測 |

各窓の完全vector・SHA・実観測時刻・forward・pass IL・H2/H3と科学監査は `summary.json` / `paired.csv`。窓より前に上限で停止した hold ではない。3反復とも5局所run/4 restart、Search 5000 forwardで終了、全体 `evaluation_budget_exhausted` / 非収束。内訳は ftol 103、ftol 84、ftol 136、xtol 2013、評価上限 2664 forward。最後のrunだけの最終点でなく全観測bestを選択。終了時Jも0.313397、SHA `9e9e15ed5d61e3781062a8a2a17692e8ccdc44bb81d3afb88cef5c4b230788be`。局所成功は全体収束を意味しない。3本ともSearch requested/computed 350000 samples、Runner Terminal別に476 samples・独立MNA 2点、各窓の事後Terminal別に3 forward/1428 samples・MNA 6点。RF異常・STOPなし。Solver wall 30.131/30.642/30.586秒、CPU 30.080/30.586/30.535秒。warmupは28 forward・0.164秒で予算終了し主表に含めない。

参照のみ：#505の別測定では単発TRFは1/5/20秒に J=7.386811（約0.6秒でftol終了後hold）、Hybridの中央値は9.8945/5.8517/0.9218。今回5/20秒では単発参照より小さいJを観測したが、**別source/計測条件・ホスト情報の異なる履歴値との同一wall比較や統計的な優劣の証明ではない**。同一初期値の単一seedのタイミング反復であり普遍化できない。TRF restartが改善し得ることは観測したが、Hybridとの本比較や収束条件のsweepは未実施。

## 条件・監査・限界

- 計測時HEAD `dc836676cdbdbc2368544cf5a5292ca20d2ddf60`、main起点 `b506e805809fc57531008c88cde94cfcce2bbb09`、Runner source identity・空dirty patch SHA・script SHA・全Planは `summary.json`。計測後に、負のSciPy statusと予算同時到達時に `solver_failure` を優先する修正とそのテストを追加した。今回の最終statusは0なのでこの変更は観測停止理由に影響しないが、変更後の時間測定は実施していない。
- RF-T010 effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、base RF-T008 `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、bands `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`。S2P input `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、output `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9b84da`。
- 4L2C/25変数、6設定・28独立区間、固定S2P外部port。初期vector SHA `6e06d271e0ea54eecb547cfff045a6edda4850bfaa1f9c23bf9f3037ab867131`、bounds SHA `bf274caf1ff46fed4fead6af5dc2f151bdb7579f62117434c1507aed44aea521`、Plan SHA `01b2f2d86eb6bc8b8de16e1afd35d28f2c2ac3f473329576809b31ff47853a0c`。Search 70、Terminal 476点。TRF解析Jac/cache off、sigma 0.1、ftol 1e-8、x_scale 1.0、xtol/gtol SciPy既定、max_evaluations 5000。Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、BLAS/OMP/MKL各1 thread。計測順はwarmup、run1、run2、run3（逐次・同一host）。
- 全窓候補の物理boxとL行列SPD、Terminal格子上の外部受動性・電力保存、独立MNA spot [0,111] は通過。`physical` 中の independent_mna_checked=false は物理検査単体の記録で、別途実施したMNA spot PASSと混同しない。promotionはblocked。全窓とも J>0 で有限格子適合せず。連続帯域・SRF・Q(f)・EM・公差・実測・実装可能性・大域最適性は未保証。
- 診断wrapperは最初の局所solver開始から時刻を継続し、目的値確定後callbackで各観測をメモリ記録。ハッシュ・窓選択・TerminalはSearch後。wallには局所run間の処理を含む。観測callbackのオーバーヘッドは未校正。rawイベントやcheckpointはGit保存しない。

再現例（空のsystem temp配下の未存在pathを各runに使用）：

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
 uv run --frozen python project/diagnostics/issue509/compare.py trf 5000 /tmp/<fresh-run> /tmp/<fresh-record>.json
```

`assemble.py` は測定時の4レコードとRunner一時結果から抽出する。既存研究データ・正式EXPは変更していない。
