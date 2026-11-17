# RF-T009 試験minimax profile（Issue #450）

RF-T009 は正式 RF-F003 とは独立した **明示opt-in試験条件**。schema 1 `rf_performance_profile` は旧schema 2 trial overrideではなく、`load_constraint`／正式Campaign に渡せない。正式自動昇格・正式EXPは含まない。

- Profile: [`rf/constraints/trial/RF-T009.json`](../rf/constraints/trial/RF-T009.json)、登録: [`registry.json`](../rf/constraints/registry.json) の `minimax_profiles`。
- 実効SHA256: `d1ebefaf4cb6735898467b9c2affcc57b9590d4a6c9f53a0dd84d1f1f2f8b18d`（#446で`objective`を除去・kind変更。旧 #450 SHAは `c20f3fa290bb2ec51fa9b2e085e18dfbdab51cad43420098b6bc5cd39f52edd5`）。canonical JSON（UTF-8、キー整列、compact、非有限拒否）の `{"profile": <profile>, "base_constraint_sha256": <SHA>, "bands_sha256": <SHA>}` のSHA256。profileに閾値・源負荷・S2PパスとSHAをすべて含む。
- 物理base RF-F003 の実効SHA256: `e12c42b11d12db7f20983c48cfa441ea96e362e533450d5862aa8a271c82af86`。bands.csv SHA256: `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`。
- 源 50+j0Ω、負荷 60−j40Ω、UL/DL最大IL 0.8dB、H2/H3最小減衰30dBを全7バンドに明示。B13/B14は回路設定を共有しつつ区間・閾値は別々。
- 入力S2P SHA256 `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、出力S2P SHA256 `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。入力P1→P2、LPF、出力P1→P2の順。50ΩはS基準インピーダンスであり内部終端ではない。RI複素線形補間、範囲外拒否。

## APIと判定境界

`lpf.minimax_profile.load_minimax_profile('RF-T009', allow_trial=True)` は登録・base・CSV・各S2Pを照合し、profileを返す。`profile.build_model(definition)` は現checkoutの入力についてのみ、承認済みbaseの物理stampとprofileのRF入力を使う（別rootを指定した照合結果はmodel化できない）。`model.evaluator(grid).evaluate(x)` の外部系 `RFResponse` と、事前に要求した `EvaluationGrid` を `signed_margins(profile, grid, response)` に渡すと `(J, per_sample_margins)` を返す。profile modelの `resolved_policy` はRF入力のみであり、旧schema 2 policyとして他APIに渡さない。

### 開発Workerの限定入口（#446）

`preflight.freeze` は明示 `rf: {constraint_id: RF-T009, allow_trial: true}`、`full_lpf`、Selectionなしを受け付ける。各Search stepに `objective: signed_margin_db` を必須とし、Terminalの各区間点数は全Search stepより大きくする。`DevelopmentWorker(..., policy=<RF-F003 base>, objective_mode='profile_signed_margin', spot_checks={'terminal': [0]}, checkpoint=<新規tmp外部パス>)` では、Planで指定したSLSQP・SLP・Hybridを順に実行し、最終xのみTerminalで評価する。重みは1：SLP `signed_max` は `max(e)` [dB]、SLSQP／Hybridの `sum` または `max` は `e²` の和または最大 [dB²]。符号付き負マージンも二乗するため、両目的値を比較しない。Hybridは自由変数があれば局所収束後も予算まで再始動するため、全体の`converged`はFalse（個々の局所runの成否は別に集計）。全変数固定で正常評価した場合のみTrue。有限値でないSearch残差はSTOPし、床値を導入しない。

Searchの上限は各stepのOptimizer callback予算と実RF forwardを別々に記録し、実forwardも同じ数で事前に制限する。checkpointはOptimizer観測を記録し、Worker独自スコアによる順位付けをしない。Terminalは全S・IL・APL・両RLと物理検査、共通signed margin、指定した独立MNA spotを記録する。外部受動性はTerminal有限格子の全点で確認する。電力保存および独立MNAによる照合は指定spotのみで確認し、独立sample数を別会計で記録する。全点での独立MNA・電力保存は検証していない。開発CLIの単一Job入口については [`scripts/README.md`](../scripts/README.md#rf-t009-単一job開発) を参照。正式Campaignへの移行は対象外。RF-T008 weighted経路の小規模A/Bは [#446診断](diagnostics/issue446_ab.md) を参照し、RF-T009への性能一般化はしない。`MinimalWorker.solve()`単独でRF-T009の目的式を暗黙選択することは拒否する。

要求格子は28行それぞれの正しい設定・両端点を含み、各行の区間内に限定する。応答の格子とprofile ID/SHA、外部パワー波 S21 と IL の整合、および外部S行列の受動性を確認する。正確な伝送ゼロの +∞ dB はフロアせず扱う。profile自体は目的関数を指定しない。共通性能判定の `J=max(e)` はTerminalで使う値であり、Optimizerの目的関数は別途明示する。通過域 `e=IL−上限`、阻止域 `e=下限−減衰`。`J<=0` は**与えた有限格子上の性能閾値**のみを意味する。物理値域、全L行列SPD、接続、受動性・電力保存、独立枝電流MNAなどの検証は別途必須であり、この関数では実施しない。連続帯域、EM、SRF、Q(f)、公差、実測の保証ではない。
