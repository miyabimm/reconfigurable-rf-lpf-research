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

#537 / PR #538で4段階上位Runner `develop-staged` を実装済み。AIは回路Definition・探索方針・予算を決定し、Runnerは承認条件内の候補選抜・フェーズ移行・総予算・再現性判定を実行する。単一Planの `develop` は比較実験で引き続き使用する。#538のsmokeは機能検証であり、探索品質の証明ではない。

RF-T010 trial（effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`）、#529の4L2C・GJM01上限10 pF／他物理bounds・固定S2P、外部ポート6設定28区間の観測に基づく**暫定案**（旧3段階案を置き換える）。他トポロジー・RF条件への一般化、全工程一括の科学的有効性は未検証。以下は研究上の参照値であり、内部既定値・正式RF条件・実験承認を変更しない。

| 工程 | 初期値・候補数 | Search forward上限/候補 | Search / Terminal点数 | solver設定 | 終了 |
|---|---|---:|---|---|---|
| 一次 screening | 独立scrambled Sobol 20 seed | 5,000 | 70 / 476 | exploration | 固定予算 |
| 二次 discovery | 一次上位8 seedのbest vector | 85,000 | 70 / 476 | exploration | 局所run終了時に累積最良Search J≤0.05 dB²、または予算 |
| 三次 exploitation | 二次の有望候補 最大4 seed | 10,000 | 70 / 476 | exploitation（暫定） | 固定予算 |
| 精密 refinement | 三次の全候補 | 10,000 | 196 / 28,028 | refinement（高密度未検証） | 局所数値収束または予算 |

[develop_solver_settings.yaml](../scripts/develop_solver_settings.yaml) はPlan生成の参照設定（自動loaderではない）。explorationはftol=1e-6、x_scale=1.0、restart_sigma=0.1、直前局所終了vector基準。exploitationは同設定の累積最良vector基準（良好領域内での有効性は要実験）。refinementはftol=1e-8、x_scale=jac、restartなし。全てTRF、signed_margin_db/sum。現行staged Runnerはこのsolver組合せを具体値として展開する。比較実験では既存developのsolver optionsを使用し、科学的採否を先取りしてRunnerを変更しない。

Search70はpass2/stop3点、196はpass5/stop9点、Terminalは各17/1001点。前3段階の独立MNAはTerminal [0,111]、精密は28区間の始点・中央・終点84点。CP1000、plain、各数値ライブラリthread1、lk指定（TRF実効off）を既存比較に合わせる。

候補は同一Terminal格子で最大signed margin→正違反二乗和→元seed昇順に順位付け。物理・RF検証済みで保存完了した候補（予算終了の数値未収束を含む）のみ対象。二次から三次にはSearch J≤0.05かつTerminal最大signed margin≤0.15 dBを満たす上位最大4件を引き継ぐ。0件なら有望解未発見として終了（不能証明ではない）、1〜3件なら不足のまま引き継ぎ、補充しない。三次から精密への順位削減なし。各段階で完全vector/SHA、元seed、同一definition/profile/boundsを継承し、別Planの新規予算・TRF呼出し（SciPy内部状態・RNG状態の継承なし）とする。異常STOP時に後段・自動retryを行わない。

最終再現性は同一精密格子のTerminal順位1を基準に、Search J絶対差≤0.002 dB²、worst IL/min H2/min H3各絶対差≤0.005 dB、基準自身を含む数値収束した異なる元seedが3以上を暫定条件とする。素子値のbounds幅正規化距離（最大/RMS）は記録のみ。閾値は未校正であり、数値収束・再現性・有限格子RF適合は別判定。複数seedの一致は大域最適性の証明ではない。

最大予約はSearch 860,000 forward（100,000＋680,000＋40,000＋40,000）、Terminal36、RF samples 65,367,344、独立MNA400。二次は最大8 seedを全実行する現行Runnerであり、4候補発見時の後続seed打切りは未実装。早期終了や不足候補で実消費は減り得るが、事前予約を推定消費まで下げない。この数値は計画上限であり本番run承認ではない。

#### 根拠と残検証

- [#525](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/525)：L≤20 nHとGJM01≤10 pFの同時限定で分布改善・一部大幅悪化。ユーザー採用はGJM01上限のみ（#527）。L上限は物理27 nHを維持。
- [#529](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/529)：40→8→1、40 seed×5kのTerminal margin≤0.5 dBは14件（前半20で8、後半20で6）。20×5k・上位8は暫定。85kの二次最終8候補でJ≤0.05は7件、Terminal margin 0.082679〜0.100650 dB。残り1件J=.136658、margin=.173301。最終dense候補IL .832706 dB、参照 .827841 dBに近いがH2/H3は30 dB未達。有限格子RF適合・参照同等条件は未成立。
- [#531](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/531)：良好領域発見前の20kでは直前局所終点基準が最良値・到達数で優位（J≤.05は2/8対0/8）。良好領域到達後の累積最良基準の評価ではない。
- [#535](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/535)：一次上位8開始点・20k・直前基準。ftol 1e-6/1.0、1e-7/1.0、1e-7/jac、1e-8/jacのJ≤.05到達2/1/0/0件。現行explorationを維持。保存局所run境界でJ≤.05なら2件・143,883/160,000 forward（10.1%削減の反実仮想）。J≤.1では同2件・139,698 forwardだが2001の開始候補が異なる。J≤.2では3件のうち2009はTerminal margin .151548で.15を超える。J≤.5では全8件が1,615 forwardで止まるため緩すぎる。
- #535 Aのseed2025/2001は局所run終了9,211/14,672 forwardで初回J≤.05、20kと#529 85kの最良vector SHAに一致し、追加146,117 forwardの改善なし。#529の過去保存観測ではJ≤.05が20k/40k/60k/85kで2/3/4/7件。85k各seedの最終best発見局所runを上界に使った早期終了の推定Search消費≤463,054（680,000の31.9%以上削減、同軌跡を仮定）。初回到達全件のTerminalは未確認で、checkpoint瞬間観測と局所run境界を混同しない。長時間停滞後に良好領域へ移動するseed2015があるため、二次の停滞早期終了は採らない。
- [#533](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/533)：70点・restartなし・二次終点8候補でftol=1e-8/jacが有力。良好7候補のIL幅.017970→.001379 dB、全8のforward中央値5192.5。さらに厳しいftolで7件は同じxtol終了点。全64件有限格子RF適合未達。196点での適用、予算・再現許容差は未検証。
- **次実験 [#539](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/539)**：#529の全局所runからJ≤.05初回到達vectorを抽出し、476点/2 MNAの固定評価で最大4件を選抜。三次 A=last/.1、B=best/.1、C=best/.03（各10k）、D=三次なしを比較し、全条件の全候補を196/28028点・最大10kの精密探索へ引き継ぐ。三次の必要性・restart基準・摂動量・消費、精密後の再現性を評価。長時間の実際の初回到達点、閾値緩和の効果、格子選択、別回路、一次seed/予算配分、全工程の実証は区別して判断する。

Searchの上限は各stepのOptimizer callback予算と実RF forwardを別々に記録し、実forwardも同じ数で事前に制限する。Optimizerは同じSearch callbackで評価した `(x, objective)` を返し、Workerは間隔ごと・各step末尾の観測をcheckpointに記録する。Workerによる全観測照合や独自スコアの再計算・順位付けはしない。SearchはOptimizerが生成する有限な閉bounds内の点（SLSQPはSciPyのbounds処理に依存）を通常のRF Coreで評価し、SPD・非有限・線形代数異常を検査する。初期vector・各step最終x・Terminalではboxと全物理を検査し、詳細な受動性と節点→port縮約・S2Pカスケード・外部波の電力収支はTerminal全格子で確認する。独立な枝電流MNAと枝別電力収支の照合は指定spotのみ（Searchは明示指定時のみ）で実施し、独立sample数を別計上する。source/environment・RF profile/base/bands/S2PはJob入口とTerminal後に照合する。実行中の一時的な変更が照合前に復元された場合は検出を保証しない。Terminalは完全vector・全S・IL・APL・両RL・各点のsigned margin・物理検査・独立MNA spotの生証拠を記録する。親 `run.json` が事前の全額予約を記録し、`receipt.json` と全rawの原byte照合後にだけ完了・精算する。未収束は科学状態として保持し、保存に成功したJobなら逐次実行を続ける。失敗時は全額unknownのまま停止し再試行・resumeしない。承認済みformalまたはtrialを物理ベースに使い、旧schema 2条件の直接入力は拒否する。正式EXP接続は未実装・未承認。

要求格子は28行それぞれの正しい設定・両端点を含み、各行の区間内に限定する。応答の格子とprofile ID/SHA、外部パワー波 S21 と IL の整合、および外部S行列の受動性を確認する。正確な伝送ゼロの +∞ dB はフロアせず扱う。profile自体は目的関数を指定しない。共通性能判定の `J=max(e)` はTerminalで使う値であり、Optimizerの目的関数は別途明示する。通過域 `e=IL−上限`、阻止域 `e=下限−減衰`。`J<=0` は**与えた有限格子上の性能閾値**のみを意味する。物理値域、全L行列SPD、接続、受動性・電力保存、独立枝電流MNAなどの検証は別途必須であり、この関数では実施しない。連続帯域、EM、SRF、Q(f)、公差、実測の保証ではない。
