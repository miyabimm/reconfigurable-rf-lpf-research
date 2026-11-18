# 正式EXPの外部管理と旧Campaignの扱い

Issue #448で旧Campaign実行／専用ゲート・保存APIを撤去した。旧schema2 Campaignの再実行・変換は提供しない。保存済み正式EXPの原本・制約・台帳を変更しない。必要な履歴は[固定Git履歴](legacy_git_replay.md)から参照する。

RF-T009専用の[逐次開発CLI](../scripts/README.md#rf-t009-開発run)は開発用のraw生成のみ。`run.json` はGit外の開発Runローカル台帳であり、G0の正式予約、G2認定、正式保存のいずれでもない。**新形式の正式Campaignは未接続・保留**。

正式EXP管理は引き続き[運用正本](instructions.md)と[保存ポリシー](experiment_storage_policy.md)の手順でPi Codeと独立スクリプトが行う。

- G0: [番号予約](../scripts/reserve_experiment_number.py)とmain読戻し。開発Runからは呼ばれない。
- G1: [外部checkout検証](../src/lpf/search/checkout.py)の `verify_checkout(root, constraint_id, expected_sha256, ...)` は完全なcheckout、fresh main、clean tree、ソース・import起点、RF実効SHA、bands・固定S2Pの証跡を検査／返却する。番号・manifest照合、実行可否判断は別工程。
- G2: 新方式の正式実行は本Issueの対象外。
- G3〜G5: [汎用正式保存](../src/lpf/experiment_preservation.py)と[保存監査](../scripts/audit_new_experiment_storage.py)のmanifest、台帳、保存原byte/SHA、Git読戻し、削除適格性を維持する。旧Campaign専用の未完了保存は汎用経路から確定しない。外部の `cleanup_eligibility` は、manifestに登録・remote mainで原byte確認済みのC inventory（raw相対パス→SHA256）と現物を照合する。分類完了・再開不要の確認も必須。可否判定のみで、rawは削除しない。
