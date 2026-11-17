# Issue #446：限定開発A/B（2026-11-17 UTC）

**用途はソフトウェアの同条件診断であり、RF適合・最適性・実装可能性の結論ではない。** 正式EXPや新候補探索は行っていない。RF-T008の旧weighted開発経路で、旧mainと新実装の動作・CPU時間・保存サイズを比較した。RF-T009との直接比較ではない。

- A: `6b68580851748df14c0b7d87b28c6f4e58d4be9e`、B: `dbdd9262a887152166daaa5a4e6ea8b1dfce60de`。両者とも同一Python実行環境、計測対象ソース差分なし。Bの文書のみ作業途中であり、source identityはコードの変更なしを記録。
- RF-T008 effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、Plan SHA `3c7a4b1bee3596f109eed0add120bb7a5da3aefcec9f500f9172a2bdae54d73d`、seed 23、開始vector SHA `bedc3233fdf1af8052b56e00f4693b18561f456323942f902e318ac533ee6da4`。入力config SHA `5563c964e3d93af1c75f1e7c4f685f1b6f2e94658e0a0149ba8db60a4f23276f`、starts SHA `ced80fdb77b5dfd9c74723a0b035a2f813479f60530f0207fdedbf41676c0acb`。
- bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、入力S2P SHA `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、出力S2P SHA `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。Planの`data/...`は旧論理パス、現行実体は`rf/...`。
- Hybrid/sum、`J=max(0, worst_pass_IL−0.30)^2 + 100×mean(max(0, 30.01−harmonic attenuation)^2)`、各runのSearch上限10 forward、Search 70点／forward（grid SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`）、Terminal 476点（SHA `28ee5b630e4842b183a7c36fd610cc32e2509c0044c6a5848ce2fbd147a22e29`）、独立MNA spot `[0,111]`。各runでSearch 10 forward／700 requested samples、Terminal 1 forward／476 samples、独立MNA 2 samples。全8 run合計 Search 80 forward、Terminal 8 forward、独立MNA 16 samples。
- 無計時のplain CLIプロセス全体を `/usr/bin/time` で測定。Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、Linux WSL2 x86_64、AMD Ryzen 7 PRO 4750G、OpenBLAS/OMP/MKL各1 thread。プロセス起動・source hashing・Terminal・spot・保存を含むため、solver単独のCPU時間ではない。A/B各1回warmupを除外、測定順 `A B / B A / A B`、各3回。全run終了コード4（予算終了、数値収束ではない）。

|  | CPU user+system 秒 | wall 秒 | 保存ファイル総バイト（ディレクトリ自体除外） |
|---|---|---|---|
| A | 1.34, 1.29, 1.33（中央値1.33） | 1.40, 1.36, 1.39 | 各202,033 |
| B | 1.37, 1.53, 1.38（中央値1.38） | 1.43, 1.59, 1.43 | 各201,770 |

Bの2回目に外れ値があり、標本数・時計分解能・外乱から改善／悪化率は断定できない。保存量差は結果schemaの変更を含み、同一証拠量での圧縮率を意味しない。8 runすべてでPlan・RF SHA・Search counts・最終vector SHA・目的値・Terminal assessmentと独立spot結果が完全一致した。Terminal strict FAIL、未収束であり、この値からRF性能を主張しない。

入力、標準出力、時刻ログ、各runのcheckpoint／結果原本は `/tmp/rf-lpf-issue446-ab/` に保持中（system tmpは永続保存保証なし）。一時baseline worktreeは使用後に状態を確認して除去。正式なG0〜G5証拠には使用しない。
