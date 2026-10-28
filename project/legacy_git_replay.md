# 旧Gitパス・監査・再現性の切替ガイド（Issue #185）

## 現役正本と旧パスの意味

- 現役の唯一の運用正本: `project/instructions.md`。旧 `docs/chatgpt_project_instructions.md` は移転案内。
- 現役の唯一のRF入力: `rf/constraints/registry.json`、`rf/bands.csv`、`rf/parasitics/`。
- 旧 `docs/` の現役文書6パス、`data/` のRF入力16パスは互換用Git symlink（新しい独立正本ではない）。実験・候補・台帳・過去の監査報告は `experiments/`・`data/`・`docs/` の履歴領域に残す。
- 承認済みRF-F001～003のJSON本文とS2P・帯域のbytes/実効SHAは一切変更しない。旧RF JSON内部の `data/...` は当時の**論理パス**であり、実行時は `src/lpf/constraint_versions.py` の `rf_input_file` を通じて `rf/` の実体を読む。
- 旧 `data/design_constraints.json` は **RF-F003固定** の互換リンクであり、将来のactive正式版には追従しない。現役のRF数値は必ずregistryから `load_constraint()` で読み込む。

## Git再現で注意する点

```bash
# 現行checkoutでのRF入力は新パスのGit blobを指定する。
git rev-parse HEAD:rf/bands.csv
git rev-parse HEAD:rf/constraints/formal/RF-F003.json

# 旧パスの元の証拠は移行前mainのGit treeで特定する。
git rev-parse c7968d185d5dd3d94cad47d2e1c08f2e327b5d42:data/bands.csv
git show c7968d185d5dd3d94cad47d2e1c08f2e327b5d42:data/bands.csv | sha256sum

# 移行後の HEAD:旧パス には symlinkのリンク文字列が保存される。
# Git blob SHAやgit showで旧パスを直接比較しない。
git ls-tree HEAD data/bands.csv
git show HEAD:rf/bands.csv | sha256sum
```

**重要:** `git show HEAD:data/bands.csv` は今後、CSV本文ではなくシンボリックリンクのターゲット文字列を返します。歴史manifestの `data/...` は改変せず、元コミットで `git show <元コミット>:<元パス>` と照合します。`git hash-object data/bands.csv` はチェックアウトされたシンボリックリンクの実体をたどるため、旧論理ファイルの**実際の内容**を検査できます（ただしGitインデックス内のsymlink blobとは異なる）。

## 完全監査環境とPi sparse環境

```bash
# 完全な検証環境（歴史データ・実験原本も展開）
git clone https://github.com/miyabimm/reconfigurable-rf-lpf-research.git
cd reconfigurable-rf-lpf-research
uv sync --frozen
uv run --frozen python -m unittest discover -s tests -p test_canonical_source_aliases.py -v
uv run --frozen python -m unittest discover -s tests -p test_audit.py -v
python scripts/verify_phase2_cleanup_w1_links.py --active-only

# Pi の通常環境：docs/data/experimentsは一切展開しない。
# project/README.md のpartial clone + sparse-checkoutに従う。
```

履歴の全ファイルを対象とする監査は完全環境でのみ行います。Pi sparse環境で不在の原本や台帳を「検証PASS」と扱わないでください。

## W3・W4当時の差分監査（時点固定）

以下の歴史的スクリプトは、当時の保護パスがHEADまで**変更されていない**ことを要求する差分判定を内蔵しています。

- `scripts/verify_phase2_cleanup_w3.py`
- `scripts/audit_w4_exp042_artifact_checkpoint_crosswalk.py`
- `scripts/audit_w4_exp042_missing_variants.py`
- `scripts/audit_w4_exp046_exp047_sources.py`
- `scripts/preserve_exp042_actions_artifacts.py`
- `scripts/verify_phase2_bc_exp046_lossless.py`

この条件は当時の実行結果・保護判断を検査するためのものです。今回の **所有者の承認対象である旧RFパスのsymlink化** を「無断変更」と誤判定しないよう、**歴史的監査スクリプトを緩和して現行HEADでPASSさせることはしません**。各W3/W4の報告に記録された**監査完了時点のコミットと同じtree**をGit worktreeに復元し、その時点のスクリプトを実行してください。

```bash
# <監査当時の検証済みコミットSHA> は当該監査報告／PRに記録された値を使用。
git fetch origin main
git worktree add --detach ../lpf-historical-audit <監査当時の検証済みコミットSHA>
cd ../lpf-historical-audit
python scripts/verify_phase2_cleanup_w3.py  # W3当時の作業ツリーを選んだ場合
```

**注意:** `c7968d1` はIssue #185の「移行前の元ファイル」を比較する基準であり、すべてのW3/W4監査におけるPASS確定コミットではありません。監査ごとに当時の報告で確定したコミットを選びます。誤った時点のスクリプト実行を「失敗＝歴史証拠が破壊された」と解釈しないでください。

## カットオーバー監査

`tests/test_canonical_source_aliases.py` は旧RF入力（レジストリを除く）の**移行前の元blobとの内容一致**、旧リンクの存在と解決先、旧運用指示が移転案内のみであることを検証します。レジストリは将来承認後にactive IDが更新され得るため、元blobと同一であることを恒久要求しません。

現行監査 `scripts/audit_results.py` と新EXP予約 `scripts/reserve_experiment_number.py` は `rf/` の正本を参照します。予約・研究証拠の検証は完全環境専用であり、ローカルPi sparse環境では実行しません。

本PRでは歴史EXPや固定監査報告の上書き、RF性能再計算、新規EXPは行っていません。実際のレビュー・CI結果は [Issue #185](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/185) ／ [PR #186](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/186) に記録します。
