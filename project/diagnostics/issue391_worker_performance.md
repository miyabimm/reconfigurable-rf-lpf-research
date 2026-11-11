# Issue #391：最小Workerの時間内訳（開発専用）

## 条件・境界

マージ後main `5ac616f72af527ff4f20c93ba1fc7dd56c916ca7`（PR #390）を起点とし、`src/`等の対象実行コードに差分なし。計測スクリプトは当時未追跡、別SHA `4eaf700b764a02e228e2ed6ce8562bd005f488cbda7e09401ca414371674d428`。[再現コード](issue391_benchmark.py)はsource_identityと自身のSHAをsetup内・solver外で取得する。source identity canonical SHA `ca1a17fa5b66f15cc7ba2e120b1c53c78c0c74724abfa6bf75340d98f7559913`。これは開始時取得であって外部固定SHAとの事前照合や途中変更監視ではない。各processのidentityは一致。

RF-T008 rev3 **trial opt-in** effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、full_lpf、6設定・28独立帯域/H2/H3・固定S2P。Plan SHA `8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e`、search 70 samples/grid SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`。bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、S2P input/output SHA `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945` / `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。#389と同じdefinition/config、seed1002原本vector SHA `6203467121a4e37baaa51c471aaecb3174f3374f9ab955d6fbf101f7b5ce935f` を**RF実行前**に実照合、startsファイルSHA `63b671ea269656843df118230b7d920e91515188235809b6dd0efd667ac997ab`。Hybrid max 100 / restart 0。

Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、Linux WSL2 6.18.58.1、Ryzen 7 PRO 4750G。OPENBLAS/OMP/MKL各1 thread。共有負荷・cacheは非制御。独立processで以下を3回plain、1回timed、1回profile（順序固定）：

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src \
 .venv/bin/python project/diagnostics/issue391_benchmark.py \
 --starts /home/user/issue377-rf-profile-20261110/inputs/starts-1002.json --mode plain
# --mode timed / profile も同様。各process最大100 forwards。
```

計500 solver forwards / 35,000 samples、追加診断forward 0。次回実行は別の計算消費。原本vectorがない/異なる場合STOP。RF-F003は不変更。#389の修正前0.270550 sは別HEADの1回であり改善率を算出しない。

## 実測（秒）

| 観測 | setup wall / CPU | solver wall / CPU |
|---|---:|---:|
| plain 1 | 0.295172 / 0.258775 | 0.256984 / 0.256634 |
| plain 2 | 0.238219 / 0.233111 | 0.257408 / 0.257194 |
| plain 3 | 0.257676 / 0.249649 | 0.270284 / 0.268608 |
| plain 中央値（範囲） | 0.257676 (0.238219–0.295172) / 0.249649 | 0.257408 (0.256984–0.270284) / 0.257194 |
| timed | 0.254043 / 0.246592 | 0.251084 / 0.249640 |
| cProfile | 0.248696 / 0.242421 | 0.346371 / 0.344882 |

setupにはsource/script hash、preflight、model、grid/S2P準備を含むがPython importは含まない。timedはwallとprocess CPUの時計・wrapperを各領域で呼ぶ。plainとの差は負荷変動を含み、今回timedが速いためオーバーヘッドを差分から推定できない。cProfileは別観測でplain中央値より約35%長く、CPU内訳をそのままplainに適用しない。

詳細計時（1回、各100呼出、wall / process CPU秒）：physical `0.050532 / 0.050410`、RF `0.080692 / 0.080448`、requirements `0.105035 / 0.104686`、evaluate包含 `0.238329 / 0.236968`、residual包含 `0.242102 / 0.240689`。残差整形等は包含差 `0.003773 / 0.003722`、solver内のresidual外は差 `0.008982 / 0.008951`（計測器も含む）。前者3項は別領域だがwrapper費用を含み、包含領域とは加算不可。順位はrequirements > RF > physical。1回の内訳で不確かさがある。

別のcProfile観測ではrequirements累積0.148320秒（自己0.082987）、RF 0.105265、physical 0.072083。RF内 `port_admittance` 0.048293、`node_admittance` 0.037175（包含）。NumPy行列演算はサンプル一括処理だが、native BLAS対その他の比率はcProfileで分離できず**未測定**。wallとCPUはほぼ一致するがBLAS比率の証拠ではない。

## 候補と下限の推定

1. requirements：要求格子と応答格子の毎回fingerprint、区間ごとのindex生成、sample/行のtuple/dict詳細構築を確認。候補依存の複素応答/数値異常、各区間・全要求・残差、厳密判定は維持し、固定gridの一度の照合とsolver用詳細出力の分離が候補。
2. physical：毎回physical bounds・固定role監査・policy fingerprintを再計算する。固定部分の前計算は候補だが、候補ごとの全値域・全設定・coupling/SPD検査は必須。

RFは2番目に大きいが、`RFEvaluator`は固定S2Pをsetup済みで、毎回`resolved_policy`をJSON展開し、トポロジー内で固定配列も再準備する。JSON単独寄与や配列再準備単独寄与は未分離。高速化効果は未実証。

**A/B試作は未実施**：詳細requirementsは公開される完全な応答・行情報と網羅性/異常STOPを持ち、単純省略やgrid fingerprintの無条件cacheでは契約を満たすと確認できない。固定/可変境界と異常注入を含む比較を本短時間診断内で正当に構成できなかったため、性能比や同等性を主張しない。既存API/科学条件は未変更。

参考として、timed内requirements全体を非現実的にゼロにできた場合の単純差は `0.251084 - 0.105035 = 0.146049 s/100`、physical全体もゼロなら約 `0.095517 s/100`。これは同一実行内の算術上の楽観的下限**推定**であり、必須検査・計測器・交互作用のため達成可能な速度ではない。RF計算そのものも残る。

## 結果の同等性と限界

5回は元の同じコード経路で、solver結果の全フィールド（best_x、best_fun、runs、nfev、終了理由）が完全一致。best vector SHA `6c3480628c8676654f8f63775e3566c69aed34f3f06689a85447a0cd33635bbe`、best objective `27088.776754855604`、nfev 100、nit 1、`evaluation_budget_exhausted`・未収束。timed wrapperは呼出値を変更しないが、各forwardのrequirements/residualを記録していないため、それらの個別比較は未実施。試作の科学/数値同等性は未検証。元経路は候補検査とRF/requirementsを通常実行、固定S2Pも使用；この診断は独立MNA・dense・連続帯域・候補固有の受動性/電力保存の独立検証、Q(f)/SRF/EM・公差・実測・実装可能性を確認していない。有限格子の性能保証・RF認定ではない。

`py_compile` PASS、#389 SourceBoundaryTests（no-RF）2件PASS。新EXP、正式Campaign、大規模探索、3000評価/100 restart、dense、EM/実測はnot_run。正式経路採用は別Issue・独立レビューが必要。

生JSONはローカル `/tmp/issue391-worker-diagnostic/` に残存、外部永続保全未確認。`0-plain`〜`4-profile` のSHA256は順に `48d4e061d85619e06e7c05925317636308c1f43142ae76ad6354d1da5333f78f`、`cf7376161681cfba43cd74d1b53726be998185f72c4a5197797d9c012f2c74a4`、`14ef4f16142cd54e1741a6f2a7db8c9a341aee2597cfdb92c03ffd6a833d8a71`、`6abe8ebfc8f51bad0fbf6f9eb6b70ec34bfe8c447f0837c682a6404534189758`、`87e2ff5156e83d8a18b964a71d60d942ce083f7c7229acff098e6e09ed31497d`。重要な要約は上記に記載。
