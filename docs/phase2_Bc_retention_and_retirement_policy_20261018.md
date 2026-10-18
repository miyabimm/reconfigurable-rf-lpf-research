# Phase 2：Bを基本・C寄りのGitHub保管／workflow退役方針（2026-10-18）

> **ユーザー選択：「C寄りのB」で進める。** これは削除対象を探して個別審査を進める方針の承認であり、**元実験ファイル・workflowの個別削除承認ではない**。本PRは優先度付けと出典台帳のみ。削除・停止・RF数値再計算なし。Phase 2継続、Phase 3未承認。

## 対象・監査境界

起点main \`42c1d91c7dcff5dff14c24fa0c0010737040b5d3\`（PR #89統合後）。最新の[運用正本](chatgpt_project_instructions.md)、[W5後続の47 workflow・225元出典の調査](phase2_w5_followup_disposition_20261018.md)、[GitHubのみの実験結果保存方針](experiment_result_storage_policy_proposal_20261015.md)を基準とする。旧W0～W5の固定CSVは歴史的な実行結果であり書き換えない。

固定した個票：

- [workflow 47件の「保持・退役審査段階」CSV](../data/repository_reviews/phase2_Bc_workflow_retention_proposals_20261018.csv)
- [元実験・validation証拠225件の「保全・集約審査段階」CSV](../data/repository_reviews/phase2_Bc_evidence_screening_225_20261018.csv)
- [集計・第1波・未承認状態JSON](../data/repository_reviews/phase2_Bc_retention_proposal_summary_20261018.json)

今回の「C寄り」とは、**不必要な新規中間データをGitに大量保存しないこと、古いworkflowの停止・除去可否を優先審査すること**である。元原本については削除可能性を実証したものだけを、後日の**対象ファイルごとの承認**と別PRで扱う。

## 1. workflowの5区分（47件すべてに個別判定）

| 区分 | 件数 | 処遇案 |
|---|---:|---|
| **A：必須運用** | **2** | \`audit.yml\`と\`reserve_experiment_number.yml\`。現在の回帰・EXP番号予約機能を保全 |
| **A/B：代替CI整備まで維持** | **7** | W1文書・候補台帳・履歴・Artifact・W4再現性・W5保全等の現行検査を保持。機能同等性を比較して統合検討 |
| **B：監査機能の重複整理** | **1** | \`phase2_cleanup_w4.yml\`の検査対象を現在のW5保全ゲートと突き合わせる |
| **C1：先行退役審査** | **9** | 過去のW0/W2/W3・Step1/5・W4再計算を伴わない一度限りの監査用CIなど。**まだ退役を承認したわけではない** |
| **C2：再実行代替後に退役審査** | **28** | EXP-042/043/044の19専用workflow、旧LPFなど9専用workflow。コード再実行・元run出典・独立MNAの代替が確立するまで保全 |
| **合計** | **47** | 現段階の削除・無効化ともに**0** |

2026-10-17の[39件Actions API調査](../data/repository_reviews/w4_workflow_runs_20261017.csv)は現在までの完全な履歴ではない。古い実行回数が0件のworkflowも未使用と断定しない。書込兆候5件には\`exp042_manifest.yml\`、\`exp043_manifest.yml\`、\`phase2_cleanup_w0.yml\`、\`phase2_step1_repository_inventory.yml\`、番号予約があり、副作用と元ブランチの復元を個別に点検する。

**第1波：次に個別退役の可否を精査する5件（削除未承認）**

1. \`phase2_cleanup_w2.yml\`：旧W2索引監査と現行候補台帳CIの機能差を比較。
2. \`phase2_cleanup_w3.yml\`：W3文書保全が既存のW5確認と重複するか比較。
3. \`phase2_w4_exp042_crosswalk.yml\`：19member対Git照合の独立保全機能を特定。
4. \`phase2_w4_exp042_missing_variants.yml\`：元ZIP6member復元性チェックの代替先を特定。
5. \`phase2_w4_exp046_exp047_provenance.yml\`：131原本SHA/正式RF-F003候補出典照合の代替先を特定。

削除可能とする前に**現行/手動起動、他workflow・branch・docsからの参照、元run replay、Git SHAでの復元、合格判定の他CIへの移管、GitHub Actions required check、実行権限・書込副作用、後日の個別owner承認**を確認する。単に「いままで動かしていない」では削除不可。元のworkflowファイルそのものを別場所へ二重コピーする代わりに、元Git SHA・commitと復元手順を個票で固定する。

## 2. 元データ225件の3区分

| 区分 | 件数 | 保管判断 |
|---|---:|---|
| **A：元出典を保全** | **128** | 固有コード、元checkpoint/ベクトル、直接workflow依存、EXP-047 legacy overlay、当時の解釈文書。重要な元Q割当・容量損失の訂正前後を保全 |
| **B：記録の等価性が未検証** | **81** | 数値・診断JSON。条件/実行stage/独立検証/固有ベクトルを照合するまで現物保全 |
| **C候補：集約可能性の優先審査** | **16** | 一見、中間batch/retune/予備探索の数値JSON。**削除候補確定ではなく集約の調査対象**。計271,406非圧縮bytes、削減可能容量ではない |
| **合計** | **225** | **全件まだ保持** |

225件内のGit blob SHA完全一致の別pathペアは**0組**。単純な同一バイト削除効果はこの標本では見込めない。先行W4のE-001+E-002計747件は**この225件を含む時点固定の広い母集団**。現在の全tracked file数と今回の削減額を示すものではない。

**C候補の具体的な注意：** EXP-047の\`round2_margin_retune_20261017.json\`には複数の完全パラメータベクトル等、EXP-046の\`bridge_cap_relocation_batch{0,1,2}_results.json\`には配置ごとの探索結果・評価件数と28×5/31の報告値がある。形容上「中間」「batch」でも独自の探索証拠を持つ。**これらを現時点で再生成可能・不要と判定していない**。元の独立84点MNAや28×1001点検証も全batchに一律実施されたとは主張しない。

**第1波：実験中間データの集約可能性を調べる3件（削除未承認）**

- \`experiments/chatgpt_topology_search/runs/EXP-046/bridge_cap_relocation_batch0_results.json\`
- \`experiments/chatgpt_topology_search/runs/EXP-046/bridge_cap_relocation_batch1_results.json\`
- \`experiments/chatgpt_topology_search/runs/EXP-046/bridge_cap_relocation_batch2_results.json\`

これらは同じRF-T005試験範囲での3分割探索の**別データ**であり、現状では一切削除しない。各batchの\`eval_count\`、各配置\`results\`、完全ベクトル、30/35dBゲート、参照source/manifestを**出典付きで一本の構造化結果へ損失なく集約できるか**をまず検証する。圧縮・一本化が成功しても旧runに必要な元pathがあるなら保持。後日個別承認を得るまでは原本を守る。

## 3. 将来の新規実験に適用する保存方針

- **必須A：** formal/trialを分離したconstraint IDとSHA、6設定/28区間、固定S2P SHA、元実験番号・run/seed・コード/環境、完全L/C/kおよび全設定Cvベクトル、評価格子/結果、独立検証・訂正の原出典、有限格子である旨。
- **条件付B：** 多様なトポロジー、パレート非劣解、35dB近傍、重要な負例・反例・停止/再開点、代表的なworker異常ログ。破棄前に役割・復旧手順・代替データSHAを確認。
- **通常Git保存しないC：** 新規runの全iteration dump、無差別な全workerログ、純粋なキャッシュ、完了後再開に不要な空lock、同じ内容の再計算可能な格子波形。ただし**原JSON・元checkpointの形式や出典を事後的に書き換えない**。新runのmanifestで保存対象と集約方針を開始前に決める。
- **保管先はGitHubのみ**。期限付きActions artifactを永久アーカイブの代わりにせず、未保全の原ZIPを先に消さない。旧manifest/branch/tag/historyを勝手に削除しない。

## 4. 明確な削除承認ゲート

各対象の**元path、サイズ、原Git SHA、実験・制約ID、参照関係、代替出典、出典バイト／数値同等性、元run replayの要否、Gitからの復旧方法、CI・文書影響**をまとめた削除候補PRを個別に提示する。所有者の明示承認なしに原本・workflowの削除・停止・移動・Git refの変更をしない。

**現時点：** 提案された退役審査対象はworkflow **9+28件**、研究元データの集約審査対象は**16件**。これは**削除承認件数0、削減実績0件/0 bytes**と明確に区別。コードや独立RF検証を新規実行していない。Phase 2のみ。
