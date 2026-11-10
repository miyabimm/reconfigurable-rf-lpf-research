# Issue #377：window100の限定プロファイルと高速化

## 結論・判定

#377のユーザー判断（2026-11-10）とPR #380レビューに従い、#369の**開始・窓／状態境界でのsource/RF入力照合**を維持し、毎forwardのsource/import-origin再照合は追加しない。各forwardの合法性・SPD・RF/requirements・費用上限、および窓の事前atomic予約、境界でのfsync/readback、unknown費用の保守的扱いは維持。ファイルsource SHAとPython import-originの保証は別物であり、各forward import-origin検証は行っていない。

限定改修後、同じseed1002の3,000 search forwardを含む**局所探索1回は77.445秒wall／76.500秒process CPU**、nfev 3,000、nit 80、評価上限によりsolver未収束（exit 4）。**60秒・20秒はともに未達**。Job全体は監視wall 86.333秒、最終観測process-tree CPU 84.06秒、観測peak RSS 143,097,856 bytes。局所runとJob全体は別、RSSはサンプリングpeak、CPUは終了した短命子を欠く可能性がある。これは単一条件・1回の観測であり大域最適性を示さない。

同じ固定入力による変更前後の短時間実RF比較で、保存されたselection 2件とterminal 1件の**全Sパラメータ、IL/APL/RL、requirements全体・mandatory g、物理/SPD、solver結果と費用経路はcanonical JSONで完全一致**。各件は全6設定・28個別区間を含む。独立MNAは別のテストで6点のみPASS（後述）。それ以外の全帯域独立MNA、dense、連続周波数、Q(f)・SRF・EM・公差・実測・物理実装性は未検証。PRはDraftでありChatGPT独立レビュー待ち。CI PASSと科学的認定は別である。

## 条件・予算・原本

