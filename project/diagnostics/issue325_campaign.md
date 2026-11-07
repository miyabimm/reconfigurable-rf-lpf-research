# Issue #325 — Campaign逐次提案境界・G0/G1 planned保存接続

## 状態とレビュー単位

PR #326で第1増分の開発APIをmainへ反映済み。次の増分は `search.gates` による
Campaign単位のG0/G1 planned保存・read-only照合。**Issue全体のDoDと正式Runner接続は未完了**。
G1の技術照合成功を、正式Workerへの実行権限やG3〜G5保存完了と混同しない。

- 実EXPの予約、中央台帳・歴史証拠の変更、本番探索は行わない。
- `campaign.run_campaign()` は常に `not_ready` で停止する。正式G0/G1の代替承認機構ではない。
- 全開発出力はcheckout外system tmp限定。`development_only` / `G0_G1=not_ready` /
  `G2_G5=not_ready` を保持し、正式runへ名前だけ転用しない。
- 既存schema2 `develop`、旧fixture、optimizer、RF数値仕様は変更しない。

## 入力契約

Campaign YAMLは既存schema2の拡張であり、別のPlan schemaを作らない。
既存の `rf`、`seeds`、`arms`、selection/terminal/anytime/denseの格子・Job/Trial上限は必須のまま。
本増分ではControllerの固定ルールを **1 seed × 1 arm** に限定し、同じ規則から提案ごとに新Jobを作る。
Campaignの `definition` は `null`。未来のdefinition/start/Job一覧は格納しない。

追加する `campaign` の必須キー：

- `max_topologies`, `max_rf_samples`：正整数。Pythonに実研究の既定値を置かない。
- `structure`：`max_nodes`、`max_fixed_capacitors`、`max_variable_capacitors`、
  `inductor_types`、`fixed_c_types`、`variable_roles`、`allow_coupling`、`allow_ic_fixed`。
  明示した数・種類以内のL-tree/C枝を対象とする。端点・接続・role・物理配置・結合slotは既存構造/物理検査がさらに制限する。
  構造上限はRF上限の拡張ではなく、無制限の素子数を提案することを防ぐ研究範囲。
- `independent`：`stage`（`not_run`または`terminal`）、`max_candidates`、`sample_indices`。
  `not_run`なら0/空配列。terminal検証では現在のWorkerがtop-kを全て検査するため、
  `max_candidates`とselectionの`top_k`を一致させる。指定indexを各対象候補で検査する。
  検査対象候補/点数は凍結し、主RF samplesには換算しない。

AI提案YAMLは別ファイル。Issueの必須キー例どおり、`schema_version`と4つのpayloadキー
`proposal_id / based_on_state_sha256 / reason / definition`のみを受け付ける
（本文の「4キー」はschema_versionを除くと解釈）。
`definition`は既存3 dataclassの全フィールドをそのまま使い、省略・未知フィールドを認めない。
枝の向き/順序、physical_order、符号付き結合のslot順、IC-fixed枝を維持する。
SafeLoaderで未知tag・重複キーを拒否し、厳密型検査でboolの整数化、NaN/Inf、未知キーを拒否する。
L/C/k、seed、solver、予算、RF条件、コマンドを提案へ記載できない。

## APIと証拠

```python
from lpf.search.plan import load_preflight
from lpf.search.campaign import (
    begin_development_campaign, campaign_snapshot, submit_development_proposal,
)

plan = load_preflight(campaign_yaml)
advisor_input = begin_development_campaign(plan, new_system_tmp_directory)
# ユーザー/呼出側が1件のデータYAMLを提出。自動AI生成・watcherはない。
advisor_input = submit_development_proposal(plan, proposal_yaml, new_system_tmp_directory)
```

`campaign_snapshot()` は新しいdictとcanonical SHAを返す。Plan SHA、許可構造、採用済み構造SHA、
残topology数、requested/completed/reserved/残samples、実raw由来の短い結果要約とSHAを含む。
返されたdictを変更しても台帳は変わらない。初回も実際に生成したSHAが必要。
拒否を記録した後もsnapshot SHAは更新されるため、再提案には新snapshotを使う。

親専有 `campaign.json` に提案/拒否/採用/終了イベントを追記する。
提出YAMLの元bytesを `proposal-*.yaml` として保全し、入力byte SHA、正規化proposal SHA、
`asdict(CircuitDefinition)`の構造SHAを別々に記録する。
採用時にだけ構造SHAを登録し、同一構造の再Jobでは増やさない。採用後にunknownでも返還しない。
Job固有ID、親Job、Campaign Plan SHA、proposal SHA、参照state SHAを既存開発JobSpec内へ凍結する。
Jobごとの完全definitionは既存schema2の `definition` 欄へ同じdataclassデータとして格納する。
従来のファイル/SHA参照も維持する。新しいトポロジーDSLはない。

- 完全xは `starts.generate_for_definition()` の単一Sobol点で生成し、既存closed bounds/Q/role/SPD検査を通す。
  非合法なstartをclip・補充・再試行しない。
- `requested + reserved + next_job_cap <= max_rf_samples` を検査し、
  採用・JobSpec SHA・当該Jobのcap予約・unknown markerを1回の親atomic書込で確定してからWorkerを呼ぶ。
  未来のJobのcapは予約しない。
- `execute_development_job()` と `_development_readback()` を再利用する。
  Step/Selection/Terminal/Anytimeの実requestedを合計する。denseは未実行で `not_run`。
  独立branch-current MNAのrequested/completedは別計数。
