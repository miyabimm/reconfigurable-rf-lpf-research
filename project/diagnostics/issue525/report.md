# Issue #525 — RF-T010 L/C探索bounds比較（開発run）

## 結論と限定

固定4L2C回路・20対応seed・各5000 Search forwardの観測では、B（L≤20 nH、GJM01 C≤10 pF）はTerminal正違反二乗和の中央値を199.934→5.917 dB²に下げ、20組中12改善・8悪化・同値0だった。一方、seed1001は4.356→8503.196、1015は111.343→8063.163 dB²と大きく悪化。最大signed marginの比較は13改善・7悪化であり、二乗和と同じ指標ではない。全40 jobは予算使い切り・非収束で、有限Terminal格子閾値達成は両条件とも0/20。限定の既定化を示す結果ではない。開始分布、TRF座標正規化、restartの物理幅の影響は分離できない。Lのみ/Cのみ、追加予算、既定化はユーザー判断であり本runでは未実施。

## 条件と証拠

- RF-T010 **trial** effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、definition canonical SHA `bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068`、外部S2Pを含む外部port。実行HEAD `1ff1a0cce3d522a904c81e6e804803aaebe16b33`（clean）、共通source SHA `c9ecd72aa439c09c1cc59b27fb2e1d0662dcc5c6dc903870d1c32d7a8914db1d`。
- 25座標中先頭4 LQP02HVの上限27→20 nH、次の3 GJM01の上限100→10 pFのみ変更。下限・PCB C・k・IC fixed/variable Cを保持。seed 1001–1020の同一正規化Sobol点から生成し、Aのvector SHAを#513と一致確認。初期値40件の部品・SPD検証、2 Planの物理sub-box・予約・6設定28区間・S2P照合にPASS、illegal startなし。
- 標準CLI、TRF exact、signed_margin_db/sum、ftol=1e-6、x_scale=1、restart_sigma=0.1、Search 70点、Terminal 476点、MNA [0,111]、plain、CP1000。`--rf-cache-mode lk` を指定したがTRF感度経路の**実効**cacheは両条件とも `off`（result確認）。Search grid SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、Terminal `28ee5b630e4842b183a7c36fd610cc32e2509c0044c6a5848ce2fbd147a22e29`。
- Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、PyYAML 6.0.3、OpenBLAS/OMP/MKL各1。2026-11-27 A→B。各run exit 4、20/20 receipt照合済み、異常・未実行・unknownなし。実消費は各100,020 RF forward（Search 100,000＋Terminal 20）、7,009,520 RF samples、40 MNA samples、合計200,040／14,019,040／80。合計は予約上限と一致。
- rawは `/tmp/issue525-raw/{baseline,limited}/`、入力は `/tmp/issue525-inputs/` に保持（**一時領域で永続保存を保証しない**）。保存済み `results.json` は各jobのreceiptとrawファイルの原byte SHA/サイズ、全CP、vector、消費、検証値を保持。`paired.csv` はseedごとの指標・差・CP・探索統計を保持。巨大rawはGitに入れていない。入力manifestは `input-manifest.json`、raw SHA `cc87a17397eb36a5c2e0a3c0acb5a3e2a7aae1e25a2d01efdf7a8148119fc80e`。`results.json` SHA `77af9019f9e5c82f43672f7f9ede8e7d0f205ef9fd491de3eb2ab8900c0e8e6d`、`paired.csv` SHA `9af014de011c1108fbc1bde43257762c68dd49ae6092e939f47c6da7408fb5c2`。
- Plan canonical SHA A `aae523265a35c96cd5cf9918a39ae597defcce40f31ab06290d583b58cd6ca9a`、B `4448002cdf5ba5e98d5329e6dabfe38a36d60ecf376eeafd5479f07c4af3c285`。bounds SHA A `bf274caf1ff46fed4fead6af5dc2f151bdb7579f62117434c1507aed44aea521`、B `01b1683266b4776bb7ebdcff3f09de827d9f899ab94d11eef31fb9239185276b`。plan/run原byte SHAとRF/bands/S2P、各入力SHAは `results.json`。

## 比較

四分位数はNumPy線形補間、表は中央値 [Q1, Q3]。差はB−A。

