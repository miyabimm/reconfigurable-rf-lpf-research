# RF-T009 試験minimax profile（Issue #450）

RF-T009 は正式 RF-F003 とは独立した **明示opt-in試験条件**。schema 1 `rf_performance_profile` は旧schema 2 trial overrideではなく、`load_constraint`／正式Campaign に渡せない。正式自動昇格・正式EXPは含まない。

- Profile: [`rf/constraints/trial/RF-T009.json`](../rf/constraints/trial/RF-T009.json)、登録: [`registry.json`](../rf/constraints/registry.json) の `minimax_profiles`。
- 実効SHA256: `d1ebefaf4cb6735898467b9c2affcc57b9590d4a6c9f53a0dd84d1f1f2f8b18d`（#446で`objective`を除去・kind変更。旧 #450 SHAは `c20f3fa290bb2ec51fa9b2e085e18dfbdab51cad43420098b6bc5cd39f52edd5`）。canonical JSON（UTF-8、キー整列、compact、非有限拒否）の `{"profile": <profile>, "base_constraint_sha256": <SHA>, "bands_sha256": <SHA>}` のSHA256。profileに閾値・源負荷・S2PパスとSHAをすべて含む。
- 物理base RF-F003 の実効SHA256: `e12c42b11d12db7f20983c48cfa441ea96e362e533450d5862aa8a271c82af86`。bands.csv SHA256: `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`。
- 源 50+j0Ω、負荷 60−j40Ω、UL/DL最大IL 0.8dB、H2/H3最小減衰30dBを全7バンドに明示。B13/B14は回路設定を共有しつつ区間・閾値は別々。
- 入力S2P SHA256 `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、出力S2P SHA256 `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。入力P1→P2、LPF、出力P1→P2の順。50ΩはS基準インピーダンスであり内部終端ではない。RI複素線形補間、範囲外拒否。

## APIと判定境界

`lpf.minimax_profile.load_minimax_profile('RF-T009', allow_trial=True)` は登録・base・CSV・各S2Pを照合し、profileを返す。`profile.build_model(definition)` は現checkoutの入力についてのみ、承認済みbaseの物理stampとprofileのRF入力を使う（別rootを指定した照合結果はmodel化できない）。`model.evaluator(grid).evaluate(x)` の外部系 `RFResponse` と、事前に要求した `EvaluationGrid` を `signed_margins(profile, grid, response)` に渡すと `(J, per_sample_margins)` を返す。profile modelの `resolved_policy` はRF入力のみであり、旧schema 2 policyとして他APIに渡さない。

### RF-T009 専用開発Runner（#448）

[共通CLIと実効Plan](../scripts/README.md#rf-t009-開発run)はRF-T009の明示opt-in専用。Planの各Search stepに `objective: signed_margin_db` を明示し、Terminal各区間は全Search stepより密にする。WorkerはPlanで指定するSLSQP・SLP・Hybridを順に実行し、最終xだけをTerminalで評価する。重みは1：SLP `signed_max` は `max(e)` [dB]、SLSQP／Hybridの `sum` または `max` は `e²` の和または最大 [dB²]。符号付き負マージンも二乗するため、両目的値を比較しない。Hybridは自由変数があれば局所収束後も予算まで再始動するため、全体の`converged`はFalse。全変数固定で正常評価した場合のみTrue。有限値でないSearch残差はSTOPし、床値を導入しない。

Searchの上限は各stepのOptimizer callback予算と実RF forwardを別々に記録し、実forwardも同じ数で事前に制限する。Optimizerは同じSearch callbackで評価した `(x, objective)` を返し、Workerは間隔ごと・各step末尾の観測をcheckpointに記録する。Workerによる全観測照合や独自スコアの再計算・順位付けはしない。SearchはOptimizerが生成する有限な閉bounds内の点（SLSQPはSciPyのbounds処理に依存）を通常のRF Coreで評価し、SPD・非有限・線形代数異常を検査する。初期vector・各step最終x・Terminalではboxと全物理を検査し、詳細な受動性と節点→port縮約・S2Pカスケード・外部波の電力収支はTerminal全格子で確認する。独立な枝電流MNAと枝別電力収支の照合は指定spotのみ（Searchは明示指定時のみ）で実施し、独立sample数を別計上する。source/environment・RF profile/base/bands/S2PはJob入口とTerminal後に照合する。実行中の一時的な変更が照合前に復元された場合は検出を保証しない。Terminalは完全vector・全S・IL・APL・両RL・各点のsigned margin・物理検査・独立MNA spotの生証拠を記録する。親 `run.json` が事前の全額予約を記録し、`receipt.json` と全rawの原byte照合後にだけ完了・精算する。未収束は科学状態として保持し、保存に成功したJobなら逐次実行を続ける。失敗時は全額unknownのまま停止し再試行・resumeしない。RF-F003は物理ベースのみ、旧RF-F003/T005〜T008性能入力は拒否する。正式EXP接続は未実装・未承認。

要求格子は28行それぞれの正しい設定・両端点を含み、各行の区間内に限定する。応答の格子とprofile ID/SHA、外部パワー波 S21 と IL の整合、および外部S行列の受動性を確認する。正確な伝送ゼロの +∞ dB はフロアせず扱う。profile自体は目的関数を指定しない。共通性能判定の `J=max(e)` はTerminalで使う値であり、Optimizerの目的関数は別途明示する。通過域 `e=IL−上限`、阻止域 `e=下限−減衰`。`J<=0` は**与えた有限格子上の性能閾値**のみを意味する。物理値域、全L行列SPD、接続、受動性・電力保存、独立枝電流MNAなどの検証は別途必須であり、この関数では実施しない。連続帯域、EM、SRF、Q(f)、公差、実測の保証ではない。
