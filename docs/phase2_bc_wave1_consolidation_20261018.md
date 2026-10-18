# Phase 2：C寄りBの第1波 — 旧5監査CIの共通実行とEXP-046の可逆保全（2026-10-18）

> **実施状態：** PR #90で固定したBを基本・C寄りの整理方針に基づく第1波。旧workflow退役・実験原本削除は未承認であり、このPRでも**削除0件・停止0件**。Phase 2継続。Phase 3未承認。

## 第1波1：5つの旧監査workflowの検証を同じCIで実行

[新しい共通監査workflow](../.github/workflows/phase2_bc_wave1_consolidated.yml)で、元の5つの検証を**同じコマンド・固定CSV/JSON対照を保持して実行**する。旧5workflow自体は一切変更せず、引き続き独立CIとして走る。

| 元workflow | 共通監査で行うチェック |
|---|---|
| `phase2_cleanup_w2.yml` | W2トポロジーのPython unittest、派生索引・報告のバイト一致 |
| `phase2_cleanup_w3.yml` | 承認済みD-001～004の元Git履歴復元、D-005～007保全、W1リンク |
| `phase2_w4_exp042_crosswalk.yml` | 元ZIP 10件／19内部ファイルのSHA/CRCと29ベクトル・出典差、固定CSV/JSON照合 |
| `phase2_w4_exp042_missing_variants.yml` | 元ZIPから復元するEXP-042の6 JSON、元run/変種、SHA・元ZIP検証 |
| `phase2_w4_exp046_exp047_provenance.yml` | EXP-046/047の131原本SHA、Q割当／容量損失訂正、正式RF-F003 4候補の出典 |

[共通監査初回CI](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39101712307)は**SUCCESS**。ただしこれは**検査内容の技術的重複・統合実行に成功した**ことを表す。GitHub上の必須ステータスチェック名、pathフィルター、個別workflowの手動実行インターフェイス、artifactの名称・運用監視まで完全同等であるとは断定しない。**旧5件を直ちに削除できる証明ではない。**

退役前の未解決確認事項：保護ブランチのrequired checks/下流参照、新workflow単独での検証全件再現、Actions履歴への依存、パス変更時のtrigger被覆、アップロード成果物の利用者、GitコミットIDから旧workflow定義を復元する手順、所有者による5件それぞれの明示的削除承認。

## 第1波2：EXP-046の元3件を正確に復元できる圧縮集約

元RF-T005記録は3つのbatchで合計**10の異なる配置・各30成分ベクトル**を持つ。元の評価回数は130,481 + 124,259 + 169,493 = **424,233**（記録値の合計であり今回の新規最適化ではない）。

[可逆集約の検査ツール](../scripts/verify_phase2_bc_exp046_lossless.py)は元のJSONを**パースして正規化せず、実バイト列を1ファイルずつzlib(level9)で圧縮**する。それぞれの元パス、Git blob SHA-1、SHA-256、非圧縮・圧縮バイト数、配置名、元評価回数、Base64符号を保持する。[可逆保存用JSON](../data/repository_reviews/phase2_bc_exp046_bridge_lossless_archive_20261018.json)から個々の元JSONをバイト完全一致で復元できることを検査する。**原本を置換しない。**

| 情報 | 元の3ファイル | 可逆保存用データ |
|---|---:|---:|
| 元JSON非圧縮の合計 | 34,818 bytes | — |
| zlib圧縮ストリームの合計 | — | 6,615 bytes |
| Base64・全復元メタデータを含むUTF-8 JSON | — | **11,692 bytes** |
| 完全復元する固有ベクトル | 10配置×30成分 | 全10配置を元JSONとして復元可能 |
| 元実験のサンプル格子 | 28×5探索・28×31スクリーニング | 元記録をそのまま保存 |
| 変更後配置の独立MNA／28×1001 | **未実施（元sourceにpending）** | 新規実行していない |

**注意：** この集約を追記した段階では元データも残るのでGitの現在treeはむしろ増加している。「34,818−11,692＝23,126 bytes」は**将来元3件を本当に消すことが承認され、他の変更がなかったと仮定した現在tree上の概算差**であり、Gitの履歴・pack・Actions容量の実削減値ではない。承認前に原本を削除せず、既存の分割ファイルを参照する研究runnerや履歴資料を変更しない。

[初回発見CI](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39101712307)では元JSONの計10配置・424,233評価・ビット単位のzlib復元を検証して、Gitへ可逆JSONを固定した。[固定済み元JSONの再復元CI 39101884013](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39101884013)は**SUCCESS**となり、`EXP046_LOSSLESS_COMMITTED_PASS`で3元JSONへのバイト完全一致を確認した。パレート候補の新規登録、物理Q(f)/SRF/EM、公差、独立MNAの新規計算はしていない。

## 削除判断の現状

- 旧5つの監査workflow：共通CIでの検証が動作。ただしステータス・trigger・成果物・履歴の運用同等性は未検証。**退役は未承認**。
- EXP-046元3 JSON：完全バイト復元できる圧縮コンテナあり。ただし元ファイルパスの動的依存・新CIでの再復元・独立数値検証の必要性を評価し、**対象3ファイルを個別承認するまでは保持**。
- このPRでは**元実験・元workflow・RF制約・候補台帳を変更しない**。Git履歴削除・ブランチ削除も行わない。

最終的に、個々の元ファイルパス・保存byte/SHA・検証CI・復旧手順を列挙した**削除承認専用PR**を別に作る前提であり、このPRのマージを削除承認と解釈しない。
