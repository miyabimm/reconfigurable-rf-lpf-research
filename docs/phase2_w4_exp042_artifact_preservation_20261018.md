# Phase 2 W4：EXP-042 GitHub Actions Artifactのバイト保全（2026-10-18）

> **目的：** 期限付きのEXP-042のActions成果物を保全可能な形にし、元run・Artifact ID・ZIP全体のSHA-256・ZIP内memberのSHA-256を結び付ける。研究はPhase 2継続。実験原本・workflow削除0。RF最適化・独立MNAの再実行ではない。

## 適用範囲と区分

起点mainは`eced0bd838f62781f4c17be93241749afa0a21f9`（PR #83統合後）。[2026-10-18の6run・10Artifactメタデータ観測](../data/repository_reviews/w4_exp042_actions_artifact_metadata_20261018.json)を選定一覧とする。対象は以下の旧RF-T005 EXP-042 Actions runの成果物であり、新しい正式RF-F003の最適化・性能達成値に読み替えない。

- Run [38999677183](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38999677183)：面積variantのArtifact 3件。
- Run [38999677194](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38999677194)：RF-T005目標30/35dBと独立7,001点検証名のArtifact 3件。
- Run [38999310277](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38999310277)：passband-QのArtifact 1件。
- Run [38999677216](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38999677216)：PCB variantのArtifact 3件。
- Run [38999427474](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38999427474)：ジョブはSUCCESSだがAPI可視Artifact 0件。
- Run [38822654644](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38822654644)：manifestジョブFAILURE、API可視Artifact 0件（失敗の出典を保全）。

## 保全方式・検証

[専用読み取りスクリプト](../scripts/preserve_exp042_actions_artifacts.py)で元のGitHub Actions REST APIから固定10 Artifact IDのZIPを取得、ZIP内全memberのCRC・パス安全性とSHA-256、ZIP全体のSHA-256を検査する。**一時URLだけでなくZIPの実体をGitへ保全**するため、各ZIPの元バイト列を無損失Base64として単一JSONに格納し、元run ID／Artifact ID／name／期限メタデータと紐付ける。ZIPバイト列は元Base64をデコードすれば復元でき、一般的なzip展開は本スクリプトの検査後に利用する。

実体の取得・保全確定先：`data/repository_reviews/w4_exp042_actions_original_zip_b64_20261018.json`（実際にZIPを取得しGitへコミットした場合のみ存在）。Git上の[検証ワークフロー](../.github/workflows/phase2_w4_preserve_artifacts.yml)では、保存したZIPとmemberのSHA-256を**認証・ネットワークなしでも再照合**する。内容の意味・正しいRF判定値・独立MNAの計算結果は、ZIPハッシュが一致しても**未再解析**として扱う。

**旧metadata上の期限：2027年1月15日（UTC）**。これは2026-10-18にGitHubから取得したメタデータであり延長・短縮され得る。ZIP保全後でもGitHub Actionsを使ってRFソルバーを再実行したとは主張しない。元実験ファイル・旧46保護元証拠・制約・S2Pはすべて残す。

## 実行状態

- GitHub APIメタデータ：既に取得済み（6run、10Artifact）。
- **元ZIPのダウンロード・バイトSHA確定、Git保全および独立復元検証：専用PR CIで実行してから結果を記録する。**
- 数値再計算／独立回路検証／製造・EM評価：未実行。
- E/W削除承認：0件。実削除：0件。

**W4の個別削除可否は未決。Phase 3は未承認。**
