# Issue #394 物理検査経路の実RF A/B（限定開発診断）

ユーザーが旧新各3回、最大600 forward／42,000 samplesを承認。[実行前固定](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/400#issuecomment-6809687068)に従い、**600 forward／42,000 requested samples**を実施。追加の末尾RF forward、独立MNA、dense、正式Campaign、新EXPは実施していない。評価器は実RFモデルだが、MinimalWorkerにはJob費用台帳・復旧はない。費用はsolver `nfev` と1 forwardあたり70 samplesから算出（plain経路にforward以外のRF評価はない）。

## 条件

- 旧: main `6ac982306cd5899dee99b40dee660d3a6986db89`、source identity SHA `137ccfa590a1184bf6fa1852625b44668afa19d0a2926f3a16f8a01c56063cc0`。新: PR #400 `81f5d712f5f94e0e9becb84a27f355a31f072d8a`、source identity SHA `e99b4de34f61be98414a4e7aa24ef6b5b7d2ff3747721e5d5e3c2eb5a7bf72a1`。対象実行sourceのdirty patchは両方空。新revisionは結果記録コミットより前の実行コード。
- RF-T008 rev3 **trial opt-in**, full_lpf、effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。6設定・28別区間、固定S2P。Plan SHA `8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e`、70点grid SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`。
- bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、入力S2P `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、出力S2P `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。
- seed 1002、原本vector SHA `6203467121a4e37baaa51c471aaecb3174f3374f9ab955d6fbf101f7b5ce935f`、starts byte SHA `63b671ea269656843df118230b7d920e91515188235809b6dd0efd667ac997ab`。Hybrid sum、max_evaluations 100、max_restarts 0、maxiter 300。
- 共通 `project/diagnostics/issue391_benchmark.py` plain mode、script SHA `4eaf700b764a02e228e2ed6ce8562bd005f488cbda7e09401ca414371674d428`。BLAS/OMP/MKL各1 thread、Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1。別processを旧→新→新→旧→旧→新の順で実行。単独process内でsetupとsolverを測定し、各forwardの時計取得・記録は行わない。setupはsource identity取得を含み、totalはsetup＋solver。計測器自身の費用は別途測定していない。

## 観測（秒）

| 順 | 版 | setup wall | solver wall | total wall | solver CPU |
|---:|---|---:|---:|---:|---:|
| 1 | 旧 | 0.306629 | 0.175820 | 0.482448 | 0.175787 |
| 2 | 新 | 0.310946 | 0.138130 | 0.449076 | 0.138133 |
| 3 | 新 | 0.260874 | 0.101765 | 0.362639 | 0.101764 |
| 4 | 旧 | 0.322152 | 0.207030 | 0.529182 | 0.207004 |
| 5 | 旧 | 0.328514 | 0.230381 | 0.558895 | 0.230332 |
| 6 | 新 | 0.286437 | 0.142365 | 0.428802 | 0.142286 |
| 中央値 | 旧 | 0.322152 | 0.207030 | 0.529182 | 0.207004 |
| 中央値 | 新 | 0.286437 | 0.138130 | 0.428802 | 0.138133 |

この6 runの中央値に限るとsolver wallは約33.3%、total wallは約19.0%短い。各群3回と少なく、共有環境・cache・CPU負荷・周波数は制御していないため、一般的な改善率や信頼区間とは扱わない。#393のrequirements最適化の効果と混同しない。測定対象は**MinimalWorker**であり、window100や保存付きJobの高速化を実測したものではない。

6 runともsolver全出力は完全一致：nfev 100、`evaluation_budget_exhausted`、未収束、best objective `27088.776754855604`。各forwardのvector・RF応答・requirements系列は今回記録していないので、その系列の一致はこの測定から主張しない。独立MNA、dense／連続周波数、物理Q(f)/SRF/EM、公差、実測、実装可能性は未検証。RF性能合格や探索の最適性を意味しない。

## 原記録

各JSONは実行順、revision、コマンド、終了コード、stderr、benchmark標準出力を保存する。標準出力内に完全source identity・solver出力・環境・RF入力SHAがある。write後にSHA確認。

| ファイル | SHA256 |
|---|---|
| [01-old.json](01-old.json) | `61ea26f97311c606cc271dcf3299a2e1c56bc3a5b7343ff5c9469504580650b5` |
| [02-new.json](02-new.json) | `ec26b02dbd697efbf62a39c073c3ccbdf9c0624c3b50b174bd30f9556e2a06f6` |
| [03-new.json](03-new.json) | `6f82746ad2926709a3fb6934fe896c45d281495869dc8d46cb816fe45786f441` |
| [04-old.json](04-old.json) | `f28011dc1e365882aea1acdaa12f6a0b928b397a5c717dbb1f8f11e5de0c900e` |
| [05-old.json](05-old.json) | `aa818ebc8758e5da449b7cb0f4a190db81147f3652682dd164c0087106586958` |
| [06-new.json](06-new.json) | `f36000b1fa221562d288a8e1ecd66645347e02f2e0de15f5db34c1d347a82332` |

旧版用 `/tmp/issue394-baseline-6ac9823` worktreeは出力・研究データがないことを確認し、生成されたPython bytecodeのみを削除した後、worktreeを正常に削除した。新コード側の既存未追跡 `.issue361-definition.json` は変更していない。
