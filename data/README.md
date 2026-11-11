# data/：実験管理台帳と移行途中の旧データ

**正式RF入力の正本は[rf/constraints/registry.json](../rf/constraints/registry.json)、[rf/bands.csv](../rf/bands.csv)、[rf/parasitics/](../rf/parasitics/)です。** `data/constraints/`・`data/bands.csv`・`data/parasitics/`の互換リンクは現役callerを確認した後に削減の可否を判断します。

## 維持する原則

- `experiment_index.csv`・`experiment_number_registry.csv`：正式EXPの実行／検証状態とG0中央番号予約に必要な台帳。新規EXP保存ゲートG0〜G5は維持します。
- 現行探索・RF評価・正式実験記録に必要な機械入力、選抜候補、独立検証根拠：実際の依存関係と将来の利用価値で選別します。
- `validation/`、`repository_reviews/`、`pareto_snapshots/`、`catalog/`、旧補助索引やZIP等：**移行途中の歴史資産**であり、恒久保管を約束しません。[Issue #397](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/397)で知見を[methods](../project/methods.md)・[results](../project/results.md)へ抽出し、不要なら実際に削除します。

歴史的な原SHA、旧manifestのpath登録、過去の数値証拠という理由だけでは保管を継続しません。ただし旧データを使う現行コード／テスト／CIがあれば、科学的機能を保って依存を解消してから削除します。元manifestを残す場合は当時の内容を遡及改竄せず、旧証拠が現行treeに揃わなくなったことを明記します。

**過去全実験の原バイト・探索履歴の再現と、今後のEXPの必要な再現性は別です。** 現行RFの条件・全6設定／28区間・H2/H3・独立MNA・SPD・受動性／電力、現行EXPの保存SHA検査は省略しません。整理前の情報が必要な場合はGit履歴・旧Issueを参照しますが、それだけで数値的な再現PASSとは扱いません。
