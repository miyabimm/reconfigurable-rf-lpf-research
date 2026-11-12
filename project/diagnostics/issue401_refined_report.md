# Issue #401: timer校正とRF Core細分化（追加診断）

既存の26 run証拠は変更していない。新規計測はHEAD `f5bd7dbb0d5ccc580999633b76116eb7356b80db`、source identity SHA `240c16eec5c9b9da2cdb8c3a9bd5ed5f78750a4b7d72b5170f26adcbbaeade4c`、対象source dirty patch空。条件は従来と同じRF-T008 trial/full_lpf、seed 1002、70 samples、100 nfev、固定Plan/grid/vector、単一thread、CPU affinity 0。[開始順・SHA・各開始/終了/solver/timer原記録](issue401_refined_raw/)を保存。全33 run（plain/timed/deep各warmup 1、plain/timed各測定10、deep測定10）はsolver出力一致、各nfev100で予算切れ・未収束。計3,300 forward／231,000 samples（nfevから算出）。正式EXP・新しい候補探索ではない。

RFを使用しない合成noopで、20,000回×10組、plain/wrapped/nestedの順序を交互に測定。wrapperをplainから差し引いた中央値は1 regionあたり約1,504 ns/call、2段nested全体で約3,011 ns/call。`issue401_timer_calibration.json`に原値を保存（SHA `e2ad491b01c0185d6a191a4f3f4d4c7abbe89dc89339eb1d859c7c3e86776857`）。ループ・時計・共有負荷の影響を含む概算であり、RFのtimer負荷を直接表さない。

| 100 forwardあたり | 中央値ms [範囲] |
|---|---:|
| plain solve wall | 97.093 [90.692, 122.711] |
| timed solve wall | 96.086 [92.257, 100.849] |
| deep solve wall | 100.833 [97.758, 105.686] |

plain/timedの順番対応10組の差中央値 −0.879 ms、範囲 −27.883〜+10.157 ms。ばらつきが大きく実RFの計測負荷の厳密値は不明。比較は同じ`worker.solve()`境界であり、plainのHybrid単独壁時計は分離していない。deepは診断probeを含みplainの改善率には使わない。

## deep region（各10測定の中央値、100 forwardあたりms）

| region | ms | 関係 |
|---|---:|---|
| RF forward | 83.817 | 全体、inclusive |
| port admittance | 35.860 | RFに包含 |
| node admittance | 25.979 | portに包含 |
| matrices | 8.744 | nodeに包含 |
| power response | 15.388 | RF内、portとは別 |
| decode | 7.911 | RF内、portとは別 |
| encode | 0.830 | RF内、portとは別 |
| Y→S solve | 2.586 | RF内、portとpower内のsolveを除外 |
| cascade 2回/forward | 5.636 | RF内、合計200呼出 |

全regionのcount/failedを各runで確認。RFからport/power/decode/encode/Y→S/cascadeを差し引いた残りはrun別15.347–16.664 msで、配列準備・変換・関数/計時器・タイマーregionの境界外部分を含む。各演算だけの確定費用ではない。追加wrapperの干渉があるため、深い区間同士・親子を足し合わせて効果を見積もらない。

候補：固定のC incidence再構築を減らす変更はnode処理の一部を対象にできるが、その直接時間や効果はこの計測だけでは不明。変更の採否には別途、同一条件のplain A/Bと全6設定・複素S・SPD・独立MNA等の回帰が必要。各評価点のRF応答系列は今回未保存、RF適合・連続帯域・EM・Q(f)・SRF・公差・実測・物理実現性は未検証。
