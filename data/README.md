# data/：研究証拠・歴史的データ

**正式RF数値の現役正本は [rf/constraints/registry.json](../rf/constraints/registry.json)、周波数帯は [rf/bands.csv](../rf/bands.csv)、固定S2Pは [rf/parasitics/](../rf/parasitics/) です。**

旧 `data/constraints/`・`data/bands.csv`・`data/parasitics/` は既存コード・研究履歴の参照互換用です。今後の正式条件更新時に編集・二重同期する場所ではありません。

研究証拠・監査・候補・台帳（例：`experiment_number_registry.csv` と `experiment_index.csv`）は引き続き `data/` に原本を保存します。通常のPi Codeはこのフォルダを取得せず、全履歴検証と新EXP番号の予約は別の完全環境で行います。旧実験結果・SHA固定の証拠は遡及変更しません。
