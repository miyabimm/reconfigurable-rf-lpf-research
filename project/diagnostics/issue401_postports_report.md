# Issue #401: source/load高速化後の時間内訳

## 条件・原記録

ユーザー指示により、固定source/load impedanceの事前準備を採用したコードで、[変更前の詳細測定](issue401_refined_report.md)と**同じ計測region**を再測定した。初回plainに大きな外れ値があり、原因を特定できなかったため、結果を除外せず同条件で一式を再測定。各batchはplain/timed/deep各warmup 1、測定はplain/timed各10をP→T→T→P順、deep 10、各run別process。warmupは集計から除外。計66 run／**6,600 forward・462,000 samples**（100 nfev × 70 samplesから算出）、追加の検証forwardなし。正式EXP・Campaign・新規候補探索ではない。

- 変更前 HEAD `f5bd7dbb0d5ccc580999633b76116eb7356b80db`、source identity SHA `240c16eec5c9b9da2cdb8c3a9bd5ed5f78750a4b7d72b5170f26adcbbaeade4c`。
- 高速化後 初回HEAD `6908e52149de9f59c51c859f291ba6f4cd8de72c`／source SHA `5ee9ed0a32515395786d7984e81a239b9898fdd1167e26528de77b3c8a2e1fe2`、[初回原記録](issue401_postports_raw/)のfreeze SHA `80a7c1bbae4d6505b7a443f2e16e6926a75b41c93640aa4c848409fef8509c39`。
- 高速化後 再測定HEAD `124a55c5b1cda68b17a41daeeede7447d70b0437`／source SHA `096574332493de384558a8e2fbf272e24d2aaf4fa8e993156071d033460c48a4`、[再測定原記録](issue401_postports_repeat_raw/)のfreeze SHA `a5fe74962eff41fed7f8458e4021267dac5ea031538f32a3c71b2c511c3fe0e9`。両後版の実行sourceファイルは一致、後者は結果とbatch出力指定の記録追加のみ。両実行source dirty patch空。変更前後のsource file SHA差は `src/lpf/rf_core/model.py` のみ。計測regionを定義する `issue401_timing.py` SHAは3測定とも `10c3b0bb24489104a62a71a70cf47ecf852e63a84d525da56adb0307ece3f948`。開始順・driver/benchmark SHA・各runの開始予約、stdout/stderr、全solver result、timer rawは各freezeとJSONを参照。
- RF-T008 rev3 **trial opt-in**、full_lpf、6設定・28別区間、70 samples/forward、Hybrid sum・seed1002・max100/restart0。effective policy SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、Plan `8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e`、grid `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、vector `6203467121a4e37baaa51c471aaecb3174f3374f9ab955d6fbf101f7b5ce935f`、starts file `63b671ea269656843df118230b7d920e91515188235809b6dd0efd667ac997ab`。bands/S2P SHAはrawに記録、変更前後で一致。
- Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、BLAS/OMP/MKL 1 thread、CPU affinity 0。環境は同一だが共有host・CPU周波数・他負荷・温度は未制御。変更前後は別時刻・非交互であり、以下の差は新規A/B速度改善率ではない。

全後版66 run、ならびに変更前33 runと比較したsolver出力全項目はJSON値で完全一致。全run nfev=100、`evaluation_budget_exhausted`、**未収束**。全後版timed/deepはcallback/RF/requirements/residual各100回、deep Y→S/decode/encode等100回、cascade 200回、失敗0。各forwardのRF配列は本再測定では保存していない。別途実施した3候補の旧新配列digest比較は[port A/B報告](issue401_ports_ab_report.md)参照。

## 全体と計測負荷（100 forwardあたり、ms）

中央値［最小, 最大］、各10測定。setupはsource identity・preflight・evaluator構築を含む。plainのsolveは`worker.solve()`全体で、Hybrid単体ではない。

| 区間 | 変更前 | 後：初回 | 後：再測定 |
|---|---:|---:|---:|
| plain setup wall | 256.202 [253.936, 272.232] | 276.140 [261.245, 303.603] | 272.182 [256.380, 281.856] |
| plain solve wall | 97.093 [90.692, 122.711] | 99.753 [86.025, 239.046] | 91.730 [82.902, 100.729] |
| plain solve CPU | 97.044 [90.574, 122.518] | 99.668 [85.997, 238.862] | 91.708 [82.901, 100.732] |
| timed solve wall | 96.086 [92.257, 100.849] | 92.494 [84.412, 101.947] | 93.364 [82.875, 103.090] |
| deep solve wall | 100.833 [97.758, 105.686] | 98.506 [92.410, 106.680] | 99.118 [90.650, 162.408] |

同一batchの順番対応timed−plain差中央値［範囲］は、変更前 −0.879［−27.883, +10.157］ms、後初回 −7.990［−137.100, +3.921］ms、後再測定 +2.251［−14.879, +18.220］ms。各10組・seed401・10,000再標本による中央値の参考bootstrap 95%区間はそれぞれ［−6.440,+4.525］、［−45.412,+0.677］、［−9.959,+9.734］ms。分布が大きく重なり、実RFタイマー費用は特定できない。初回plain最大239.046msはCPU時間238.862msであり、その原因は不明。再測定deepにも最大162.408msの外れ値がある。いずれも除外していない。過去の合成校正（1 wrapper約1.50µs/call、2段約3.01µs/call）はRFでの負荷そのものではない。

## L1/L2（timed inclusive、100 forwardあたりms）

| region | 回数/run | 変更前 中央値［範囲］ | 後初回 中央値［範囲］ | 後再測定 中央値［範囲］ |
|---|---:|---:|---:|---:|
| solve_total | 1 | 95.926 [92.015, 100.696] | 92.342 [84.152, 101.793] | 93.178 [82.727, 102.811] |
| hybrid_minimize | 1 | 94.810 [90.789, 99.667] | 91.317 [82.794, 100.698] | 91.947 [81.667, 101.576] |
| postsolve_validation | 2 | 0.944 [0.888, 1.049] | 0.949 [0.885, 2.341] | 1.051 [0.920, 1.239] |
| solver_callback | 100 | 87.261 [83.258, 91.502] | 83.100 [75.271, 91.243] | 83.643 [74.288, 91.870] |
| rf_forward | 100 | 79.284 [75.597, 82.949] | 74.288 [67.468, 81.137] | 74.770 [66.431, 81.896] |
| requirements | 100 | 4.326 [4.076, 4.675] | 4.637 [4.185, 5.345] | 4.514 [4.244, 5.342] |
| residual | 100 | 1.905 [1.798, 2.094] | 2.200 [1.844, 2.400] | 2.016 [1.785, 2.321] |

`solve_total` ⊃ `hybrid_minimize` ⊃ `solver_callback` ⊃ RF/requirements/residual、後段物理検査はsolve内の別区間。親子の時間は加算しない。RF/callback比の中央値［範囲］は変更前90.82%［90.25,91.03］、後初回89.30%［88.87,89.63］、後再測定89.35%［88.94,89.76］。RFはなお主要な時間領域だがtimer費用を含む。

## L3（deep inclusive、100 forwardあたりms）

| region | 回数/run | 変更前 中央値［範囲］ | 後初回 中央値［範囲］ | 後再測定 中央値［範囲］ |
|---|---:|---:|---:|---:|
| RF forward | 100 | 83.817 [81.534,87.414] | 78.404 [75.224,84.714] | 79.016 [74.269,134.615] |
| port admittance | 100 | 35.860 [33.910,37.130] | 38.913 [36.677,43.261] | 38.631 [35.824,55.608] |
| node admittance | 100 | 25.979 [24.335,26.929] | 28.377 [26.874,31.865] | 28.241 [26.016,40.193] |
| matrices | 100 | 8.744 [7.963,8.847] | 9.779 [8.586,11.005] | 9.465 [8.554,13.766] |
| power response | 100 | 15.388 [14.828,15.845] | 14.977 [14.171,16.049] | 15.251 [14.225,27.879] |
| decode | 100 | 7.911 [7.591,9.129] | 8.276 [7.789,8.935] | 8.153 [7.743,27.611] |
| encode | 100 | 0.830 [0.792,0.882] | 0.894 [0.802,1.004] | 0.892 [0.840,1.232] |
| Y→S solve | 100 | 2.586 [2.494,2.868] | 2.690 [2.542,2.949] | 2.712 [2.599,3.863] |
| cascade合計 | 200 | 5.636 [5.496,5.734] | 5.813 [5.623,6.225] | 5.981 [5.469,8.139] |

`RF ⊃ port ⊃ node ⊃ matrices`。power/decode/encode/Y→S/cascadeはRF内のportとは別のinclusive region。Y→S solveはport/power内のsolveを除外。RFからport/power/decode/encode/Y→S/cascadeをrunごとに差し引いた未分解残余の中央値［範囲］は、変更前 **15.768［15.347,16.664］ms**、後初回 **6.764［6.293,7.526］ms**、後再測定 **6.897［6.137,10.282］ms**。残余には旧policy JSON decodeやimpedance検査に加え、配列準備・変換・関数/計時境界外処理を含む。後の値が小さい観測は変更方向と整合するが、非交互実行・計時誤差のため**差の全てを当該変更に帰属しない**。deep値からplain改善率を計算しない。

この条件の候補検討ではport/nodeとpower responseがなお主要区間。ただしinclusive時間全額の削減は不可能であり、C incidence事前準備案は別A/Bで効果を判別できず不採用済み。次の最適化は個別の変更・科学的回帰・交互plain A/Bで検証する。今回の有限測定はwindow100の実時間改善、RF合格、全軌道・連続帯域、独立dense、EM/SRF/Q(f)/公差/実測や物理実現性を保証しない。
