# Issue #325 — Campaign逐次提案境界（第1段階の開発API部分）

## 状態とレビュー単位

本差分は#325の段階分割Draftの最初の増分。**Issue全体のDoD、および第1段階の正式G0/G1接続は未完了**。
未検証の構造提案→Controller→親Runner→既存開発Workerの境界と2予算を、
正式保存ゲートへ接続する前に独立レビューできる単位とする。

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
  **正式planned manifest commitによるHEAD変化の解決は未実装**であり、この開発source照合を正式G1と呼ばない。

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

## 残る実装（このDraftではPASSとしない）

1. 完全checkout/最新main/G0中央予約と `new_manifest/validate_manifest`、
   `validate_run(mode='preflight')` をCampaign単位で接続する正式G1。
   EXP/owner/目的、保存/停止方針、承認実行code bytesと実行時HEADの分離・照合。
2. 正式Worker入口のゲート接続。開発JobSpecをそのまま正式EXPとして流さない。
3. 複数Jobのraw→run_summary/checkpoint/manifest/storage_recordへの選別、Git HEAD byte readback、
   G4独立audit、G5削除可否を偽Git main/EXPの完全fixtureで通す第2段階。
4. 上記正式経路を実装した同一HEADでの通常/sparse CIとfull checkout専用実Git監査。

本増分にG3/G4監査PASSやG5削除権限はない。正式EXPの着手は別の具体的実験Issueとユーザー起動が必要。
