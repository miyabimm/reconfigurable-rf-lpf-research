# Phase 2 W4 — EXP-042未選別3変種の元Artifact復元と採用判断ゲート（2026-10-18）

> **作業状態：** [前回のW4照合](phase2_w4_exp042_artifact_checkpoint_crosswalk_20261018.md)に続き、現行mainに選別済みcheckpointのない`cf2`、`both`、`pcb_cf2`について、元Actions ZIP内に保全済みの元JSONを**バイト同一**で取り出す。新規RF数値探索／再検証は行わず、Phase 2を継続。原本削除0件、旧46件保全。

## 出典と区別

- 基準main：`c1b874c1e240ac3fedfeaa67064783f0918ed9a2`（PR #85マージ後）。
- 保存済みの10 ZIP／19ファイル：[元ZIPのSHA・Base64記録](../data/repository_reviews/w4_exp042_actions_original_zip_b64_20261018.json)、[各メンバSHAの照合個票](../data/repository_reviews/w4_exp042_member_crosswalk_20261018.csv)。
- [読取専用復元監査](../scripts/audit_w4_exp042_missing_variants.py)では元ZIPのSHA-256・CRCと6メンバのSHA-256／bytesを照合する。対応する`experiments/.../checkpoints/cf2.json`、`both.json`、`pcb_cf2.json`が存在しないことを検査し、**架空の選別済みcheckpointを生成しない**。
- 元レコードを再利用しやすくするため、読み出した**元の6 JSONファイルを一切変更せず**`data/repository_reviews/w4_exp042_recovered_original_members_20261018/`へコピーし、元run・Artifact ID・ZIP SHAを[固定メタデータ](../data/repository_reviews/w4_exp042_missing_variant_source_review_20261018.json)へ記録する。ファイル名の異なる正規化版・候補登録・新パレート点と混同しない。

## 評価のゲート

- 保存された`selected.vector` 29成分を全件数値・有限値として確認する。ソースJSONの`dense`に報告された最悪IL・H2/H3・結合L行列最小固有値を**元の観測記録**として抽出する。
- H2/H3の30dB必須値の判定は、**元JSONに報告された有限格子値の再比較だけ**に限定する。S2PをロードしたRF解析、28周波数帯の再サンプリング、独立9×9 MNAの再計算は今回行わない。
- `*_independent.json`の元バイトと報告字段を保持するが、単に存在することを独立再実行した根拠にはしない。
- **採用価値は保留または補足比較候補**として扱う。H2/H3の有限格子記載が満たされても、旧checkpointと完全同条件・評価格子・ソースSHAを照合し、新たな独立再検証を実施するまでは正式候補台帳・Paretoスナップショットを変更しない。
- 既に選別された35dB候補と別runの`target_35.json`、`cf1`の異なるstageについても、旧ZIPとGitの両方を保持する。[前回の段階差の個票](../data/repository_reviews/w4_exp042_member_crosswalk_20261018.csv)が主出典。

## 未実施と承認境界

実行値・結果は専用Actionsでチェックし、真正な元JSON6件と固定メタデータをGitで保管する。既存39workflow、EXP-042元ソース・manifest・checkpoint、正式RF-F003の制約・固定寄生S2P、旧46件、候補台帳は**無変更**。新たな削除承認は0件。RF最適化・独立MNA・EM・Q(f)/SRF・公差・実測も未実施であり、Phase 3には進まない。
