# Phase 2：現行情報への集約と不要文書・情報の削除計画（2026-10-17）

> **状態：計画策定・削除未実行。** 本計画では、旧文書の実ファイル削除および現行文書内の不要な旧記述削除を明示的に対象とする。ただし、個別の削除採否は最新mainで出典・参照・再現性を再監査した後のレビューPRで決定する。現段階で原資料・Gitブランチ・tag・Git履歴・実験を削除していない。
>
> **研究はPhase 2継続。Phase 3への移行はユーザーの明示承認を要する。** 本計画は新たなRF-F003設計・探索・RF仕様改訂を含まない。

## 0. 正本・開始点

- 運用正本：[chatgpt_project_instructions.md](chatgpt_project_instructions.md)。
- RF数値正本：[constraints/registry.json](../data/constraints/registry.json) が指定する[正式RF-F003](../data/constraints/formal/RF-F003.json)。RF-T005は[試験](../data/constraints/trial/RF-T005.json)。周波数帯は[bands.csv](../data/bands.csv)。
- 今回の計画起点main：`055b222c79c73c7fbeacb19383f21c1da0625195`（2026-10-17、[統合PR #71](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/71)のマージ）。実作業前にはmainの最新SHAを再取得し、差分を取り直す。
- 原[2026-10-17整理計画](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/12b1dfd7a91ab466a6cfbbb8b4db968715e91d5f/docs/phase2_repository_reorganization_plan_20261017.md)はStep 1～5の原判断を残す履歴であり、この文書はその**追加の品質仕上げ・不要物削除フェーズ（研究のPhase 2内）**に当たる。
- 旧[Step 1監査](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/d0351e507dd9fd39338f7e4a69c2003bae3d531f/docs/repository_audits/step1_20261017_report.md)：2026-10-17整理開始時の1,043 tracked path／12,859,345非圧縮bytes／同一blob34組・追加38path。新mainの**現在値ではない**。旧静的参照カウントも当時の値に過ぎない。
- [Step 4保全判断](phase2_repository_step4_review_20261017.md)と[46件台帳](../data/repository_reviews/step4_retention_46_20261017.csv)は全件`retain_pending_source_context_review`。**この46件を本計画の承認によって削除可能にしたとは解釈しない**。
- [Step 5統合検証](phase2_repository_step5_final_verification_20261017.md)：マージ直前の[Phase 2 regression](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39028160775)とStep 3/4/5 CIはSUCCESS。マージ後mainのCI結果は別実行として確認が必要。

## 1. 最終目的と成功基準

旧日付の研究叙述、終了した作業指示、二重管理情報、再生成可能な不要出力を**現行の入口から排除**し、利用者は「正本、正式/試験区分、実際の最良候補、実行/検証状態、次工程」を短い経路で確認できる状態にする。同時に、保存すべき実験証拠を守り、合理的なものは**Gitの現在のtreeから実際に削除**して維持管理の負荷を下げる。

完了基準：

1. README → 現行RF-F003/RF-T005・最新候補・未完了課題・番号予約・方法の経路は**原則2クリック以内**。現行欄に「PR #67レビュー中」「EXP-047で全CI失敗」「14+10候補未統合」などの**解消済み状態は0件**。
2. `docs/roadmap.md`・`docs/current/*`・`docs/results/README.md`・`data/README.md`・`experiments/README.md`・`scripts/README.md`は、最新mainの実績・実行状態と整合。歴史記録は当時の日付・制約を付けて区切る。
3. 全追跡Markdownのローカル相対リンクを列挙・解決し、**真の不正リンク0件**。テスト内の架空パス、コード片は実ファイルリンクと区別。アンカー、workflowのGitHubブラウザURLについても可能な範囲で別検査。2026-10-17 Step 5の403件PASSは**対象文書限定**であって全Markdown検査PASSではない。
4. 条件別の統合24候補について、面積・IL・H2/H3・L/C数・EXP・元ベクトルSHA・検証状態に加え、**接続/トポロジー系列・Lの配置と結合の符号を検索する方法**を実装。旧記録の欠損属性は`unknown`であり推測補完しない。
5. 現行Git treeから削除した各ファイルは、[候補審査台帳](../data/repository_reviews/phase2_cleanup_deletion_candidates_20261017.csv)に**理由、削除前path/blob SHA、出典コミット、参照解消、代替出典、再現性評価、承認、削除PR/CI、復旧方法**を確定して記録する。削除承認0件の時点で「削除作業が完了」とは呼ばない。
6. 全てのPhase 2 regressionとデータ整合テストがSUCCESS。RF-F003正式/試験RF-T005の区別、4+6候補、旧14件の保存、2個の固定S2P SHA256、元EXP-047 manifest非改変、46件保全対象を確認。
7. 現在のtreeのファイル削減数・非圧縮bytes削減・Gitオブジェクト／履歴削減を**それぞれ別**に報告。Git blobが同一の38追加path削除は、Git packディスク容量の節約を保証しない。

## 2. 削除・移動・保持の判定区分

| 処置 | 具体的な対象 | 条件・扱い |
|---|---|---|
| **T：現行文書から古い文言を削除・置換** | 古いCI失敗宣言、未マージPR、未統合24候補など | 実績を現行欄へ反映し、過去の一次証拠は変更しない。優先実施 |
| **D：Git追跡treeから文書を削除** | 現行正本と役割が重複する旧計画・旧説明・解消した一時的運用メモ | 重複しない事実・当時の制約・訂正・PR/run/SHAを保持する出典へ移し、全参照置換・ownerレビュー後に個別削除 |
| **M：退避・一本化（削除とは区別）** | 必要な研究履歴をもつ旧文書、複数の方法説明 | 出典コミット・元path・明示リンクを残す。研究原本の安易な移動はしない |
| **R：原位置保持** | 研究一次証拠、正式/試験JSON、bands、S2P、元checkpoint、manifest、検証結果・訂正根拠 | 内容の重複や古さにかかわらず原則保持。要レビュー46件は明示の個別承認まで保持 |
| **E：再生成可能な不要出力を削除** | 将来の探索の中間dump、キャッシュ、空ロック、期限付きレポート | 元runの停止/再開・失敗原因の再現に必要ないと確認できたファイルのみ。Git管理外の`results/`との役割を先に分離 |
| **W：終了済みworkflowを廃止** | 完了済みEXP専用workflow | 再実行機能・最新main上の使用・履歴復元性と予約workflowへの影響を調査後に別PRで削除 |

**旧い・0静的参照・同一blob・GitHubで復元可能という一条件だけでD/Eを確定しない。** `git show <source_commit>:<path>` で以前の文面を取得できても、実験の再開スクリプトやレビュー実務が現在のpathを必要とすることがある。削除承認は「履歴復旧性だけで十分」という判断まで含む。

## 3. 具体的な対象と優先順位

各行の進行状態・承認欄・基準日の出典は[個別判定台帳CSV](../data/repository_reviews/phase2_cleanup_deletion_candidates_20261017.csv)に記録する。以下のDは**削除の提案であって、削除可能と検証済みではない**。

### 3.1 最優先：解消済み情報の現行欄からの除去（T）

| 対象 | 削除する古い情報 | 置換先・対応 |
|---|---|---|
| `README.md` | PR #67「レビュー中」、EXP-047が原因で「全CI PASSではない」とする現行注記 | [マージ済みPR #71](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/71)、実行済み最終CI、旧形式EXP-047対応範囲に更新 |
| `docs/roadmap.md` | 冒頭のEXP-047未修復、14+10候補未統合、Step 2未実施の現行扱い | Phase 2の残課題だけを冒頭に集約し、以前のロードマップ本文は**日付付き履歴**へ |
| `docs/current/open_research_questions.md` | 既に解消したEXP-047監査失敗を開いたP0として扱う表現、旧候補統合未完了 | 「2026-10-17に互換アダプターで回帰成功」に変更。不明seed/環境・厳格manifest完全復旧は未完了として残す |
| `docs/results/README.md`、`data/README.md`、`scripts/README.md` | 最新10候補と旧14件が「未統合」、報告器が旧14件専用との断定 | [条件別24候補の派生CSV](../data/catalog/phase2_candidate_catalog_20261017.csv)、不変14件入力、`--catalog`使用例へ誘導 |
| `experiments/README.md` | EXP-047の旧スキーマによるCI失敗を未解消扱い | 原manifestが非標準のまま保持されていることと、[索引専用legacy adapter](../src/lpf/legacy_manifest_adapter.py)によるPASSを明記 |
| `docs/phase2_repository_reorganization_plan_20261017.md` と `docs/phase2_repository_step5_final_verification_20261017.md` | 冒頭の「未実施」「未マージ」を**現行状態に見せる入口** | 元の日時・観測に手を入れず、冒頭に#71マージ済みと追記するか目次側で履歴扱いを明記 |

### 3.2 過去文書：ファイル削除を候補とする（D）

| ID | ファイル | 削除の目的 | **削除前に満たすべき追加条件** |
|---|---|---|---|
| D-001 | `docs/repository_reorganization_plan.md`（2026-10-12旧R1～R5計画） | 後継[2026-10-17の整理計画](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/12b1dfd7a91ab466a6cfbbb8b4db968715e91d5f/docs/phase2_repository_reorganization_plan_20261017.md)、[今回の計画](phase2_repository_cleanup_and_deletion_plan_20261017.md)への一本化 | 旧R2/P4-A実装ゲートと未実行事項に現在も固有の規範がないか確認し、残る事項は履歴に明記する |
| D-002 | `docs/research_result_governance.md`（2026-10-14初版） | 現行RF-F003と矛盾するRF-F002「現行」規定、旧9候補の初版説明を現行ルールから除外 | 出典別比較規則、元候補の昇格基準、訂正ルールで独自の意味があれば[運用目次](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/governance/README.md)と正本へ移す |
| D-003 | `docs/phase2_actions_ci_repair_20261017.md`（過去CI修復メモ） | 解消したワークフローの一時運用説明を常時閲覧対象から外す | EXP-044/046当時の改訂理由、CI障害の原因、実run URL・コミット、修正履歴を事故記録に集約。再発テストは保持 |
| D-004 | `docs/repository_storage_audit_20261014.md`（旧Git tree数値監査） | 旧規模707件/8.30MBを現行値と誤認しないよう監査導線を一本化 | 当時のmain SHA、件数、対象条件、比較可能性、旧runログ／再開証拠の説明を日時付き監査履歴へ保持 |
| D-005 | `docs/phase2_storage_pareto_review_20261015.md`（旧13候補の保存レポート） | 現行24件カタログ導入後の旧候補サマリーを整理 | **慎重扱い**。当時の候補の数値・条件・優越判定を完全に引き継げること、元候補の実測ではないこと、必要な再現性を確認するまで**削除しない** |
| D-006 | `docs/r2_handoff.md`と退役した旧探索範囲資料（旧Git履歴に保存） | 旧限定探索スコープを現行実装の説明と混同しない | 数値検証／探索上限・未実施記録など固有内容が多い可能性。**まず現行と履歴の明示ラベル付けのみ**、削除は再評価後 |

2026-10-17のStep 1でD-001～D-004等に静的流入参照0件が記録されている例があるが、**旧mainの集計であり統合PR #71追加の`docs/archive/`、`docs/governance/`、`docs/methods/`から新規リンクが増えている**。最新mainの参照実態を調査せずにD判定を確定しない。

### 3.3 基本的に削除しない対象（R）

- `docs/rft003_*.md`の12件、`docs/research/rf_t004_*.md`、`docs/exp016_*.md`、`docs/phase2_exp017_checkpoint_provenance_review_20261015.md`などの**数値実験の経緯・訂正・比較を唯一記述する歴史資料**。コンパクトな履歴目次と原文を保持。特に独立MNAの適用条件を失わない。
- `docs/maintenance/branch_cleanup_20261014.md`：ブランチ削除を**実行した証拠**と元PRの復元経緯であり、単なる不要な古文書ではない。
- `docs/research/*literature*`、T/π結合・モード理論文書：将来の回路考案の源泉となるため、未参照や旧日付のみで削除しない。
- `data/constraints/`、`data/bands.csv`、`data/design_constraints.json`、`data/parasitics/`、`data/pareto_snapshots/`、`data/catalog/2026-10-17固定入力`、`uv.lock`、`experiments/**/manifest.json`、元ベクトル・実行時ソース、必須検証overlay。
- `data/repository_audits/`、`data/repository_reviews/`の**削除判断の根拠台帳**および[EXP-047旧manifestの固定overlay](../data/validation/exp047_legacy_manifest_adapter_20261017.json)：元ソース保全の理由を失わないよう保持。
- Step 4で確認した同一Git blob 34グループ／38追加path、未判定の46要レビュー原証拠、`source_pr38/`、`code_snapshot/`、一時停止・再開試験の`logs/tasks/config/lock`は**デフォルト保持**。新規の意味判定により後からE候補へ選別可能だが、まとめ削除は禁止。

### 3.4 実験一時出力・完了済みworkflow（E/W）

- 次回の新規EXP以降、Git未追跡の`results/`に置くキャッシュや中間探索gridは、決定的に再生成でき、選別済み証拠に依存がないことを確認してから破棄可能な運用にする。
- **現在Gitにある**old runの`*.log`、`tasks/`、`*.lock`、保存ワークフローは新しい意味レビューの対象。失敗・再開・比較benchを再現するのに必要な場合は保持。意味レビューなしの`find ... -delete`は禁止。
- `.github/workflows/exp042_*.yml`などのEXP固有workflowは、**実行履歴と再起動・復元手順、workflow_dispatch利用者を調べた上**でW候補にする。番号予約、Phase 2回帰、出典整合に必要なworkflowは削除しない。
- 削除対象の見積もりは新mainの再帰Git treeと現行の参照・CIに基づき別算定する。旧監査の「診断らしい144ファイル／2.35MB」も**削除可能な量ではない**。

## 4. 実施順序：Phase 2内の独立レビューPR

| 作業 | 内容 | 実施後の確認・完了ゲート |
|---|---|---|
| **W0 現状の再監査** | 最新main再帰tree、全追跡Markdownのリンク抽出、GitHub Actionsで使われるpath、元候補/実験/検証のリンク、各D候補のGit SHAと参照を収集 | 基準SHA付きの変更前path・逆参照・byte・出典台帳完成。未追跡・動的参照の限界明記 |
| **W1 現行記述を整理** | 3.1のT項目修正、READMEを短縮、変更済み内容は日付付き履歴へ分離、EXP-004旧workflowリンクを直す | 古い現行ステータス0件。全tracked MarkdownリンクPASS。原証拠不変 |
| **W2 候補・案内を一本化** | 2026-10-17の24候補アーカイブと将来のlive候補登録を分離し、接続・結合・構造の検索用属性を追加 | 旧14+10出典SHA一致、4+6条件分離、未知情報の推測補完0。関連テストPASS |
| **W3 文書削除・統廃合（個別PR）** | D-001～D-006ごとに、元情報の固有性を判定し、現行正本へ必要な事実を移した後で**実際のGit追跡ファイル削除**を検討。旧リンクと目次を整理 | 削除する各pathのSHA・代替先・復元方法・動的参照チェック・レビュー承認・全CIを記録。不合格なら削除しない |
| **W4 実験出力・workflowの整理（別承認）** | E/W候補をrun ID・再現性・可否で厳密に分ける。旧46件と同一blob38追加pathは保全を優先 | 意味レビューとowner承認を通った候補のみ削除。禁止対象は保持 |
| **W5 全体完了監査** | 全Markdown/コード/CI/候補/EXP証拠の整合、容量・paths差分、全PR結果、復元手順を検証してmainへ記録 | **全Phase 2 CI SUCCESS、出典破壊0、真の不正リンク0、未承認削除0**。残件は明示的な未完了台帳として持ち越す |

**W0～W5はリポジトリ整理の作業番号であり、研究Phase 3とは関係ない。** 1 PR = 1主目的。マージ前は実際の最新mainを基準に再検証する。

## 5. 個別削除の必須チェックリストと復旧性

削除PRの説明には以下を全て付ける。

1. 削除対象path、サイズ、元Git blob SHA-1、元branch/コミット、実験ID・RF制約ID、削除理由。CSV台帳の進行状態を`proposed`→`reviewed`→`approved`→`removed`と更新し、`approved`は実際の所有者の承認記録に結びつける。
2. 全tracked Markdown・README・ソース・JSON・manifest・candidate index・テスト・workflowの参照、動的パス、相対パス、GitHubブラウザリンク、PRコメントからの参照を調査。一般webページ内の外部リンクは到達性を保証できない場合があるため、その限界も残す。
3. 文書を削除する前に固有の数値・訂正・検証条件・実行事実を必要な正式資料/歴史資料に移す。元のRF-Fxxx/RF-TxxxとIL・H2/H3の意味を変えない。
4. `git show <pre_delete_main_sha>:<old_path>`で復旧できることを実行確認。元blobの一致および参照先を追跡台帳と日付付き履歴に記載。Git履歴rebase/force pushや元branch削除は本計画の対象外。
5. 実験・検証一次証拠の場合、別MNA・manifest/historical runと独立して説明可能か確認し、**所有者の個別明示承認がなければ削除しない**。研究証拠の存在を単に同一Git blobだけで不要と判定しない。
6. 削除PRで回帰CI、元スナップショットSHA、2 S2P SHA、RF正式条件、候補24件、独立検証出典、reserved EXP台帳のチェックをPASS。CI失敗・参照不明ならマージしない。
7. 個別の保全判定が保留なら`deferred_retained`で終了可能。**削除件数が増えること自体を成功指標にしない**。

## 6. 変更後に必ず残す情報構造

```text
README.md                     : 現行RF-F003/RF-T005、Phase 2、成果と次工程の入口
docs/current/                 : 現行実装と未解決事項のみ（日付付きの状態）
docs/results/                 : 保存パレート／トポロジー系列、検証深度の比較
docs/methods/                 : 現行研究手法と理論成果への索引
docs/governance/              : 現行番号予約・証拠保存・評価・昇格ルールの導線
docs/archive/                 : 削除せず残す歴史成果と、削除した二次文書の復旧索引
data/catalog/                 : 2026-10-17固定の24件＋将来liveの別ビュー
data/repository_reviews/      : 削除候補・判断・SHA・承認・復旧の台帳
data/constraints/, bands.csv  : RF条件と帯域の正本（変更禁止）
data/parasitics/              : RF-F003の固定S2P原本（変更禁止）
experiments/, data/validation/: 元実行、完全ベクトル、評価・訂正の一次証拠
.github/workflows/, tests/    : Phase 2 regressionと再現性のゲート
```

**不要な過去の情報は「現行説明から削除」してよい。必要性が否定された二次文書は「レビュー後にGit treeから削除」してよい。原証拠・旧RF数値・理由の追跡に必要な歴史は保持する。**

## 7. 現時点の実施／未実施の区分

- **実行済み：** 原Step 1～5実装統合[PR #71](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/71)（mainマージ済み）、原候補24件、旧46件の保全監査、Git blob/S2Pの一致、マージ直前CI 4系統SUCCESS。
- **この計画で実行するのは計画文書・判定台帳の新設のみ。** W0の新main全追跡リンク検査、W1の文言修正、W2の構造索引、W3以降のファイル実削除は**未実施**。
- **未承認：** 個別ファイル削除、原証拠移動・削除、Git branch/tag削除、履歴rewrite、正式RF条件変更、研究Phase 3移行。
- 研究上の未達：RF-F003のIL≤0.30dB・公称H2/H3≥35dB、連続周波数極値、EM、SRF/Q(f)、全公差・実測保証。整理によってこれらの数値は改善していない。