- `main` base `9b0a83cf5411a283740114170269fbf7effcdd3e`。実RF実行source HEAD `f8b01a5bb04f1f706b59356facaca3be272fb492`、source identity SHA `f59cd811a7bf7d2dc8173210abeb5e08d044e36103b1a945040e0432ca08a7a4`。baseline sourceはmain、identity SHA `fcbfc45411e3502f780ed68e73920e953daf064c550d8d6e63962c14084a4adb`。
- RF-T008 rev3 **trial**明示opt-in、effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、full_lpf、6設定・28不連続区間、固定S2P。正式active RF-F003は不変。25変数start seed1002 SHA `6203467121a4e37baaa51c471aaecb3174f3374f9ab955d6fbf101f7b5ce935f`。search 70 samples/grid SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`。selection/anytime 84、terminal 476 samples。
- Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、BLAS/OMP/MKL各1 thread、Ryzen 7 PRO 4750G、WSL2。共有負荷・filesystem cache非制御。前後100-forward比較の監視設定とcProfile hookは同じ、実行日時とsource HEADは異なる。
- 研究Job総上限250,000 samples。再開preflight SHA `6662e93e6a50d7f5669219130b1ddda6b7216a94f6c9826eaeb40ba276a1cede`、benchmark起動前の確定済み15,288＋benchmark Job cap 212,000＝**最大227,288**を確認。benchmark Plan SHA `27ebae32d650820e8f074b39a44f24d0b8cbea612a2bf59fc613cc9bc228e19c`。short Plan SHA `8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e`。

| 研究Job | search | selection | anytime | terminal | requested = completed | reserved / unknown |
|---|---:|---:|---:|---:|---:|---:|
| 変更前短時間 | 7,000 | 168 | 0 | 476 | 7,644 | 0 / 0 |
| 変更後短時間 | 7,000 | 168 | 0 | 476 | 7,644 | 0 / 0 |
| 変更後3,000評価 | 210,000 | 168 | 252 | 476 | 210,896 | 0 / 0 |
| **合計** | | | | | **226,184** | **0 / 0** |

Job内independent spot・denseはnot_run・0。2026-11-10ユーザー判断によりCI・ローカル単体/回帰/独立MNAテストは上記の研究Job上限対象外だが、未計測分を0とは扱わない。PR作成時に自動起動した[CI 42722071175](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/42722071175)は実RF/MNAテスト実行後cancelled、sample数は未計測。後続の[CI 42819846885](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/42819846885)はHEAD `7a93a8c` でPASS、RF/MNAテスト費用は別枠・未計測。これを予算対象に含めた旧停止判定は**ユーザー判断で訂正**された。旧#361 unknown予約・#372/#375 rawは変更・相殺しない。

永続raw・監視・preflight・監査は `/home/user/issue377-rf-profile-20261110/`。全40ファイルのbyte/SHA読戻しmanifest `resume-manifest.json` SHA `9b1d6d38c2d53f742cdc7e4038d755c3455917b77a504edee9225e48e927d6e8`、manifest自体もatomic readback済。benchmark parent SHA `1ca5f299ec7c559b9501a1dc6112454c4f0aac1f344d998be186124213f5c172`、worker `f92fc2b89ee2e819b0732b5257e96eff3518694e771aca08c2d79938f5e28d9b`、summary `de6214f3eaf66316c2604b64fbe71979ecabcb999e817e6d4632b924964eec16`。Git外ローカルであり外部バックアップは未検証。

## 実時間プロファイル：短時間比較

#378共通監視1秒周期＋科学子プロセスに同じ`cProfile` hook。py-spyは未インストール、実sampleなし。表は**inclusive時間**で親子・再帰の重複を含み、計測オーバーヘッドも大きい。加算・非計測実Jobへの外挿は不可。SPDは`validate_values`内包。実forwardだけのwall分離ではなくJob中の呼出し合計。

| 区間（回数/Job） | 変更前 秒 | 変更後 秒 |
|---|---:|---:|
| 監視Job wall（100 search、selection/terminal含む） | 39.461 | 19.200 |
| `_save`（20、contract/snapshot/atomicを内包） | 30.316 | 12.685 |
| window `snapshot`（20） | 18.453 | 7.041 |
| `plain`（再帰含む18,235,240 calls） | 26.835 | 7.552 |
| `_contract`（21、sourceを内包） | 8.592 | 4.280 |
| `source_identity`（23） | 0.514 | 0.423 |
| `atomic_verified`（24、JSON/fsync/readbackを内包） | 4.230 | 1.744 |
| `validate_values`（113、準備時を含む） | 0.378 | 0.333 |
| RF evaluator（103） | 0.154 | 0.134 |
| requirements（103） | 0.187 | 0.175 |
| SciPy `_dense_difference`（4） | 3.542 | 2.611 |

100 search residualのうち97回はSciPy有限差分callback内、残りをline searchだけと断定できない。変更前の局所run eventはWorkerの`json`スコープ不具合により**欠測**、変更後はevent wall/CPU 2.709/2.691秒、nfev 100/nit 1で科学rawと照合。共にcProfile込みで、計測器オーバーヘッドの実RF無計測比較は未実施。修正前後のwall差は環境変動・計測効果を含み、そのまま通常Jobの速度向上率としない。#367のlegacy保存profileは現行window100とは別。

#378の監視オーバーヘッドは別の整数演算合成負荷で各1回実施：監視なし起動wall 2.762秒、監視あり2.663秒、py-spy試行あり2.968秒（未インストール）。固定順・変動を含むため差は因果推定でもRFへの外挿でもない。有効なpy-spy／cProfileの実取得時オーバーヘッドは未検証。

## 改修・RF一致・独立確認

- `storage.plain` は実profileで多重呼出しが目立ったため、組込みJSON scalarの**exact type**だけ既存の同じ値を返す。subclass、dataclass、NumPyは従来処理。旧checkpoint payload単体を再変換した固定順4回比較はwall中央値約0.342→0.213秒、同一byte SHA。これは実Job倍率を示さない。
- Worker末尾のローカル`import json`がHybrid event callbackを未初期化参照にし、監視例外が握り潰される欠陥を修正。無RF回帰で修正前RED／後GREEN、変更後の実Job eventも科学rawと照合。イベントstatusは常に`unverified`であり、1 start/endの一致自体を全件保証としない。
- 変更前後の各selection/terminalは完全vector・全response・全assessment・physical_checks・grid・ソルバー・選抜・費用進捗がcanonical JSON一致。独立した計算ではないため、この確認だけでRFモデルの正しさは証明しない。比較詳細 `inputs/short-comparison.json` SHA `d7d38a07509a5024184e50e92f06d362bd74ce26a7c5413dea1bdc16291230a1`。変更前後ともcomponent policy PASS、短時間terminalの全L最小固有値 `3.9306819299763447e-10 H`。
- 別の**独立MNA回帰テスト**として、変更後短時間terminalの保存S/IL/APL/RLを6設定各1点、UL/DL/H2/H3を含む計6点で独立再計算。SとdB各値の絶対誤差<=1e-9、内部passivity・power balance検査PASS。最大数値誤差 `4.14e-13`、最大|power residual| `7.62e-18 W`。これは6点限定で28区間全域や連続帯域の保証ではない。テスト費用は研究Job外の独立6 samples、結果SHA `cb059036d2e880207a8a510c7efc6f5dfec0caa7c64caf1c84a4d205764af005`。実行コード・unknown→完了読戻しは外部inputsに保存。
- ローカル `test_issue377_plain`、`test_issue369_forward_window`、`test_issue378_monitor`、workerのmonitor/window/mock・boundary、fixed-stage source交換・保存失敗STOP計 **26件PASS**。最後2件等のテストRF費用は別枠・未計測。失敗後に暗黙再試行しない既存経路を確認。

## 3,000-eval結果・比較・今後

`max_evaluations=3000, max_restarts=0, maxiter=300` の単一Jobを1回のみ実行。監視は同じ1秒＋py-spy要求（未インストール）だが、100-forward profileとは異なり内部cProfile**なし**。イベント1 start/endのnfev/nit/終了理由と科学workerを照合、monitor summaryには `optimizer_event_status=unverified`、errorsなし。局所run時間は途中anytime・checkpointを含み、Job全体時間とは別。終了時候補の17点/区間 finite-grid値はIL 7.649545629 dB、最小H2 21.873508788 dB、最小H3 19.555109576 dB、strict FAIL、全L最小固有値 `3.55946562700974e-10 H`。数値非収束であり不可能性の証明ではない。

#372のseed1002原worker SHA `ee8fcfc6177172c8d35c90bc6b558565b49796eabba19463656ec2da193b1782` を実byte照合し、1,000/2,000/3,000 anytimeのvector、全response、全assessment、physical checksは完全一致。#372のseed別wall約121.78秒は1秒間隔の親ledgerからのJob概算、今回の77.445秒local-runとは粒度・HEAD・監視が異なり速度比は直接比較不可。#375の236.71秒は6,500評価・2 local runsを含むJob全体であり同様に比較不可。

次案として有限差分・感度/ジャンプ設計を提案対象に留める。勾配・SciPyアルゴリズム・restart生成法の変更、100-restart実探索、Main/Extension、正式EXP、Phase 3はいずれも**not_run**。連続周波数・物理実装性や大域最適性を主張しない。

作業worktree `/home/user/src/reconfigurable-rf-lpf-issue377` はDraft PR用に保持。短時間用hook `/tmp/issue377-resume-hook/` は再開時に作成し保持（過去の `/tmp/issue377-profile-hook-1000-1484683/` は再開時に既に存在せず、hook原本は上記Git外inputsに保存）。