- 正常なraw byte/SHA/費用照合後だけ未使用予約を解放する。
  未知/例外/読戻し失敗は全額、または確認済みrequestedを除いた残額を保持して全体STOP。
  親保存障害は伝播し、成功状態での再保存をしない。自動resume/retryはない。
  次の提出時にも既存JobSpec/Plan/費用/元proposal bytes/Worker rawを再読込し、
  キャッシュされた総費用・構造一覧だけを信用しない。
- source_identityには実行コードbytes/lock/環境/HEADを記録し、Jobごと/forward前にも再照合する。
  開発経路ではHEAD変更を許さない。正式planned保存のHEAD変化は下記の独立したG1照合で扱う。

## 検証範囲

`tests/test_issue325_campaign.py` は既存共有fixtureを使う再利用可能な提出/費用/保存障害契約テスト。
本物のEXP台帳を触らず、system tmpのみで実行する。通常CIとsparse CIの既存workflowに追加する。

- 異なる2構造→2 Job、同一構造の再Job、理由だけの変更で構造SHA不変。
- 逐次cap予約、照合済み余剰の再利用、古いstate SHA・未知/重複キー・悪意tag・型・role・枝・
  許可構造範囲・2予算・source/Plan不整合でforwardゼロ。
- unknown/crash/raw改変時の予約保持と後続STOP、親保存障害で再保存/forwardなし。
  後続提出前の過去raw/proposal bytes/集計値/構造台帳改変の検出。
- RF-F003と明示trial RF-T008の実RF小格子：各392 requested / 392 completed、terminalの
  独立MNA 1 spot。6設定×28不連続区間、既存複素S/IL/APL/RL・受動性/電力検査を再利用。
  solverはfixtureであり、収束・strict適合・物理実装性を認定しない。

## G0/G1 planned保存・read-only照合（次の増分）

`search.gates.prepare_campaign(plan, experiment_id, owner=..., request_id=..., purpose=...,
selection=..., root=...)` は以下を検査して**新しい当該EXPだけ**にplanned manifest/storageを作る。
既存EXPは上書きせず、予約・commit・push・RF計算・自動再試行はしない。

- 既存 `_complete_checkout` / `_fresh_main`、最新mainを含むclean HEAD、
  `is_reserved_on_main` / `reservation_on_main` で完全checkout・最新remote・中央予約を照合。
  owner/request IDは出典整合であり、追加の本人認証ではない。
- 既存schema1 `new_manifest` / `validate_manifest` と `validate_run(mode='preflight')` を再利用。
  `search_scope.campaign` にschema2 Plan全体/SHA、承認code bytes/HEAD/lock/env/threads、予約出典を格納。
  未来のdefinition/start/Jobを予測しない。selectionは既存保存ポリシー形式の明示入力。
  prepare/preflightとも見積容量をbudget JSONのEXP容量上限と照合する。prepareは例外を発行せず、
  超過見込みならファイル作成前にSTOP。preflightでも記録済みsize exceptionなしの超過はSTOPし、
  例外の必須フィールド検査は既存storage監査へ委ねる。
- RF-F003と明示trial RF-T008を同じ入口で扱う。RF/格子/総2予算・構造/solver範囲は凍結Planで照合。

plannedファイルをmainへcommit/pushした後、
`search.gates.campaign_preflight(plan, experiment_id, owner=..., request_id=..., root=...)`
を呼ぶ。manifest/storageの **最新main・HEAD・working treeの実bytes** が全て一致し、
planned状態・Plan/予約/目的/seed・既存manifest/storage監査が健全な場合だけ `preflight_ready` を返す。
承認HEADと予約mainは現在mainの祖先であることを要求する。
コードfiles/環境の一致と、承認HEAD以降のsrc/scripts/rf/project/pyproject/lockおよび
`data/phase2_git_storage_budget.json`の無変更を検査し（data全体は凍結しない）、
**planned commit前のapproved_sourceと、commit後のruntime_sourceを別に返す**。自己参照SHAは要求しない。

返値は常に `execution='not_run'`, `execution_allowed=False`, `G2_G5='not_ready'`。
read-only技術照合であり、正式Runnerは依然fail-closed。開発rawを正式EXPへ遡及昇格させない。

`tests/test_issue325_campaign_gates.py` はsystem tmpの隔離した実Git working tree＋bare originで検査する。
架空EXP-050の予約台帳・RF入力コピーのみを使い、本物の中央台帳・歴史証拠に書き込まない。
F003/T008、planned commitによるHEAD変化、未予約/branchだけの予約、owner/request不一致、
sparse/欠落/stale remote、remote bytes不一致、code/env/project入力/Plan改変、storage検査、既存EXP保護で
RF forwardゼロを確認する。これは完全な歴史証拠auditや正式実行fixtureではない。

## 残る実装（このDraftではPASSとしない）

1. G1照合結果を正式Runner/JobSpec/Worker入口へ接続し、投入ごと/forward前の再照合を行う。
   開発JobSpecをそのまま正式EXPとして流さない。
3. 複数Jobのraw→run_summary/checkpoint/manifest/storage_recordへの選別、Git HEAD byte readback、
   G4独立audit、G5削除可否を偽Git main/EXPの完全fixtureで通す第2段階。
4. 上記正式経路を実装した同一HEADでの通常/sparse CIとfull checkout専用実Git監査。

本増分にG3/G4監査PASSやG5削除権限はない。正式EXPの着手は別の具体的実験Issueとユーザー起動が必要。
