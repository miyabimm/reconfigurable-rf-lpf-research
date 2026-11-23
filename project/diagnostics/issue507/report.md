# Issue #507：TRF ftol × Jacobian スケーリングの開発診断

**正式 EXP ではない。** RF-T010 trial、seed 1013 のみ、同一初期 vector、4条件各3回。評価は固定 S2P を含む外部ポート、6設定・28個の独立区間。Search 70点、Terminal 476点。結果は単一 seed・有限格子・シミュレーションに限る。

## 主結果

各条件の数値は3回で完全一致。wall/CPU は中央値 [最小, 最大] 秒。Search J と Terminal J は今回同値だが、Search点がTerminal点に含まれ同一最悪点だったためであり一般則ではない。J ≤ 0 が有限格子のRF適合条件。

| arm | ftol / x_scale | Search目的 dB² | Search J / Terminal J dB | 最大pass IL / 最小H2,H3減衰 dB | Solver wall秒 | Runner wall秒 | 終了 / nfev,njev / 最適性 |
|---|---|---:|---:|---:|---:|---:|---|
| A | 1e-8 / 1.0 | 449.304889 | 7.386811 / 7.386811 | 5.124693 / 22.613189 | 0.644 [0.634, 0.772] | 1.290 [1.251, 1.390] | ftol status=2 / 103,96 / 2.784 |
| B | None / 1.0 | 449.304889 | 7.386895 / 7.386895 | 5.124673 / 22.613105 | 0.880 [0.868, 0.914] | 1.475 [1.452, 1.482] | xtol status=3 / 131,117 / 0.0223 |
| C | 1e-8 / jac | 2178.561288 | 14.707597 / 14.707597 | 8.047902 / 15.292403 | 2.488 [2.314, 2.563] | 3.065 [2.871, 3.183] | ftol status=2 / 372,339 / 19.42 |
| D | None / jac | 2178.558025 | 14.707742 / 14.707742 | 8.047518 / 15.292258 | 4.726 [4.437, 4.959] | 5.320 [5.024, 5.496] | xtol status=3 / 721,622 / 0.4026 |

Solver CPU中央値 [範囲]：A 0.644 [0.634,0.768]、B 0.880 [0.868,0.914]、C 2.487 [2.313,2.563]、D 4.726 [4.436,4.958]。Runner CPU：A 1.175 [1.163,1.297]、B 1.390 [1.369,1.404]、C 2.984 [2.791,3.096]、D 5.240 [4.939,5.414]。個々の時間・負荷は `paired.csv` / `summary.json`。数値上の success は全て true だが、**RF有限格子適合は全て false**。上限・STOP・例外なし。4つの28-evaluation warmupは全て予算終了（status=0）、主表に含めない。

ftol だけを無効にした A→B / C→D ではさらに探索しても xtol により停止し、Search目的の改善はそれぞれ約 0.00000015 / 0.00326 dB²、Terminal J はそれぞれ約 0.000084 / 0.000145 dB 悪化した。したがって **ftol だけがこの局所解の停滞原因だとは言えない**。スケールだけを変えた A→C / B→D では時間・品質の両方が悪化し、jac スケールが改善する仮説はこの seed では支持されない。いずれも反復は同一 seed・決定論的な探索のタイミング反復で、別初期値への一般化はできない。次は停止・局所解の診断や restart の別途設計判断を提案し、現時点では既定を維持する。restart の効果はこの比較では未検証。

## 実行・検証条件

- RF-T010 effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、物理 base RF-T008 `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。bands `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、S2P input `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、output `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。
- 4L2C・25変数、初期vector SHA `6e06d271e0ea54eecb547cfff045a6edda4850bfaa1f9c23bf9f3037ab867131`、bounds SHA `bf274caf1ff46fed4fead6af5dc2f151bdb7579f62117434c1507aed44aea521`、Search grid `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、Terminal grid `28ee5b630e4842b183a7c36fd610cc32e2509c0044c6a5848ce2fbd147a22e29`。完全初期vector・bounds・Plan・各候補vectorとSHAを `summary.json` に保存。
- TRF 正規化0–1、解析Jac、linear/exact、restartなし、共通 `max_evaluations=5000`、`xtol=gtol=1e-8`。SciPy 1.18.1、Python 3.12.15、NumPy 2.5.4、OPENBLAS/OMP/MKL各1 thread。順序 ABCD / BCDA / CDAB、各arm独立warmup後に逐次測定。比較scriptは#505の既存Runner測定を使用し、観測イベント記録を無効化。Solver時間はwrapper呼出区間、Runner時間は凍結・Search・Terminalを含み、両者は包含関係にある。
- Search感度 forward・requested/computed samples は各run A 103/7210、B 131/9170、C 372/26040、D 721/50470。Terminalは別に各1 forward/476 samples/独立MNA 2点。`nfev/njev` と実forwardは別の計数。Search Jは選択best vectorのTerminal signed marginsから、完全一致する `(frequency, setting, segment)` のSearch点を抽出して計算し、余分なRF評価なし。今回全runで `best_x` とSciPy最終 `x` は同一だが、両方とSHAを保存。
- 全選択点で6設定の物理box/componentと結合L行列SPD検査（最小固有値は約3.67e-9 H以上）、Terminal格子の外部受動性・電力保存、独立MNA spot [0,111] は通過。独立MNAは全帯域ではない。physical record内部の `independent_mna_checked=false` は物理検査単体の状態であり、別のTerminal独立spot PASSと区別する。promotionはblockedのまま。
- 計測 source HEAD `b1bb84da02b6874de04c378d9794ddb77a869254`、dirty patchなし、Runner source SHA `c72df65d653753c61be4f293c3044bddb849df14653b15357d611e4f7c6138be`、計測script SHA `423e89976dc7ef49a70871c6b19d083cda6cf056c5a110b4a8842cc4cb4ea1c6`。測定後の集約script・レポートは当時のsourceに含まれない。baseline Aは#505のSearch目的449.30488878、Terminal J 7.38681053、103 forward、ftol停止を再現。

`summary.json` と `paired.csv` は比較に必要な指紋、全候補、各runの状態・性能・時間を保存する。rawイベント、Runner checkpoint・receiptはGitに保存しないため、後から別の時間窓を再構成できない。途中窓は今回取得せず、各solver終了時のSearch最良点を比較した。再現には空のsystem tempの未存在pathを用いる：

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
 uv run --frozen python project/diagnostics/issue507/compare.py /tmp/<fresh-issue507-dir>
uv run --frozen python project/diagnostics/issue507/assemble.py /tmp/<fresh-issue507-dir> /tmp/<fresh-summary-dir>
```

全探索・時間途中の品質比較や連続周波数保証ではない。SRF、Q(f)、EM、製造公差、実測、物理実装可能性・大域最適性はいずれも未検証。正式EXP、20 seed比較、既定値変更は実施しない。
