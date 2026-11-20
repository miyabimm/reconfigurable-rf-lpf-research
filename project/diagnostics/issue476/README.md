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

## 追加指示：キャッシュdeep内訳と改善A/B

同じ入力・環境・RF条件で測定。旧PRの処理にdeep計時・分布カウンタを追加した基準 `d9eb7f53a405ca7766db7cfda265dedce425dda5`、全MISSの再組立省略のみのA `05fdb59caf509722e1a1f6326689909c039f2d36`、さらに設定別整数indexを再利用したB `babfca696e9cf83b6c3d504c69da26148def04f1`。基準は計測用にMISS収集ループを整理しており、PR元HEAD `7d7a3fd3` と完全に同じ命令列ではない。元HEADの無計時結果は上記を参照。3 HEADとも同一の25変数と1000 Search forward、1 Terminal、MNA 2点、exit 4・未収束。測定用commitはクリーンtree、科学rawのsource identityも各HEADを記録。

各HEADでwarmup各1、plain・timed・deep各3回の40 CLI run、各系列は前節と同じ順序交互化。3系列の比較は `taskset -c 3` でCPU affinityを指定したが、CPU周波数固定・他processの干渉排除はしていない。コマンドは上記CLI例に `taskset -c 3` を付け、timedは `--timing-output`、deepはさらに `--timing-level deep` を付ける。基準・Aではaffinityなしでも同じ各40 runを先行実施し、後述の一時ディレクトリに全値を保持する。timed/deepの計時はinclusive、欠測区間は0とは限らない。特に `missing_compute` は既存RF子区間を包含し、子と合算しない。計時call自体の時間、deepでの多数の追加callによる負荷を含み、plain比較にdeep時間を用いない。

### CLI全runとRF・メモリ

秒はrun番号順、RSSはKiB（process全体の最大RSS）。RFは別のtimed runにおけるSearch累積wallで、plainの内部時間ではない。各系列はwarmupを集計から除外。各セルの3値は全実測であり外れ値を除外していない。

| HEAD | mode | warmup CLI | plain CLI 3回 | timed CLI 3回 | timed Search RF 3回 | plain RSS 3回 |
|---|---|---:|---|---|---|---|
| 基準 | off | 1.68 | 1.76, 1.75, 1.54 | 1.61, 1.78, 1.64 | .4729, .5609, .4934 | 88788, 88816, 88640 |
| 基準 | lk | 1.53 | 1.85, 1.56, 1.56 | 1.73, 1.69, 1.56 | .4920, .4942, .4427 | 88876, 88592, 89152 |
| 基準 | response | 1.79 | 1.70, 1.71, 1.78 | 1.68, 1.70, 1.85 | .6045, .5739, .6286 | 89440, 89560, 89644 |
| 基準 | both | 1.60 | 1.74, 1.64, 1.82 | 1.75, 1.76, 1.66 | .6272, .5271, .5770 | 89728, 89732, 89476 |
| A | off | 1.63 | 1.58, 1.69, 1.56 | 1.71, 1.61, 1.70 | .4892, .5253, .4753 | 88796, 88888, 88716 |
| A | lk | 1.66 | 1.56, 1.56, 1.66 | 1.59, 1.73, 1.53 | .4986, .4786, .4407 | 88844, 88720, 88944 |
| A | response | 1.68 | 1.68, 1.79, 1.69 | 1.75, 1.72, 1.72 | .5483, .5456, .6050 | 89540, 89572, 89624 |
| A | both | 1.74 | 1.73, 1.68, 1.67 | 1.66, 1.75, 1.66 | .5273, .5280, .5313 | 90096, 89604, 89580 |
| B | off | 1.62 | 1.70, 1.66, 1.70 | 1.60, 1.80, 1.67 | .4584, .5303, .5193 | 88836, 88804, 88816 |
| B | lk | 1.56 | 1.70, 1.52, 1.58 | 1.73, 1.58, 1.60 | .4824, .4882, .4513 | 88860, 89224, 88812 |
| B | response | 1.83 | 1.67, 1.76, 1.77 | 1.69, 1.78, 1.70 | .5764, .5414, .5948 | 89668, 89712, 89636 |
| B | both | 1.64 | 1.71, 1.73, 1.78 | 1.65, 1.66, 1.67 | .5084, .5704, .4974 | 89152, 89616, 89608 |

baselineおよびAのaffinityなし実測plain CLI（3回）も全記録：基準 off 1.74/1.60/1.73、lk 1.62/1.65/1.67、response 1.81/1.72/1.71、both 1.71/1.72/1.64；A off 1.83/1.63/1.71、lk 1.51/1.77/1.65、response 1.70/1.67/1.65、both 1.65/1.70/1.60。各warmup・timed・deepを含む全40+40 runは下記analysisに保持。

### Deep内訳・HIT分布

以下ms、3回全値。キャッシュなしoffにcache区間はない。lkでは検索3.1–3.5、計算375.2–446.1、保存1.5–2.1 msで、設定別抽出・再配置はない（基準とB、6 runの範囲）。各RF/computeは異なる計測runのinclusive時間。deep Search RFの範囲は基準off 560.6–578.2、lk 488.3–585.7、response 655.5–688.4、both 585.2–595.9 ms、Bはそれぞれ513.0–578.4、506.3–556.2、602.4–656.4、556.4–579.3 ms。深い計時はplainに対し計器負荷や実行環境差が混入する。

