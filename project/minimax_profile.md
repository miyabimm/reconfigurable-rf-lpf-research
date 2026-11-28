# 試験minimax profile（Issue #450、#458）

RF-T009 は正式 RF-F003 とは独立した **明示opt-in試験条件**。schema 1 `rf_performance_profile` は旧schema 2 trial overrideではなく、`load_constraint`／正式Campaign に渡せない。正式自動昇格・正式EXPは含まない。

- Profile: [`rf/constraints/trial/RF-T009.json`](../rf/constraints/trial/RF-T009.json)、登録: [`registry.json`](../rf/constraints/registry.json) の `minimax_profiles`。
- 実効SHA256: `d1ebefaf4cb6735898467b9c2affcc57b9590d4a6c9f53a0dd84d1f1f2f8b18d`（#446で`objective`を除去・kind変更。旧 #450 SHAは `c20f3fa290bb2ec51fa9b2e085e18dfbdab51cad43420098b6bc5cd39f52edd5`）。canonical JSON（UTF-8、キー整列、compact、非有限拒否）の `{"profile": <profile>, "base_constraint_sha256": <SHA>, "bands_sha256": <SHA>}` のSHA256。profileに閾値・源負荷・S2PパスとSHAをすべて含む。
- 物理base RF-F003 の実効SHA256: `e12c42b11d12db7f20983c48cfa441ea96e362e533450d5862aa8a271c82af86`。bands.csv SHA256: `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`。
- 源 50+j0Ω、負荷 60−j40Ω、UL/DL最大IL 0.8dB、H2/H3最小減衰30dBを全7バンドに明示。B13/B14は回路設定を共有しつつ区間・閾値は別々。
- 入力S2P SHA256 `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、出力S2P SHA256 `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。入力P1→P2、LPF、出力P1→P2の順。50ΩはS基準インピーダンスであり内部終端ではない。RI複素線形補間、範囲外拒否。

## RF-T010（Issue #458）

[`RF-T010.json`](../rf/constraints/trial/RF-T010.json) は承認済みRF-T008 rev3物理base（SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`）を使用。profile実効SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`。全7バンドのUL/DL IL上限は0.75 dB、H2/H3下限は30 dB。他のRF入力・参照面はT009と同じ。試験条件であり正式EXPではない。

## APIと判定境界

`lpf.minimax_profile.load_minimax_profile('RF-T009', allow_trial=True)` は登録・base・CSV・各S2Pを照合し、profileを返す。`profile.build_model(definition)` は現checkoutの入力についてのみ、承認済みbaseの物理stampとprofileのRF入力を使う（別rootを指定した照合結果はmodel化できない）。`model.evaluator(grid).evaluate(x)` の外部系 `RFResponse` と、事前に要求した `EvaluationGrid` を `signed_margins(profile, grid, response)` に渡すと `(J, per_sample_margins)` を返す。profile modelの `resolved_policy` はRF入力のみであり、旧schema 2 policyとして他APIに渡さない。

### profile共通開発Runner（#448、#458）

