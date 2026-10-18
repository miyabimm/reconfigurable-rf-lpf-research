# W5後続：T-001～010・全workflow・実験証拠の現行整理判定（2026-10-18）

> **状況：Phase 2・非破壊レビュー。** [W5総合監査](phase2_w5_readonly_closure_20261018.md)をPR #88でmainへ統合後、推奨順序に従って文書現況→workflowの利用リスク→研究原本の削除可否→最終CIを順番に確認した。**今回の新規原本削除0、workflow停止・削除0、RF計算0、Phase 3未承認。**

## 1. 現行README等と旧T-001～T-010台帳の突合

起点main **`486a2761661cbd3da16be97041568e50b9547f00`**（[PR #88](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/88)）。旧[W0削除候補台帳](../data/repository_reviews/phase2_cleanup_deletion_candidates_20261017.csv)の`not_started_unapproved`は**策定時の状態**である。履歴記録を上書きせず、[W5後続の10件個票](../data/repository_reviews/w5_followup_T001_T010_status_20261018.csv)に現在のblob SHA・確認語句・状態を保存。

- **T-001～007：** README／ロードマップ／現行課題／results／data／scripts／experimentsの入口は、RF-F003正式／RF-T005試験、旧14＋新10＝24候補、非標準EXP-047 manifestの索引専用アダプターとCI履歴の区別を反映している。単に古い計画の`not_started`を現況扱いしない。
- **T-008：** EXP-004元READMEの`../../../../actions/workflows/lpf-target040.yml`はGitHub Actions画面用の**歴史的なWebルート形式**で、Git追跡ファイル`actions/workflows/`内に存在する相対リンクではない。実際のworkflow定義は`.github/workflows/lpf-target040.yml`に存在し、元READMEにはその相対ソース参照もある。**Web画面上で古い相対URLが遷移できるか未検証**。コード中に表示される元実験説明を黙って書き換えず、将来必要なら外部Webルートの解決確認と個別文書修正を行う。
- **T-009/010：** 当時の計画・Step5報告には後日付のPR #71マージ追補があり、元の未マージ・Draft記述は日時を限定した過去の証拠である。追加整理の現況は本報告／W5を参照する。
- **変更実績：** 当初の10ファイルのうちW5時点で9ファイルのGit blobが策定時から変わっている。元EXP-004 READMEだけが同一blob。現時点で確定した文書の追加修正事項は0、**UIルート到達確認は1件保留**。

## 2. 旧workflowを含む全定義の個別分類

[47 workflowの個票](../data/repository_reviews/w5_followup_workflows_47_20261018.csv)は、2017ではなく**2026-10-17の旧39 workflow API履歴**と、2026-10-18の本PR作業ツリーに実在するYAMLを対応づけた。**39件は旧W4台帳に掲載済み、後続に追加された8件の監査workflowを含めてPRヘッド47件**（PR #88統合直後のmainは46件）。過去の履歴数と現在の実行履歴を混同しない。

| 静的検出・役割 | 確認数 | 判定 |
|---|---:|---|
| 現在のYAML | **47** | **全件保持** |
| 2026-10-17履歴台帳にもあるもの | **39** | 過去のAPI記録。現在の有効性は未確認 |
| 後続追加（本監査workflow含む） | **8** | 保全CIが多く、削除提案ではない |
| `workflow_dispatch`の記述あり | **46** | 手動再実行の潜在依存。未使用の証明ではない |
| `git push`／`contents: write`などの字句的書込検出 | **5** | Git状態を変え得るため高優先の個別保全対象 |
| Artifact／resume関連の字句的参照 | **38** | 元run再現・成果物参照の可能性。内容未実行 |

書込系の5件を現行ソースで確認した：`exp042_manifest.yml`／`exp043_manifest.yml`は研究用の固定ブランチへのcommit/push、`phase2_cleanup_w0.yml`と`phase2_step1_repository_inventory.yml`は出典の記録／書込権限、`reserve_experiment_number.yml`は新規EXP番号予約の重要操作を持つ。特に予約workflowは研究開発に必要なため**退役対象としない**。他のworkflowも、必要性と影響・実際の実行権限・dynamic dependencyを確かめるまで削除しない。字句検出は危険の手掛かりであって操作を本監査で実行していない。

## 3. 実験証拠のファイル別判定

[W4個票225件の後続分類](../data/repository_reviews/w5_followup_evidence_225_20261018.csv)に、各元Git blob SHA・ファイルサイズ・参照状態・元manifestの静的ヒット・固定S2Pや動的パス処理の手掛かり・EXP-046/047の訂正系列・再実行／削除承認の有無を保存。

- **225件全件：保持**。その内数であるEXP-046の35件と正式RF-F003のEXP-047の96件の原本・訂正前後を保持。
- 先行[W4非破壊監査](phase2_cleanup_w4_evidence_workflow_review_20261017.md)でE-001 `data/validation/`266件とE-002 元実験run 481件、合計**747件**を棚卸し済み。これは過去の固定時点の値であり、225件＋747件を合算して972件の別原本とは扱わない。
- [EXP-042の元10 ZIP](../data/repository_reviews/w4_exp042_actions_original_zip_b64_20261018.json)／19member、選別checkpointとの対応、未選別3構成の元6 JSONがSHA・CRC検証済みでも、全元runをRF-F003の共通solverで再演できたことは示さない。
- **退役可と確証されたファイル0件**。元実行SHA・seed・環境／branch依存や中断再開の用途が不明なものを削除候補へ勝手に昇格させない。E-001、E-002、W-001、W-OTHERの所有者削除承認は0件。

## 4. 最終判定と持ち越し

現在確認済みのソフトウェア範囲で**「古い説明の現状不一致」についてはほぼ解消**。ただしT-008のGitHub UIルート到達性は未検証。旧workflowは47件を個別分類し全件保持、W4元225件も保持とした。**リポジトリ整理の監査・出典整理は実施済みだが、研究実験や旧workflowを消す作業は未承認・未完了**と明記する。

最終的なCIでは以下の区別を維持する。リンク・Git SHA・既存Phase 2回帰のSUCCESSは**全設計空間のRF最適性、連続域の極値、物理Q(f)/SRF/EM、温度・公差・実測、EXP-046/047再実行可能性**を証明しない。正式RF-F003と試験RF-T005の結果は混合せず、Phase 3には移行しない。