| HEAD・mode | L/k key/lookup | 応答lookup | MISS選択 | MISS計算 | 保存 | 再配置 |
|---|---|---|---|---|---|---|
| 基準 response | 2.5/2.5/2.5 | 8.7/9.4/9.1 | 12.3/13.2/13.5 | 433.4/449.4/454.4 | 62.3/65.0/67.9 | 39.6/38.0/38.0 |
| 基準 both | 2.9/3.1/3.0 | 8.6/8.8/8.5 | 12.3/12.1/12.2 | 354.8/357.1/358.6 | 61.4/62.6/64.0 | 35.0/35.5/37.5 |
| A response | 2.4/2.8/2.7 | 8.6/9.0/9.9 | 12.2/13.5/14.0 | 423.2/454.2/478.4 | 62.8/67.3/71.9 | 16.5/18.2/17.5 |
| A both | 3.0/2.9/3.1 | 8.9/8.8/8.6 | 12.6/12.0/12.1 | 364.8/356.7/360.2 | 63.2/62.5/62.8 | 16.7/16.5/16.7 |
| B response | 2.3/2.6/2.6 | 8.8/12.8/9.2 | 12.2/13.2/13.3 | 420.7/456.4/451.9 | 54.8/59.4/59.0 | 9.4/10.6/10.2 |
| B both | 2.9/3.1/3.1 | 8.6/9.1/8.5 | 12.1/12.5/12.3 | 357.5/373.9/358.0 | 55.2/56.9/55.4 | 9.1/10.0/9.1 |

C/Dの分布は全測定同一：全MISS 544 forward（54.4%、38080 samples）、部分HIT 456（45.6%、5320 samples）、全HIT 0（0%、0 samples）。応答lookup 6000、HIT 2280、MISS 3720、実計算43400 samples。B/DのL/kはlookup 1000、HIT 688、MISS/実計算312。A/offは計算70000 samples、L/k実計算1000。各設定が存在しないgridでは**存在する設定数**を分母に全MISS/部分/全HITを判定する。失敗時のsample数はfallbackを含む実計算試行数で、課金とは別。

検索は比較的小さく、実RF計算が最大、保存・再配置も無視できない。全MISSの多さからAは再配置のdeep時間を短縮、Bは整数indexの実測で保存・再配置が更に短縮した。ただし同一区間の計時値は計測器負荷込みであり、削減分をCLI改善量とみなせない。

### plain RF再生・採否と科学同値性

CLIのばらつきが大きいため、別に元のSearchで生成された全1000 vectorを順に再生。各process内でmode順序を6通り交互化、各modeの最初をwarmupとして除く。各HEADを **基準→A→A→基準**、**A→B→B→A** の順に切り替え、各2 process×5測定、`taskset -c 3`。RF evaluatorのみを無計時で一括wall測定し、全出力のhashは計時後に計算。下は10回中央値（範囲）、秒。RFだけの再生でありCLI全体速度ではない。

| 比較 | off | lk | response | both |
|---|---|---|---|---|
| 基準（A比較） | .4650 (.4566–.5161) | .4302 (.4267–.4841) | .5739 (.5520–.6365) | .5805 (.5224–.7618) |
| A（基準比較） | .4625 (.4504–.5175) | .4335 (.4192–.4865) | .5617 (.5303–.6018) | .5074 (.4894–.5576) |
| A（B比較） | .4697 (.4541–.5295) | .4306 (.4214–.4976) | .5535 (.5328–.6046) | .5125 (.4962–.6179) |
| B（A比較） | .4828 (.4517–.5391) | .4271 (.4199–.4899) | .5259 (.5127–.5869) | .4926 (.4777–.5517) |

範囲は重なり外れ値もあるが、A/Bともplain RF再生のresponse/bothで比較対象の2 process各中央値を下回り、deepで対応する処理の短縮も観測したため、最小変更としてA・Bを採用する。**CLI全体の高速化は確認できない**（上のplain値はばらつきが大きく、Bが遅い場合もある）。他モードへの一般化や既定変更はしない。残る保存の中間コピー削減Cは、所有権・不変性を保った直接書込みが追加の複雑さを伴い、現データでCLI改善を見込めないため実装しない。

各HEADで40 runの全科学output treeがモード・計時level間でbyte一致し、全200 runのreceipt登録ファイル長・SHAを再検証。異なるHEAD間はsource/head/SHAが意図的に異なり、receipt byte一致は期待しない。`result.json` はsourceとそのSHAを除けば旧PR測定HEADを含め一致。別計装の各再生で全1000 Search forwardの全S/IL/APL/両RL byte連結hashは、基準・A・Bの全modeで `f46c7804dc8caa60cd24b9a75847025fefa42be8e6941119e5ef4d1bba3d1de5`。Search objective・最終vector・Terminal J・局所状態・forward予算/ledgerは前節と同じ、Terminalの受動性・電力保存・独立MNA 2点pass。追加回帰で全modeの非SPD・非有限・注入したY/S特異行列STOP、partial HITの元sample_index、失敗非保存、非連続/欠設定grid、配列不変性とdeep外での時計非呼出しを検査。有限grid・1 seed・注入故障等の限界は残る。

全200 CLI runのstdout/stderr・raw・計時JSON・分析、追加の非affinity RF再生と上述のaffinity RF再生の全値・再生scriptは `/tmp/issue476-cache-deep-ripRlB/` に保持（system tmp、永続保証なし）。正式EXPではない。
