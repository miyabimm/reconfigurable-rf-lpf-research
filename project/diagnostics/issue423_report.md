# Issue #423 — dB異常値検査のplain A/B：本番不採用

## 判断

`np.concatenate(metrics) > -np.inf` による4配列の集約を診断内だけで比較した。100 vectorでは全出力ビット一致、STOP境界・科学回帰も通過した。局所plainは一貫して速いが、**完全forwardは3 batchとも中央値こそ改善方向ながら、対応差の範囲と外れ値が大きく勝率も9/12、7/12、12/20**。共有hostの変動に対して明確かつ再現性のある改善と判定できないため、Issueの条件に従い**本番`src/`は変更しない**。将来の速度改善や数学的同値性を一般に否定するものではない。#419の候補は使っていない。

## 固定入力・環境

- 実行時HEAD/main `b068858fe8294212230be31435828712809042d1`、本番source差分なし。`source_identity` SHA `9ca5096fad2fbf0f949db1a91bea825eeced3a995572da0c8e6b7fa97c869788`（1 thread環境）、対象source diff SHAは空diff `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`、`src/lpf/rf_core/model.py` SHA `0e1152cb0b466b9cbc29d8200e3ab30a35db972fbaa07300594102867589e497`。候補は[driver](issue423_probe.py) SHA `7a8e2b1aea021d479cf6a277c2fe9b79e3feb2fa42037d7e276854f6f4873b40`で現行関数の該当1行だけを置換して生成。共通driver [#419](issue419_probe.py) SHA `c096bda549c8dec5ee5a643bcd29eada99cb4614ed2eb7928e34cd6c34bf1354`。
- RF-T008 rev3 **trial opt-in/full_lpf** effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。active正式RF-F003 SHA `e12c42b11d12db7f20983c48cfa441ea96e362e533450d5862aa8a271c82af86`には性能・RF適合を一般化しない。Plan SHA `8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e`、grid SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、6設定・28不連続区間・70点/forward。
- bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、入力S2P `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、出力S2P `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`、starts seed1002 `63b671ea269656843df118230b7d920e91515188235809b6dd0efd667ac997ab`、固定100 vectorファイル `e87355eb364073a5743062e8e4ee7c90c3012cbfb5e38bef6283860381736ba0`、個別vector SHA照合。各processの旧forward由来S連結SHA `1512e77f269a1524727c1bd8d9e420a541714ccdb9caae3f00b2b9da2713bb02`は全179 processで一致。
- Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、OpenBLAS 0.3.34.106.0、Ryzen 7 PRO 4750G共有host、affinity CPU 0、OPENBLAS/OMP/MKL各1 thread。占有・温度・外部負荷は未制御。

## 同一batchのplain A/B

各runは新process、同じ100入力を計測前にwarmupし除外。旧新を隣接・順序交互で実行。局所は収集済み実Sによる完全`power_response` 100回、forwardは完全`RFEvaluator.evaluate()` 100回。単位ms/100回、差は各pairの新−旧。全run（setup、wall/CPU、順序、外れ値、同値性・MNA）を[batch 1](issue423_runs.json)、[batch 2](issue423_runs_repeat.json)、[batch 3](issue423_runs_third.json)に保存。

| batch | モード | 旧/新 wall中央値 | wall対応差中央値 [min,max] | 新が速い組 | 旧/新 CPU中央値 | CPU対応差中央値 [min,max] |
|---|---|---:|---:|---:|---:|---:|
| 1 | local | 11.761 / 9.803 | −2.000 [−6.768,−1.458] | 12/12 | 11.761 / 9.802 | −1.993 [−6.768,−1.458] |
| 1 | forward | 49.055 / 46.912 | −1.646 [−6.132,+17.213] | 9/12 | 49.055 / 46.811 | −1.894 [−6.132,+17.240] |
| 2 | local | 11.697 / 9.889 | −1.735 [−5.512,−0.918] | 12/12 | 11.697 / 9.888 | −1.734 [−5.485,−0.918] |
| 2 | forward | 49.629 / 48.463 | −0.806 [−42.179,+79.660] | 7/12 | 49.628 / 47.968 | −1.239 [−41.432,+45.903] |
| 3 | local | 11.902 / 9.929 | −1.869 [−9.235,+7.434] | 18/20 | 11.902 / 9.928 | −1.870 [−9.234,+7.350] |
| 3 | forward | 55.073 / 54.130 | −1.765 [−19.228,+40.329] | 12/20 | 55.071 / 54.145 | −1.763 [−19.252,+40.103] |

CPUの勝数も各行のwall勝数と同一。外れ値を除外・再選別していない。batch 2・3は初回の外乱を受けて追加測定した。率や局所削減分のforwardへの単純加算は主張しない。

## 数値・科学・STOP

- 各batchの全100 vectorで複素S、IL/APL/入力・出力RL、worst IL、順序付きmandatory g 42個の旧新を比較。最大絶対差すべて0、すべてbit一致。独立branch-current MNAで各batchの代表index 0/49/99×70点を検証、最大絶対差 `2.214e-12`（閾値1e-9）。独立検証はSPD、外部S受動性、固定S2Pを含む各損失・電力保存を検査。代表点以外や連続帯域を証明しない。
- [契約テスト](../../tests/test_issue423_db_probe.py)で空配列、ゼロ・極小透過、複素Z、反射境界、特異/near-singular、#419の3つの有限極端STOP反例を旧新比較。`ValueError`、`wave_singular`、`wave_nonfinite`、`available_gain_undefined`、`db_invalid`、予期しない例外伝播を確認。4対数位置ごとの`NaN`/`±inf`は障害注入、`+inf` dB許容・`NaN`/`-inf` dB拒否を確認した。自然発生の主張ではない。
- 旧・候補の両方で下記9 test file **各49 tests PASS**：`test_issue307_constraints.py`、`test_issue309_rf_core.py`、`test_issue311_performance.py`、`test_issue343_d3_science.py`、`test_rf_f003_t005.py`、`test_phase2_branch_mna.py`、`test_phase2_generic_coupled_lc.py`、`test_phase2_numeric_diagnostics.py`、`test_phase2_s2p_grid_cache.py`。RF-F003/T005/T006/T007/T008、T006追加帯域、H2/H3、固定S2P、SPD、MNA/電力・STOPに関連する既存回帰。加えて `test_issue410_c_assembly.py` 旧・候補各5 PASS、`test_issue419_power_probe.py` 4 PASS、`test_issue423_db_probe.py` 2 PASS。
- 任意入力や連続帯域、実測、EM、SRF、Q(f)、公差は未検証。旧 `test_rft003_loss.py` は#419で参照先履歴ファイル欠如が報告されており今回は未実行。CIはPR上で別途確認。

## 消費・再現

3 batch合計179 process：setup 17,900 forward、forward plain warmup+測定17,600、equivalence旧新600、合計 **36,100 forward / 2,527,000 requested samples**。局所plain warmup+測定17,600 `power_response`呼出（setupとは別）、独立MNA 630点。既存unit test分はこの計数に含めない。Solver・新EXP・探索は0。source identity取得の初回は`PYTHONPATH`未設定で失敗し、設定して再実行した（RF forwardなし）。

```bash
uv sync --frozen
uv run --frozen python project/diagnostics/issue423_probe.py --pairs 12 --output /tmp/issue423-replay-new.json
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --frozen python -m unittest discover -s tests -p 'test_issue423_db_probe.py' -v
```

出力先は未存在にする。前記9 fileと#410を旧・候補で実行するには、それぞれ新Pythonで`sys.path[:0]=['src','scripts','tests','project/diagnostics']`、`import issue423_probe`後、候補だけ `issue423_probe.base.rf.power_response=issue423_probe.candidate()` とし、`unittest.defaultTestLoader.discover('tests', pattern=...)`を実行する。テストは1 thread、旧新別process。driverは利用可能な最小CPUを選ぶ。提出commitではHEADを含むsource identityが変わるので、元HEADと上記driver SHAを照合する。
