# Phase 2：46ファイルの出典・内容レビュー（2026-10-15）

> **保全用の歴史記録（2026-10-15基準）。** 本文にある `scripts/build_reference_inventory.py`、`scripts/triage_unlinked_evidence.py`、`tests/test_triage_unlinked_evidence.py` は軽量化でmainから退役した当時の専用生成・検査ツール。元コードは [固定Git原本](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/tree/f0337963688d2a7155b8e28488d6723f2578e73e/scripts) および [旧専用テスト](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f0337963688d2a7155b8e28488d6723f2578e73e/tests/test_triage_unlinked_evidence.py) から復元できる。データ `data/research_storage_triage.csv` と46件の調査対象原本は保持する。本文の実行コマンドは当時の再現手順であり、現行mainでは直接実行できない。

PR #49～#51のmain統合後の非破壊的な再点検。基準main：dacf0dcbefe5ed191528ace190f0578ff56330fd。研究はPhase 2のまま。正式制約RF-F002、試験条件RF-T004、旧制約RF-F001等を区別し、Phase 3には移行しない。

## 調査範囲

前段の scripts/build_reference_inventory.py が review_only_no_deletion とした46追跡ファイルを対象とする。scripts/triage_unlinked_evidence.py はファイル単位にGit blob SHA-1・サイズ・内容形式/JSONキー・Git相対パスの文字列一致・Markdown相対リンクの解決・別パスにある同一blobを照合する。

- 個別の出典・保全記録：data/research_storage_triage.csv（ST-001～ST-046）
- 再生成：python scripts/triage_unlinked_evidence.py --csv artifacts/phase2_reports/storage_triage.csv --summary artifacts/phase2_reports/storage_triage_summary.json --check
- 回帰検査：tests/test_triage_unlinked_evidence.py とGitHub Actions。

**46ファイルすべての暫定処置は retain_pending_source_context_review。削除・移動は実施0件。** 文字列一致やリンクはファイルの意味の証明ではなく、過去の数値計算や物理検証の実行を追加で主張しない。Git全履歴、元チャットの外部ZIP、未追跡のローカルrunは機械的検索の対象外。同一Git blobはバイト一致を示すだけで、異なる出所とrunの役割が重複不要という意味ではない。

## 46件の実測分類とCI検証

[GitHub Actions 38594722099](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38594722099)にて、対象46件のスキャンと保存された原資料の整合検査がPASS。

| 一次調査の保管要因 | ファイル数 | 処置 |
|---|---:|---|
| 追跡文書・コードからの直接パス記載またはMarkdown相対リンク | 32 | 文脈確認まで保持 |
| 別パスにバイト同一のGit blobがある（かつ上記優先区分外） | 9 | run出所を照合するまで保持 |
| 参照・同一blobが未検出の元PR README | 5 | 原資料の説明文として保持 |
| **計** | **46** | **削除承認なし** |

直接パス文字列は26件の記載（該当20ファイル）、Markdown相対リンクは26件（該当26ファイル）で、両者の重複を除くと32ファイルがリンクあり。別パスとGit blob一致するものは全部で15ファイルだが、6件は文書リンクありと重複するため、表では残り9件を独立区分に記載する。

元source_pr38/SHA256SUMSの17ファイルをSHA-256で照合して一致。ハッシュ一覧に載らない最上位README.mdは別途SHA-256 b1b844ed35724373ba971e7b8806a58cfb1681c5e839b8c6edb358d201f0e1ce で確認した。旧R1の completed-checkpoint.zip は27,357バイト・4メンバーで、CRC検査がPASS。ZIPのSHA-256は 15f610edad60818319703747d25826ce76d84b7482bd7be1b377d7e900c775d8。**CRCとハッシュの成立は内部回路の数値正しさや実装性を証明しない。**

今後のCIでは検証内容をarchive_integrity_summary.json、個別分類をstorage_triage.csv、集計をstorage_triage_summary.jsonとして既存のPhase 2 artifactに同梱する。元記録は不変であり、新しい検証はCI履歴から別証拠として追跡する。

## 主な保全対象と個別の読み取り

### 歴史的RF条件の検証ソース

data/validation/exp016_20261012/ と exp017_20261012/ は旧RF-F001モデル等の証拠が含まれ、現行RF-F002候補の達成値として昇格させない。特に前者のpcb_followup_shortlist.jsonは内部constraint ID=RF-F001を持つ。data/validation/rft003_20261012/ と rft003_20261013/ は試験条件の探索・検証記録であり、複数のscripts/verify_rft003_*.pyから参照される。今後の回帰参照を失わないよう保全する。

### 復旧・再計算の証拠

data/validation/r1_20261012/completed-checkpoint.zip は同ディレクトリsummary.jsonから言及される復旧チェックポイント。ZIP内部と元のrun環境は今回検査していない。rf_f002_checkpoint_reproduction_20261014/の候補別JSONは集計summary.jsonが参照する検証データ。exp016_ci_replay_20261014.jsonは旧EXP-016の事後CIレポートを別形式で転記した証拠であり、別のreplay summaryとの相互代用は自動判断しない。

rf_f002_checkpoint_warmstarts_20261014、rf_f002_grid_refinement_20261014、rf_f002_unscaled_followup_20261014等のconfigはrun原位置と現在の参照文脈を保持する。たとえ複数パスが同一Git blobでも自動移動・削除はできない。

### EXP-020の元PR資料

experiments/chatgpt_topology_search/runs/EXP-020/source_pr38/ は別ブランチの候補JSON、README、検証コード、pareto CSV、SHA256SUMSを保持する履歴スナップショット。一部はEXP-020直下の保存物とGit blobが一致するが、元PRの出典構造と相対パスを保全する。

特にsource_pr38/EXP-019/EXP019-1W7L-C11.667.jsonは同一blobの別パスが見つからなかった数値候補。RF-T004試験3可変Cであり、RF-F002正式達成ではない。元資料として保管する。

### 旧候補資料

candidates/LOSS_BREAKDOWN.jsonとLOSS_REVIEW.mdは旧候補の損失解析。最新の制約別Pareto表に直接昇格させないが、技術検討の出典として保持する。

## 元PRチェックサムの適用範囲（確認済み）

元の source_pr38/SHA256SUMS は、配下EXP-016～019の**17個の追跡ファイル**に対するSHA-256を列挙する。実際には最上位README.mdも保存されているため、SHA256SUMSのみで**計18資料の全件検証済みと宣言してはいけない**。scripts/verify_archived_evidence_packages.py は17件を元ハッシュと照合し、最上位READMEを別の現在値SHA-256として明示する。元のSHA256SUMSの追記・変更は行わない。別のR1 checkpoint ZIPについてもZIP構造・CRCを検査するが、回路数値や保存時の計算環境の再現は保証しない。

## 最終整理に必要な確認ゲート

1. README・元PR・元runのSHAと数値実行環境を人手で照合する。パス文字列だけから採否を決めない。
2. ZIP・SHA256SUMS・同一内容ソースコピーの役割と参照元を確認し、復元性を損なわないか評価する。
3. 異なる原コミット・検証環境・run目的・相対パスを持つ複製は、内容が一致しても根拠保存の必要がある。
4. 将来の移設・削除・保管期間変更は、独立のPRとユーザーの明示的承認を必要とする。
5. 今回は新規最適化・独立MNA・連続帯域保証・実装検証を行っていない。

本記録は保全のためのレビューであり、削除可能なファイルを認定したものではない。