| 指標 | A | B | B−A |
|---|---:|---:|---:|
| Terminal 正違反二乗和 dB² | 199.934 [22.830, 896.007] | 5.917 [3.674, 1191.982] | −16.544 [−889.628, 442.076] |
| Terminal 最大signed margin dB | 1.562 [0.576, 4.255] | 0.336 [0.298, 5.046] | −0.180 [−3.457, 1.256] |
| worst IL dB | 2.312 [1.326, 4.516] | 1.086 [1.048, 4.779] | −0.180 [−3.413, 1.471] |
| min H2 attenuation dB | 28.877 [25.745, 29.929] | 29.937 [26.321, 29.992] | 0.093 [−0.786, 2.886] |
| min H3 attenuation dB | 28.895 [28.488, 29.981] | 29.983 [28.285, 29.989] | 0.009 [−0.899, 1.220] |
| Search 最終best目的 dB² | 26.981 [2.723, 125.326] | 0.714 [0.443, 166.922] | −1.002 [−124.459, 66.270] |

seed1006の二乗和は7142.458→3.383、seed1002は953.184→1.304と改善したが、上記の大幅悪化もある。個別差・最大margin・IL/H2/H3は `paired.csv` に全20組記録。local_runs中央値 A 14.5/B 14、restart中央値 13.5/13、njev中央値 4245.5/4254、nfevは全件5000。stopは全件 `evaluation_budget_exhausted`。

### checkpointの解釈

TRFの周期checkpointは**そのforwardで評価した観測値で、累積bestではない**（restartで悪化しうる）。`paired.csv` は各CP1000/2000/3000/4000/5000の生観測と、それまでに保存されたCPのみの最小値 `best_saved` を区別する。後者も全forward中の真のbest曲線ではない。CP5000には最終global bestの追加checkpointが同一forwardにある場合があり、`best_saved` にはそれを含む。全seed全CPが存在。各時点の保存CP内best中央値（A/B、dB²）は1000: 4370.482/167.075、2000: 177.146/167.057、3000: 125.987/84.035、4000: 125.987/1.933、5000: 26.981/0.714。途中の真のbest曲線はrawに記録されず復元不能であり、未検証として扱う。

### 境界と検証

各最終vectorの全25座標・L/C上限距離 `(upper-value)/(upper-lower)` は `results.json` に記録。探索範囲幅の1%以内の件数（20候補中、定義順L0–L3、GJM C0–C2、PCB C）はA `[9,1,2,0,0,5,4,8]`、B `[4,10,4,4,2,4,3,7]`。候補採否の基準ではない。全件component policyと全6設定、L行列SPD（最小固有値の全件最小 `6.936e-10 H`）、Terminal格子での受動性・電力保存、独立MNA 2点passを確認。MNAは全帯域検証ではない。結果は有限格子上のシミュレーションであり、連続周波数・SRF・Q(f)・EM・ばらつき・実測・物理実装性・正式RF適合は未保証。

## 再現／監査

新しい未存在パスを使用。探索の再実施は新たな計算であり、承認済み今回実測とは区別する。

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
uv run --frozen python project/diagnostics/issue525/generate_inputs.py /tmp/NEW-525-inputs
mkdir /tmp/NEW-525-raw
for arm in baseline limited; do
  uv run --frozen python scripts/run_rf_search.py develop \
    --config /tmp/NEW-525-inputs/$arm/config.yaml --starts /tmp/NEW-525-inputs/$arm/starts.json \
    --search-bounds /tmp/NEW-525-inputs/$arm/bounds.json --output /tmp/NEW-525-raw/$arm \
    --spot-checks '{"terminal":[0,111]}' --checkpoint-interval-forwards 1000 --rf-cache-mode lk
  rc=$?; if [ "$rc" != 0 ] && [ "$rc" != 4 ]; then echo STOP; break; fi
done
# collectorにはbaseline/limitedが子ディレクトリのraw親を渡す。
uv run --frozen python project/diagnostics/issue525/collect.py /tmp/issue525-inputs /tmp/issue525-raw /tmp/NEW-525-results.json
uv run --frozen python project/diagnostics/issue525/paired.py /tmp/NEW-525-results.json /tmp/NEW-525-paired.csv
```

監査は40件のinput/result/receipt/checkpoint原byteと親台帳、Plan/source、初期・最終vector、格子・設定・予算・検証状態を照合。再集計結果は保存済みJSONとbyte一致。入力をRF forwardなしで再生成し全ファイルbyte一致。`test_issue503_trf_runner.py` 8件、`test_issue509_trf_restart.py` 20件PASS。実行時点のmainは `d6d9712cc826216f6e74b2e9c4e2cea4c0c0a498`。独立レビュー・CIは別判断。
