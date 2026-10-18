# Step B 第1弾：旧リポジトリ監査workflowの退役案（2026-10-18）

> 状態：**draft PR上での退役差分・提案のみ。mainでは未実施。** 研究はPhase 2、Phase 3未承認。ユーザー指定の「最終結果・考察・再現情報を残し、軽量・明快にする」方針を適用する。対象パスを明示した**バッチ削除の承認後**にmainへ統合する。

## 第1弾の対象と残す機能

- 基準main：`5a1d32099541f6ab561401494893457bbbd10376`（Step A統合後の軽量スモークCI PASS）。
- 旧整理・証拠監査workflow **17件**を現在のtreeから退役する**案**。旧監査で生成したデータ、CSV、レポート、実験・評価コード、固定原本は**削除・上書きしない**。
- [PR #91統合監査](../.github/workflows/phase2_bc_wave1_consolidated.yml)は**手動`workflow_dispatch`専用に変更**。旧W2/W3/W4の5検査、EXP-046のバイト復元、Git原本照合コードをそのまま保持。常時CIは[軽量24テスト](../.github/workflows/audit.yml)のみ。番号予約workflowも保持。
- 残りの過去実験・探索workflow28件は**今回変更しない**。第2弾で現行コードと過去Gitコミットからの再実行を短く整理する。
- ベースから17件の退役を実施した場合、workflowは**48→31件**。**mainへマージするまでは48件のまま**。

## 元ソースの復元表（削除対象17ファイル）

全パスの共通接頭辞：`.github/workflows/`。元YAMLはGitコミット`5a1d32099541f6ab561401494893457bbbd10376`から復元でき、以下は元ソースのGit blob SHA（Git SHA-1）である。

| 元ファイル名 | 元blob SHA |
|---|---|
| `phase2_cleanup_w0.yml` | `27fd34d7fd68b7c1eeea9fa58dad384cd575a267` |
| `phase2_cleanup_w1.yml` | `f2172a220eb34e30f3bbc27af57fed190bd66872` |
| `phase2_cleanup_w2.yml` | `e0edee51a0684dad390482f97d661549a69ff623` |
| `phase2_cleanup_w3.yml` | `17ce8d94355c4fb326d9f927671864a56a3eb771` |
| `phase2_cleanup_w4.yml` | `92be916443ea979f690c5fcc66197fff89c9f827` |
| `phase2_cleanup_w4_run_forensics.yml` | `bac06b67ec111ef456ffb0abb785080cd435d58c` |
| `phase2_step1_repository_inventory.yml` | `79429a8917f91edf989c1dc7a9786f870b6da464` |
| `phase2_step3_candidate_catalog.yml` | `3a8b77f811a61043247113ee4e3081a24edb5658` |
| `phase2_step4_history_inventory.yml` | `8f8b82bc118c62138357cc3fecef746c0c53cbc4` |
| `phase2_step5_integration.yml` | `b103d5d6ad41103847e645239de6be22826ea66d` |
| `phase2_w4_exp042_crosswalk.yml` | `c2cb776bba727b9fcc64f05a6ed255266ffd69f4` |
| `phase2_w4_exp042_missing_variants.yml` | `d2ba86955cb6c5eb2bb9b043479e3bb997750bb7` |
| `phase2_w4_exp046_exp047_provenance.yml` | `e06d4b890173fe46dd00564ec25a5d1733ab7dcb` |
| `phase2_w4_preserve_artifacts.yml` | `c91af49f11927c2232352a094ad651e61272e154` |
| `phase2_w4_replay_dependencies.yml` | `dc58f56fbff456d8fc3fed60f6595c2824c81a40` |
| `phase2_w5_post_cleanup_disposition.yml` | `4ecd6fe0103393905bf8d44b7d91d572fe47d970` |
| `phase2_w5_readonly_closure.yml` | `b9050e26c8ae87ba955306e04127fc5d46fed1ff` |

例（ローカルcloneで原処理・引数・実行環境を確認する）：

```bash
git show 5a1d32099541f6ab561401494893457bbbd10376:.github/workflows/phase2_w4_exp042_crosswalk.yml
git show 5a1d32099541f6ab561401494893457bbbd10376:.github/workflows/phase2_w5_readonly_closure.yml
```

これにより元の`run`コマンドと当時の定義をそのまま取得できる。再現時は固定コミットのソースをチェックアウトし、制約ID・seed・入力SHA・実行済み/未実行を明示する。退役したworkflowのGitHub UIでの再起動ではなく、**必要なコマンドを手動実行**する設計とする。

## 簡易検証と限界

1. 新PRの軽量スモーク（RF-F003/試験RF-T005、固定S2P、6設定、候補等）がPASS。
2. Markdownで退役先を指す**5文書・6相対リンク**は、元の歴史コミットへの不変リンクへ差し替える。リンク切れがあれば修正する。
3. main統合前のdiffを読み、**削除は上表17 YAMLに限定**、正本CI・番号予約・実験原本・数値制約・過去のGit refに変更がないことを確認。
4. 同SHAの重い監査全件PASSや外部システム利用の不存在証明は**新たに要求しない**。ユーザー説明で外部システムは存在しない。古い出典の新しいRF数値的成立は主張しない。

**所有者の明示承認が必要なのは本第1弾の17パス一括退役。** `続けて`による準備の指示と、対象を指定した削除承認・main統合は分ける。このPRはdraftのまま保留できる。Git履歴をrewriteせず、旧28 workflow・raw実験原本・正式RF条件は維持する。
