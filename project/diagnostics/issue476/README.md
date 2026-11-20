# Issue #476: Search RFキャッシュ4条件の開発診断

## 条件と方法

正式EXPではない。測定したコードHEAD `0eacecb57e61f3ec6d5e923fa297488b116a0b52`、クリーンtree（この報告は後続commit）。前の #475 マージ `3decc825` を基点とする。入力・grid・環境の詳細とSHAは [#470](../issue470/README.md) と同じ：RF-T010 effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、base RF-T008 rev3、固定S2P、seed 1013、25変数全物理bounds、Hybrid sum/sigma 0.1、Search 70点×1000、Terminal 476点×1、独立MNA `[0,111]`。有限grid上の開発診断であり、物理実装性や連続帯域を保証しない。

Linux WSL2、Ryzen 7 PRO 4750G、Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1。`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`、実thread数・CPU周波数固定は未確認。各モードplain warmup 1回後、plainとL1/L2 timed各3回（deepなし）。各系列の順序は off/lk/response/both、both/response/lk/off、lk/both/off/response。warmup・plain・timedの全28 runを記載し、選別していない。CLI wall/RSSは `/usr/bin/time`、Search RF・solver・jobは別runのinclusive timer。強制的なCPU隔離なし。例：

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
/usr/bin/time -f 'wall=%e rss_kb=%M exit=%x' uv run --frozen python scripts/run_rf_search.py develop \
  --config project/diagnostics/issue470/config.json --starts project/diagnostics/issue470/starts.json \
  --output /tmp/issue476-example --spot-checks '{"terminal":[0,111]}' --rf-cache-mode both
# timed runはfreshなoutputに加えて --timing-output /tmp/issue476-timing.json を指定。
```

## 時間・費用

秒、記載順は上記の各run番号順。CLIは起動等を含む。timedの各領域は包含関係があり合算できず、plainとの差は計器負荷だけを分離したものではない。RSSはプロセス最大値（KiB）。

| mode | warmup CLI | plain CLI 3回 | timed CLI 3回 | timed Search RF 3回 | timed solver 3回 | timed job 3回 | plain RSS 3回 KiB |
|---|---:|---|---|---|---|---|---|
| off | 1.55 | 1.54, 1.55, 1.49 | 1.63, 1.50, 1.51 | 0.5012, 0.4669, 0.4728 | 0.5784, 0.5430, 0.5459 | 0.9619, 0.9166, 0.9164 | 88772, 89168, 88652 |
| lk | 1.50 | 1.53, 1.46, 1.50 | 1.52, 1.57, 1.49 | 0.4464, 0.4950, 0.4370 | 0.5236, 0.5940, 0.5101 | 0.9477, 0.9703, 0.8806 | 88612, 88764, 88504 |
| response | 1.57 | 1.58, 1.68, 1.64 | 1.60, 1.67, 1.63 | 0.5649, 0.6185, 0.5523 | 0.6413, 0.7081, 0.6330 | 1.0278, 1.0785, 1.0123 | 89560, 89568, 89564 |
| both | 1.66 | 1.60, 1.61, 1.63 | 1.61, 1.58, 1.64 | 0.5297, 0.5195, 0.5706 | 0.6075, 0.5955, 0.6603 | 0.9841, 1.0014, 1.0562 | 90176, 89772, 89580 |

各timed runのカウンタは同一。L/kは1 evaluatorで容量16、応答は各設定16。実計算sampleはSearchの再計算数であり、課金sampleではない。

| mode | L/k lookup / hit / miss / matrices実計算 | 応答 lookup / hit / miss | 実計算sample |
|---|---|---|---:|
| off | 0 / 0 / 0 / 1000 | 0 / 0 / 0 | 70000 |
| lk | 1000 / 688 / 312 / 312 | 0 / 0 / 0 | 70000 |
| response | 0 / 0 / 0 / 1000 | 6000 / 2280 / 3720 | 43400 |
| both | 1000 / 688 / 312 / 312 | 6000 / 2280 / 3720 | 43400 |

別途、Search全出力ハッシュ計装runの終了時にキャッシュを調査：off/lk/response/bothで配列payload 0/8448/107520/115968 bytes、key payload 0/896/11520/12416 bytes、エントリ L/k 0/16/0/16・応答 0/0/96/96。Pythonオブジェクト・辞書・一時配列を含まない下限で、上表RSS差はprocess全体の粗い上限目安であり正確なキャッシュ増分ではない。

## 同値性・結果と判断

全28 runはexit 4、Search 1000 + Terminal 1 forward、requested 70476 samples、独立MNA 2点、`evaluation_budget_exhausted`・未収束、異常STOPなし。各runの科学output tree全6ファイルをSHA256で比較し、input/result/checkpoint/receipt/親台帳すべてbyte一致（`result.json` SHA256 `b987f9a49c1db64e476c047f11681ae30e6f5547c4c3c477c65472fc48aa6d0c`）。Terminalの全S/IL/APL/RL、Search objective 2599.687730726887、Terminal J 10.678979507384295、最終vector、local nfev 1000/nit 31/success false/status null、STOP、ledger/receiptも一致。Terminal gridの電力検査と独立MNA 2点はpass。

さらに別の各1 runでEvaluatorを一時計装し、**同一順序の全1000 Search forward**の複素S全4要素とIL/APL/両RLのbyte列連結SHA256が4モードとも `f46c7804dc8caa60cd24b9a75847025fefa42be8e6941119e5ef4d1bba3d1de5`。このhash計装runは速度比較に含めない。テストで6設定・28区間、partial HIT順序、キャッシュ隔離、非SPD・非有限入力、sample_indexと失敗非保存、容量、check_power迂回を確認。独立MNA等の既存回帰も別途実行。ただし全可能入力でのbit一致は証明していない。

plain中央値は off 1.54、lk 1.50、response 1.64、both 1.61秒。lkはこの3回では若干短いがばらつきと重なり、速度向上は未確定。response/bothはこの条件で遅く、HIT数から高速化は推論できない。BとCを加算してDとみなさない。**既定offを維持**し、lkは追加の独立測定後に採否判断、response/bothはこの実装・条件での採用を推奨しない。単一seed・短時間の実行であり他条件へ一般化しない。

開発中の初回計測 `c611bfcd` ではlkが全設定走査を行い遅かったため、その後 `0eacecb5` で走査を避けて全条件を上記のように再測定した。初回の全28 runも `/tmp/issue476-rf-cache-fNlaEA/`、最終測定と全出力・hash計装コードは `/tmp/issue476-rf-cache-final-PnMROG/` に保持（system tmp、永続保証なし）。正式研究証拠ではない。
