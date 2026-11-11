# experiments/：正式実験記録と移行途中の歴史資産

実験の登録・状態は[中央実験索引](../data/experiment_index.csv)と[番号台帳](../data/experiment_number_registry.csv)で管理します。新規正式EXPは[保存ポリシー](../project/experiment_storage_policy.md)のG0〜G5に従い、代表候補の完全L/C/k、全6設定Cv、RF条件ID・実効SHA、格子・ソース情報・実行と検証状態を記録します。正式／試験／旧条件、実行済み／未実行／未収束／独立検証済みを区別します。

現存する[EXP別runs](chatgpt_topology_search/runs/)には、旧数値、checkpoint、ソース写しなどの歴史資産も含まれます。[Issue #397](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/397)で研究上の知見を[methods](../project/methods.md)・[results](../project/results.md)へ統合し、現行研究・正式記録に不要な旧資産は削除します。現行treeに過去全証拠が揃うことを完成条件としません。旧manifestを残す場合、削除済み証拠に合わせて遡及編集しません。

歴史的な[matching_limit/](matching_limit/)のコードは現行RF-F003実行器ではありません。現在の探索入口と検証手順は[project/README](../project/README.md)を参照します。
