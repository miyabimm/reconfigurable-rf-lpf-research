# Pi Codeの通常作業範囲

Piの通常作業は `project/`・`rf/`・`src/`・`scripts/`・`tests/`・`.github/` とリポジトリ直下ファイルで行う。
`docs/`・`data/`・`experiments/` は通常ローカルに取得しない。過去のEXP再検証・全研究証拠の監査は、これらを明示的に取得した**別の完全検証環境**で行う。

```bash
git clone --filter=blob:none --depth=1 --sparse https://github.com/miyabimm/reconfigurable-rf-lpf-research.git
cd reconfigurable-rf-lpf-research
git sparse-checkout set --cone project rf src scripts tests .github
```

- 現行の正式・試験RF入力は `rf/constraints/`、全28区間は `rf/bands.csv`、固定S2Pは `rf/parasitics/`。
- `rf/constraints/registry.json` の `active_formal_id` が現行正式版。承認済みJSONは**上書きしない**。新正式条件は所有者承認後に新IDとして追加し、active指定を変更する。trialは自動昇格させない。
- 不変の旧RF JSON内の `data/...` は**保存時の論理パス**であり、`src/lpf/constraint_versions.py` が新 `rf/` 実体へ解決する。JSON内容・実効SHA・S2P SHAは維持する。ファイル欠落やSHA不一致時は失敗させる。
- 各EXPの原manifest、重要証拠、番号台帳は従来の `experiments/`・`data/` に保全する。通常のPi sparse環境で新EXPの番号予約・保存監査が可能とはみなさず、実行前承認を別に取得する。
- Piの最低限の作業ツリーテストは `.github/workflows/pi-sparse-rf.yml`、全履歴・保存監査は通常の完全CI／個別実行とする。CI PASSは新RF性能の科学的保証ではない。
