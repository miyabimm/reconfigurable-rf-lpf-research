# Phase 2 W4：225原本の再実行依存とEXP-042 Actions成果物の存続監査（2026-10-18）

> **状態:** W4の追加・非破壊レビュー。研究・RF数値計算を再実行する作業ではない。実験の削除承認0、workflow削除承認0、今回の削除0。研究Phase 2を維持し、Phase 3には移行しない。

## 対象と出典

- main起点 `fd8c3fb4dc9f972dfd3d646009facb25cf344a0b`（[W4前回のPR #82](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/82)統合済み）。
- [前回のW4個票225件](../data/repository_reviews/w4_unindexed_225_review_20261017.csv)、[39 workflowのAPI可視履歴](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/5a1d32099541f6ab561401494893457bbbd10376/data/repository_reviews/w4_workflow_runs_20261017.csv)、[46件の保全対象](../data/repository_reviews/step4_retention_46_20261017.csv)を**入力**とし、旧出典SHAを照合する。
- [読み取り専用依存・構文監査](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/5a1d32099541f6ab561401494893457bbbd10376/scripts/audit_phase2_w4_replay_dependencies.py)は全225パスのGit blob SHA/bytes、同じ実験groupの元manifestとREADMEでの**文字列参照（証拠ではなく手掛かり）**、元workflowが元パス全体を直接参照するか、元sourceのS2P取得・動的path構築・checkpoint処理の有無を分類する。
- `.py`原本に限りPython AST、`.js`原本に限りNode.jsのmodule構文をチェック。**構文検査は実行・数値再現を意味しない**。Code Modeの`tools`／元S2P／seed／環境依存やトップレベル構文の実行形態は別途確認する。歴史的in-chatソースを強制実行しない。
- [6件のEXP-042 Actions runとArtifactの実在メタデータ](../data/repository_reviews/w4_exp042_actions_artifact_metadata_20261018.json)はGitHub Actionsコネクターが**2026-10-18に返した情報**を固定保存。これは実際のzipダウンロードやzip内成果物検証、GitHub全workflowの完全な履歴照会ではない。

## EXP-042 Actionsで新たに確認した観測値

| workflow | run ID | 観測されたjob | API可視Artifact | 状況 |
|---|---:|---|---:|---|
| `exp042-rf-t005-verify.yml` | [38999427474](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38999427474) | verify: success | **0件** | 成功jobでも現在見える成果物の有無は別 |
| `exp042_area.yml` | [38999677183](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38999677183) | 3 job: success | **3件** | 面積別成果物 |
| `exp042_rf_t005.yml` | [38999677194](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38999677194) | 30/35dB・独立MNA job: success | **3件** | 7,001点検証名称のArtifactを含む（内容未検査） |
| `exp042_manifest.yml` | [38822654644](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38822654644) | manifest: failure | **0件** | 失敗の原因・元runを保全 |
| `exp042_passband_q.yml` | [38999310277](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38999310277) | evaluate: success | **1件** | Q/loss診断 |
| `exp042_pcb.yml` | [38999677216](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38999677216) | 3 job: success | **3件** | PCB別成果物 |

計**6 run／10 Artifactメタデータ**を保存。ここで可視だった10 Artifactは`expired=false`で、全件の**有効期限は2027年1月15日（UTC）**。ただし期限はGitHub側で変更され得る。容量はコネクターが返した圧縮Artifactサイズであり、実験の生出力やGit pack保存容量とは別。**この監査ではダウンロード0件／RF計算再実行0件**。

**特に重要:** Run 38999677194は名称上「独立MNA」を実行したjobがSUCCESSであることを示すが、今回そのJSON内容や回路解析を独立に再評価していない。EXP-047の原manifestは局所in-chat計算であり、Actionsでの探索再実行がないと元文書に明記されている。RF-F003とRF-T005、元実行と後日の検証を混ぜない。

## 元出典・構文検査の実行済み内訳

[CI run 39088382917](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39088382917)で**225ファイル／2,046,501bytes**を確認し、旧46件のGit blob SHA照合もPASS。

| 検査 | 観測件数 | 正しく解釈する範囲 |
|---|---:|---|
| 元manifest中の**パス全文**と一致 | 25 | 実際の読み込み成功を証明しない |
| 元manifestで同名ファイルに言及（弱い手掛かり） | 25 | 同名異実体の場合もある |
| 同じ実験のREADMEでbasename言及 | 92 | 説明文であり実行依存とは限らない |
| 元39 workflowのYAMLにパス全文 | 20 | workflowの静的参照。動的生成パスは対象外 |
| ソース中に固定S2P文字列 | 60 | 利用する処理が実行されたとは限らない |
| GitHub fetch tool名などの文字列 | 59 | 元のCode Mode/tools環境が必要になり得る |
| 動的なパス構築らしい文字列 | 72 | 依存の可否は実行トレースで追加確認する |

元manifestにより、**正式RF-F003のEXP-047 96件、試験RF-T005のEXP-042～046計128件**と区別できた。残り1件はEXP-047旧manifestアダプターの独立した`data/validation/`資料で、グループmanifestによる自動条件帰属を行わず`unknown`とした。

**構文だけの安全な確認：** Python原本27件はAST解析PASS。JavaScript原本59件のうち25件はNode.jsモジュール構文PASS、残り**34件は非同期関数ラッパーでコンパイルPASS**。どちらも評価関数本体を呼ばず、元S2Pを読まず、RF計算・独立MNA・トポロジー探索を**実行していない**。構文PASSは過去の探索を再現した証明ではなく、原本破棄を許可する根拠でもない。

## 削除可否に関する判定基準

1. **225件のGit blob全保持**：台帳が指すパスごとに元blob SHAとbytesを照合し、旧46件も照合。元データ、正式RF制約、固定S2P、元manifest、元checkpoint、旧sourceは変更しない。
2. **構文上の再生可能性 ≠ 数値の再現実行**：Python/Node構文チェックPASSでも、元runの依存・環境・ツール・seed・Git mainとの差異を解消できていなければ「再実行確認済み」にはしない。syntax FAIL/未対応でも原本の無用性は証明されない。
3. **Artifactの保存は有限**：Actionsの成功履歴、Artifactの存在、期限、内容を区別。消去前には必要なArtifactを完全性検証・SHAと出典付きで長期保存する工程が必要。既存のGit原本をそのまま残す。
4. **旧文書削除許可を流用しない**：E-001/E-002/W-001や旧46件には個別のowner承認が必要。静的参照0・旧run・同じGit blob・GitHub履歴復元可能というだけで実削除しない。

## 検証ステータス

- GitHub Actions job/Artifact**メタデータ取得は実施済み**。元6runを個別指定して照会し上記10件を[固定JSON](../data/repository_reviews/w4_exp042_actions_artifact_metadata_20261018.json)に保存。
- 225件の元SHA・manifest/workflow依存・ソース構文の**読み取り専用CIを実行済み**：[W4 39088382917](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39088382917) はSUCCESS。[固定225件CSV](../data/repository_reviews/w4_replay_dependency_225_20261018.csv)、[実行済み要約JSON](../data/repository_reviews/w4_replay_dependency_summary_20261018.json)として現在のGitで保存。後続CIでも元CSVとのbyte-for-byte一致を検証する。
- 過去Actions Artifactの**zip実体の取得・保存と独立MNA再実行は未実施**。物理Q(f)・SRF・EM・実測・公差の達成も証明しない。

**W4の実験/旧workflow削除は依然として未承認。Phase 2継続。**
