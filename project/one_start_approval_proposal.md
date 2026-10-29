# 1-start owner承認方式案（未承認・mock限定）

親 [#213](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/213) R2/R3、子 [#214](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/214)。
**これは方式の提案であり、運用上の承認方式の確定でも、新規EXPの承認でもない。**
[運用正本](instructions.md)・[保存ポリシー](experiment_storage_policy.md)を変更しない。
`one_start_gate` は引き続き無条件に `owner_approval=not_verified` / `execution_allowed=False`。
本番solver dispatch、GitHub真正検証クライアント、実行CLIは追加していない。

## ownerに最終確認を求める方式

1. 専用の同一リポジトリ **Issueのコメント1件**を承認記録とする案。PRレビューのapprove、Issue本文、リアクション、CLI `--approve` は代替しない。
2. 実ownerの **GitHub login＋不変の数値user ID** を方式承認時に確定する。台帳のowner、コメント内の自己申告、URL、fixture、CLI入力だけでは本人確認にならない。将来の本番照合では、ownerが確認したidentityをレビュー済みのmain側で固定し、run呼出側が任意に指定してはならない。アカウント変更時もowner再確認を要する。
3. 全preflight後に表示するbinding全体と、固定されたcheckout HEADのplanned manifest・input_source（全回路/全6設定を含む）・storage_recordをownerが確認し、そのSHA-256を含む下記JSON **だけ**を自分のコメントとして投稿する案。previewが返すhashだけでは人間による計算範囲の確認を代替しない。
4. コメントの編集（同じ内容へ戻す編集も含む）・削除は無効化。承認の撤回は、同じIssueに同じbindingの `action=revoke_one_start` を投稿するか、承認コメントを編集/削除する。撤回を見つけたbindingは新しいapproveコメントでも再利用しない。別bindingで最初からレビューする。
5. 実行直前にGitHub APIから指定コメントの現状と **全コメントを全ページ**取得・再照合する案。通信失敗、ページ欠落、削除、actor/URL/本文/更新時刻/入力不一致、撤回があれば常に禁止。取得後からdispatchまでの変更可能性は残るため、ネットワーク再照合とローカルpreflightを直前に行い、使用したAPI応答・取得時刻を保存する必要がある。過去snapshotやキャッシュで許可しない。

承認本文例（`<binding SHA>` は実際の表示値、キー順も生成された文字列どおり）：

```json
{"action":"approve_one_start","binding_sha256":"<binding SHA>","proposal":"one-start-owner-comment-v0"}
```

撤回は同形式の `action` のみ `revoke_one_start` とする。mockは本文のbyte相当の文字列完全一致を要求し、前後の空白・Markdown fence・追記も承認として受理しない。
曖昧な自然文の承認や撤回を機械判定の代替にしない。自然文で撤回が示されたと担当者が知った場合も停止し、ownerへ確認する。

**未決事項:** この厳格なコメント方式・編集/撤回ルールの採否、真正ownerのlogin/数値IDと固定方法、対象Issueの選定、真正API検証・応答保全方法の最終確認。
確認前に本番許可を実装しない。方式承認と個別run承認は別で、コードマージもどちらの承認にもならない。

## 今回の読み取り専用コード

`scripts/run_phase2_shared.py` のPython関数のみ（CLI非公開）：

- `one_start_approval_request(root, experiment_id, issue_url=..., owner_actor=..., **prepare_args)`
  - 既存 `prepare_one_start` を毎回実行。完全checkout・最新origin/main・main予約owner/request・clean source・実行元byte・manifest/環境・RF/S2P/bands・完全vector/全6設定・seed・診断格子・v2予算の既存照合を迂回しない。
  - bindingにはrepository/Issue、提案actor、EXP/予約行、main SHA、source SHAと**実際のcheckout HEADを別々に**、条件ID/実効SHA、bands/input/manifest SHA、planned storage record全体SHA、uv.lock SHAを含める。manifest経由でS2P・環境、input経由で回路/完全vector/格子/予算、storage経由でselection-before-run・保存見積もりを束縛する。`manifest_sha256`等は既存canonical JSON hashであり、Git保存時のbyte hashと混同しない。
  - `owner_actor` は提案の入力にすぎず、本人確認済みではない。台帳ownerから推論しない。manifestと保存計画を変更すれば、同じcode sourceでもbindingを作り直す。
- `mock_one_start_approval(request, approval_url=..., mock_review=...)`
  - `mock_review` はテストが作る **未信頼・正規化済みデータ**。`issue_url`, `complete`, `comments` を持ち、各コメントは `id`, `url`, `actor={login,id}`, `body`, `created_at`, `updated_at` を持つ。これはGitHub APIレスポンスそのものでも、新しい本番保存schemaでもない。
  - URL/ID重複・欠落、actor、本文、編集、owner撤回、取得不完全とbinding改変を照合するだけ。`complete=True` の自己申告や時刻自体を認証しない。手作りの偽データでも `mock_match=True` にできるので、**mock一致は本人確認/真正承認を全く意味しない**。
  - 一致時も不一致時も `owner_approval=not_verified`, `execution_allowed=False`, `execution=not_run`, `candidate_promotion_blocked=True`。

この提案データを `one_start_gate` に渡して実行許可へ変更する経路はない。
テストでは隔離Git内でのみ要求を構成し、実SciPyの `minimize` を禁止して照合する。

## 本番化前の残ゲート（今回の実装外）

- R1: 対象・実効SHA・目的・全入力・研究用格子・timeout/停止条件・環境・保存先/容量・検証深度をownerと固定する。現 `prepare_one_start` の1〜3点は**診断限定**で、本番研究格子の承認ではない。timeout/停止条件等が既存planned manifestでまだ具体化されていない間は、この要求を本番run承認として用いない。
- R2最終合意後にのみR3の真正API検証を実装し、APIの返すactor数値ID/login/type（人間user）、正規URL/リポジトリ/Issue/コメントID、作成・更新時刻、全ページ完備、撤回、最新本文とbindingを検証する。API応答の真正性を呼出者提供dictで代用しない。GitHubへアクセスできない場合は常に `not_verified`。
- 実行前の再preflightとsource/実HEADの再確認、環境・入力差分検知、取得証拠保全を独立レビューする。今回の読み取り専用previewはTOCTOUを解消する本番セキュリティ境界ではない。
- snapshotは現在見えているコメントのみなので、既に削除/編集された撤回や一度も取得していない過去の撤回を検出できない。本番では既知の撤回証拠を保持し、履歴不明なら停止する運用を確定する必要がある。今回のmockは過去イベントの完全性を保証しない。
- 承認対象のsource SHAとplanned manifestを含む実HEADを分け、自己参照hashは作らない。ownerコメントはGit外に置く。mainやplanned evidenceの更新後はbindingを再生成し、古い承認を流用しない。
- R4〜R8のdispatch/保存/G0〜G5運用/独立RF判定・個別run承認とmain事前番号予約は別途必要。RF-F003/T006 adapterは未対応のまま。trialを正式条件に読み替えない。

## 再現チェック

```bash
uv sync --frozen
OPENBLAS_NUM_THREADS=1 uv run --frozen python -m unittest discover -s tests -p 'test_phase2_shared_entry.py' -v
```

既存の通常CIとPi sparse CIが同じテストを実行する。新しいworkflowは不要。
検査対象は共通の承認・入力束縛契約であり、1回のEXPの数値期待値ではない。
実GitHub owner承認検証・本物のEXP予約/実行/保存・新たな独立dense/MNA科学認定は **未実施**。
