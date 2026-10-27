# experiments/：実験原本と完全ベクトル

[実験索引](../data/experiment_index.csv)と各`EXP-NNN/`のmanifest・候補・独立検証の証拠を正本とします。実行済み・未実行・未収束・独立検証済みを区別し、旧条件を現行正式条件の達成に読み替えません。

- [chatgpt_topology_search/runs/](chatgpt_topology_search/runs/)：実験番号別の原本と保存チェックポイント。
- [matching_limit/](matching_limit/)：旧探索ソース。現在のRF-F003用実行器として仮定しない。
- [experiment_number_registry.csv](../data/experiment_number_registry.csv)：新規EXPはmain予約・照合後に開始。
- [実験保存ポリシー](../docs/governance/phase2_experiment_storage_policy.md)：新形式を旧EXPへ遡及強制しない。

完全L/C/k、全設定の可変C、原ソースSHA・検証格子・独立MNA・制約IDを確認します。後日の検証overlayは、元実験の実行環境を自動的に証明するものではありません。

[結果一覧](../docs/results/README.md) ／ [データの案内](../data/README.md)