通常のPlan入力は[入力生成手順](../scripts/README.md#標準plan入力の生成)に従い、標準設定 [`scripts/develop_search_limits.yaml`](../scripts/develop_search_limits.yaml) のGJM01固定C上限10 pFと物理範囲のLを使う。生成された完全boxをstarts生成とCLI `--search-bounds` の双方へ明示し、設定・生成入力・manifestをまとめて保存する。`search_limits: {}` は全物理box。これは入力生成の標準設定であり、Runner/APIでboundsを省略した場合の物理box既定やRF物理制約を変更しない。

[共通CLIと実効Plan](../scripts/README.md#rf-profile-開発run)は登録済みschema 1 profileを明示opt-inで受け付ける。Planの各Search stepに `solver` と `objective: signed_margin_db` を明示し、Terminal各区間は全Search stepより密にする。標準例はTRF／`sum`、比較経路としてSLSQP・SLP・L-BFGS-Bも指定できる。重みは1：SLP `signed_max` は `max(e)` [dB]、SLSQP／L-BFGS-Bの `sum` または `max` は正の違反量 `max(0,e)²` の和または最大 [dB²]、TRFはその和。負の残差は寄与せず、全Search点で違反がなければ目的値0のplateauとなる。異なる目的値を比較せず、旧方式の同名モードともソースSHAを区別する。再始動ありのTRF／L-BFGS-Bは局所収束と全体の予算終了を区別する。有限値でないSearch残差はSTOPし、床値を導入しない。

### 段階別探索の現行推奨方針（2026-11-28 JST）

研究上の推奨値は [scripts/develop_solver_settings.yaml](../scripts/develop_solver_settings.yaml) に集約する。これはPlan作成時の参照用であり、RunnerやOptimizerの内部既定値を変更しない。一次・二次の現行設定は同一なので `exploration` を共用し、局所精密化は `refinement` とする。将来二次の設定を変更する場合にのみ分離する。予算・seed・格子は実験ごとに明示する。

RF-T010・4L2Cでの観測（#529, #531, #533, #535）に基づく暫定的な最小3段階構成：

| 工程 | 初期値・候補数 | Search forward上限/候補 | Search / Terminal点数 | 設定 |
|---|---|---:|---|---|
| 一次探索 | 独立scrambled Sobol 20 seed | 5,000 | 70 / 476 | exploration |
| 二次探索 | 一次上位4 seedの最終vector | 20,000（短縮）または60,000（標準） | 70 / 476 | exploration |
| 最終精密探索 | 二次最良1 seedの最終vector | 1,000 | 196 / 28,028 | refinement（高密度への適用は未検証） |

一次・二次のMNAはTerminal [0,111]、最終は各28区間の始点・中央・終点84点を目安とする。短縮/標準のSearch上限は181,000/341,000。これらは計画値であり、全工程をこの組合せで実証したものではない。70点の独立精密化は必須工程とせず、必要な場合のみ別途計画する（#533では最大10,000 forwardで有効性を観測）。高密度の予算と設定の妥当性は今後検証する。

候補は同一Terminal格子で最大signed margin、正違反二乗和、seed番号の昇順に選抜する。物理・RF検証済みで保存完了した候補（予算終了の数値未収束を含む）を対象とし、異常STOPや検証不合格は対象にしない。後続段階へは完全vector、vector SHA、元seed、同一definition/RF profile/boundsを引き継ぐ。別の凍結Planで新規予算を設定し、SciPy内部状態と乱数状態は継承しない。各段階の原結果は上書きしない。一次の初期値に既存最良候補を使わない。

- #529：独立40→8→1探索で既存最良に近いRF性能。20→4→1と短縮予算は保存軌跡に基づく提案で、同一フローの実証は未了。
- #531：直前局所終了vectorを基準とするbounds幅0.1の正規乱数restartを維持。累積最良基準は不採用（20,000 forward比較）。全探索中の累積最良vectorを返す契約は維持。
- #533：二次終点8候補の単発局所runでftol=1e-8、x_scale=jacが有力。7候補のIL幅は約0.018→0.0014 dB。さらに厳しいftolでは7件が同じxtol終了点。全64件の有限格子RF適合は未達。この実験は単発精密化の評価であり、restart付き二次探索とは区別する。
- #535：一次上位8開始点からrestart付き二次探索20,000 forward/seedの4条件比較。現行A（1e-6/1.0/0.1）の最良IL 0.845788 dB、J≤0.05到達2/8。B（1e-7/1.0）、C（1e-7/jac）、D（1e-8/jac）の最良IL 0.848927/0.960077/0.954700 dB、到達1/0/0件。厳密化はSearch J中央値を改善したが、良好領域への到達では現行Aが優位。一次・二次のexploration共用を維持する。60k予算、他回路、高密度への一般化は未検証。
- 次の改良検討は二次探索の予算・良好領域への到達判定・選抜数、70点精密化の必要性と高密度精密化の条件、restart摂動量。推奨値の変更は実験結果とユーザー判断に基づく。


Searchの上限は各stepのOptimizer callback予算と実RF forwardを別々に記録し、実forwardも同じ数で事前に制限する。Optimizerは同じSearch callbackで評価した `(x, objective)` を返し、Workerは間隔ごと・各step末尾の観測をcheckpointに記録する。Workerによる全観測照合や独自スコアの再計算・順位付けはしない。SearchはOptimizerが生成する有限な閉bounds内の点（SLSQPはSciPyのbounds処理に依存）を通常のRF Coreで評価し、SPD・非有限・線形代数異常を検査する。初期vector・各step最終x・Terminalではboxと全物理を検査し、詳細な受動性と節点→port縮約・S2Pカスケード・外部波の電力収支はTerminal全格子で確認する。独立な枝電流MNAと枝別電力収支の照合は指定spotのみ（Searchは明示指定時のみ）で実施し、独立sample数を別計上する。source/environment・RF profile/base/bands/S2PはJob入口とTerminal後に照合する。実行中の一時的な変更が照合前に復元された場合は検出を保証しない。Terminalは完全vector・全S・IL・APL・両RL・各点のsigned margin・物理検査・独立MNA spotの生証拠を記録する。親 `run.json` が事前の全額予約を記録し、`receipt.json` と全rawの原byte照合後にだけ完了・精算する。未収束は科学状態として保持し、保存に成功したJobなら逐次実行を続ける。失敗時は全額unknownのまま停止し再試行・resumeしない。承認済みformalまたはtrialを物理ベースに使い、旧schema 2条件の直接入力は拒否する。正式EXP接続は未実装・未承認。

要求格子は28行それぞれの正しい設定・両端点を含み、各行の区間内に限定する。応答の格子とprofile ID/SHA、外部パワー波 S21 と IL の整合、および外部S行列の受動性を確認する。正確な伝送ゼロの +∞ dB はフロアせず扱う。profile自体は目的関数を指定しない。共通性能判定の `J=max(e)` はTerminalで使う値であり、Optimizerの目的関数は別途明示する。通過域 `e=IL−上限`、阻止域 `e=下限−減衰`。`J<=0` は**与えた有限格子上の性能閾値**のみを意味する。物理値域、全L行列SPD、接続、受動性・電力保存、独立枝電流MNAなどの検証は別途必須であり、この関数では実施しない。連続帯域、EM、SRF、Q(f)、公差、実測の保証ではない。
