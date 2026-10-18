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

## 実施済みの原本復元・有限格子の相対比較（2026-10-18）

元ZIP3件から6 JSON（**合計23,460 bytes**）をGitに**バイト同一**で保存。各元ファイルは[Git復元ディレクトリ](../data/repository_reviews/w4_exp042_recovered_original_members_20261018/area_cf2.json)（入口例）に置き、[個別SHA256・元run・ベクトル・報告済み数値・判定JSON](../data/repository_reviews/w4_exp042_missing_variant_source_review_20261018.json)に紐付けた。`experiments/.../checkpoints/`の存在しない3つの選別checkpointを新規作成していない。

| 元変種 | chip面積 | 既存同面積パレート候補 | 元の最悪IL | 既存候補最悪IL | 元−既存IL差 | H2/H3の元記録 | 元独立MNA報告 |
|---|---:|---|---:|---:|---:|---|---|
| `cf2` | 5.333 | `T005_4L_A5p333_EXP042` | 0.813554271 dB | 0.811306586 dB | **+0.002247686 dB** | 最小30.020dB以上 | 84点、PASS |
| `both` | 4.667 | `T005_4L_A4p667_EXP042` | 0.822191335 dB | 0.819564515 dB | **+0.002626819 dB** | 最小30.020dB以上 | 84点、PASS |
| `pcb_cf2` | 5.333 | `T005_4L_A5p333_EXP042` | 0.812800269 dB | 0.811306586 dB | **+0.001493683 dB** | 最小30.020dB以上 | 84点、PASS |

**計算は元JSONの保存値と既存[2026-10-17パレート記録](../data/pareto_snapshots/rf_t005_rf_f003_20261017.json)を比較しただけ**。3つの元構成はすべてSLSQP成功記録、29要素ベクトル、28区間×1,001点の有限格子レポート、独立9×9MNA 84点の`pass=true`レポートを持つ。いずれも元の暫定最悪IL目標0.8dBは未達。IL/面積の2目的のみに限り、既存同面積の採録候補より最悪ILが悪く、**新しい保存パレート点の追加根拠はない**。調波余裕、相互結合物理性、Q(f)/SRF/EM等も含む全目的での一律の劣位は意味しない。研究原本は歴史証拠として保持する。

**元run番号で確定したstageの差：** 保存元`target_35.json`はActions **38999677194**、選別`EXP042-35m005`は選別台帳上 **38774357292**。保存元`area_cf1.json`はActions **38999677183**、選別済み`cf1.json`は **38775558755**。**同じrunの異なる最適化stageと断定できず、少なくとも別Actions runの記録**である。前回の29ベクトル成分差・メトリック差の確認を維持し、両方保持。

対応する分析・3構成の数値スクリーンと履歴出典の確認は、[専用CI](../.github/workflows/phase2_w4_exp042_missing_variants.yml)でGit固定の原本と突合する。**本作業の独立RFソルバー実行回数は0**。

## 未実施と承認境界

実行値・結果は専用Actionsでチェックし、真正な元JSON6件と固定メタデータをGitで保管する。既存39workflow、EXP-042元ソース・manifest・checkpoint、正式RF-F003の制約・固定寄生S2P、旧46件、候補台帳は**無変更**。新たな削除承認は0件。RF最適化・独立MNA・EM・Q(f)/SRF・公差・実測も未実施であり、Phase 3には進まない。
