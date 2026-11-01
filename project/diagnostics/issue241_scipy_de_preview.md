# Issue #241：Sobol再利用・SciPy-DE接続（mock限定）

## 着手根拠・不変更

- 基点main `da24d4045ffe6dede65ce32512c9549528f36086`、PR #240統合済み。
  postmerge [CI 41299610692](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/41299610692) SUCCESSを着手前に確認。
- 運用正本、registry/bands、SLSQP v2、関連 #231/#233/#239 と
  [共通比較契約](issue239_optimizer_comparison.md)を確認。
- loader再確認：active **RF-F003** / `f85710200ccda5b72ab32f943540fbfd7a8abb3137c5f4e6e5ba7a6d7b3da2ba`、
  明示trial **RF-T008 rev3/full_lpf** / `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`。
  bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`。
- RF数値・固定S2P・全6設定/28個別区間・SLSQP v2・履歴EXP/索引は不変更。
  本Issueで新EXP/実RF最適化/本番計算を実行していない。

## 最小APIと計測

`multistart.generate_starts(..., count=3, cost_meter=None)` にopt-inを追加。
同じ16点Sobol blockを同順序で一度だけ検査し、設計1本を含む3〜17本を要求できる。
固定座標・signed k・全L/C/6設定Cv・open端・SPD/roleを既存schema/validatorで検査し、
不足は理由付き例外。clip/repair/epsilon floor/別seed再試行はない。
既定3-startの全出力は基点mainコードとmock下で直接一致を確認、完全vector SHAも回帰fixtureに固定した。

`scipy_de_preview.run_de_preview(comparison, initialize=..., seed=..., maxiter=...,
max_frequency_samples=..., max_proposals=..., max_wall_seconds=...)` は
**mock forwardを注入する契約検査用**。CLI・EXP driver・永続保存・再開/再試行は提供しない。
`initialize(meter)` は同回路・同格子の `generate_starts(..., count=N, cost_meter=meter)` を返す。
初期化はtry/予算/時間境界内。人口は5本以上、完全SHA、policy/definition/schema、重複、
部品/box/SPD/roleを再検査してからSciPyへ渡し、SciPyの暗黙init clipを防ぐ。

公開 `differential_evolution` と `NonlinearConstraint` のみ使用。
物理xのみ、`polish=False`、`workers=1`、固定 `default_rng(seed)`。
制約は未丸めminH2/minH3−30、目的はforward worst IL。
**内部はSciPy Lampinen選択**であり、共通max→sum→IL辞書式は観測bestの報告にのみ使う。
ソルバー返却一点の再評価は行わず `final_reevaluation=not_run`。

- `EvaluationCost`を継承した小さなメーターで**各forward入口の直前**に次batchのsample数を確認。
  失敗batchもrequested全数に課金し、上限超過batchは開始しない。
- 初期化のforwardも課金し、そのILから共通scoreを得て観測bestに含める。
  初期人口完成前の予算終了でも、既観測bestの完全vector/SHA/scoreを返す。
- requested/56、forward calls/completed/failures、component/SPD/box/role拒否、solver callback数を分離。
  人口検査とseed内検査は別eventだが、forward回数には加算しない。
- adapter内のexact一件F/制約共有は `cache_hits` に計上。これはmock配線の明示的方針であり、
  #239のcacheなし一次比較に採用済みではない。将来の公平な比較では全方式のcache方針を別途固定する。
- 時間は初期化＋solver overheadを含む全体を一回だけ記録（内側evaluate計時との加算なし）。
- proposal上限はsolverのscore要求event数（cache hit含む）。初期化は既存の最大16点blockに限定し、
  その拒否はgenerated.rejected/各物理拒否counterに保持。初期化失敗時もcounter/例外理由は残す。
- wallは協調停止。in-flight forwardやinitializerを強制中断しない。
- `budget_exhausted` / `proposal_limit` / `wall_limit` / `physical_rejected` / `failed` /
  `interrupted` / `solver_returned` を区別。solver_returnedでもsuccessは別列で、RF PASSを意味しない。
  例外・中断・予算終了にも最終メーターと観測bestを返し、自動retryしない。
  外部killに耐える永続保存は本Issueの対象外。

## 物理不正の扱い・本番接続ブロッカー

公開SciPy制約callbackは固定長の数値残差を要求する。しかし物理不正点にH2/H3は定義できない。
本実装はその点に架空RF残差・可行解・任意penaltyを与えず、**物理事前拒否でrun全体をfail-closed停止**する。
mockで「合法点を観測→open端不正proposal→forwardせず停止→best/拒否counter保持」を検証した。
RF不可行（合法だが30dB未達）なら停止せず、通常のSciPy非線形制約として扱う。

したがって、物理不正点を跨いで安全に探索を継続できるDE本番経路は**未提供**。
公開APIでの物理制約処理、予算・seed/人口数・cache公平性、G0/G1〜G4/永続保存は別Issueで固定・レビューが必要。
このadapterをそのまま実RFベンチマークに接続しない。

## 実行済み検査・未実施

Python3.12 / frozen uv / SciPy1.18.1、BLAS/OMP/MKL=1。
`uv sync --frozen`、新規7契約テスト、既存comparison7・problem_seed8・synthetic_runner11・
shared_entry6・staged11・normalized4・budget14、合計68件PASS。
shared_entryのEXP形式commit出力は隔離temp fixtureのみで、研究EXP作成ではない。
mainコード対既定3-start全出力一致、条件SHA確認、`git diff --check`もPASS。
通常CI・Pi sparse CIは同じ新規テストを実行するよう既存workflowに追加（結果はPRで記録）。

実RF DE/SLSQP/L-SHADE最適化、新EXP、dense1001/新候補の独立MNA/power/passivity検証は未実施。
履歴全保存監査はPi sparseでは未実施。SRF/Q(f)/EM/公差/実測・連続帯域保証・最適性は未確認。
Draft PRでChatGPT独立レビューを依頼し、レビュー前にマージしない。
