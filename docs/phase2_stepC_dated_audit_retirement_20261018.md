# Phase 2 Step C：旧一時監査スクリプトと専用テストの整理（第1弾・2026-10-18）

> **2026-10-18時点の状態：draft PR上の整理案。** 一時的な履歴監査13スクリプトとそのうち2件の専用ユニットテストを整理候補とする。Phase 2継続、Phase 3移行なし。

**2026-10-26更新:** 旧ローカル探索の専用マネージャーは別途退役。以下は当時の一時監査コード整理に関する履歴であり、現行のローカル実行入口を示さない。

## 背景と保持方針

2026-10-18 Step B完了後のmain `f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3`を基準とする。`scripts/`は74追跡ファイル、`tests/`は97追跡ファイル。日常CIは24の代表テストへ縮小済み。

- **削除候補**：2026-10-17のW0～W5、旧リポジトリ再編Step 1～5、GitHub Actions利用履歴、当時のブランチ/容量棚卸し用の一回限りの監査。すべて過去の固定commitに対するレビュー処理であり、RF-F003/T005回路の数値解析器ではない。
- **保持**：`src/lpf/`、`experiments/`、RF制約と帯域・固定S2P、候補の完全ベクトル、全一次結果、`scripts/experiment_id_registry.py`・`scripts/audit_results.py`・`scripts/build_phase2_candidate_catalog.py`、重要な独立RF数値検証器と現行6モジュール24テスト。
- **既存の手動PR #91原本検証を壊さない**：`.github/workflows/phase2_bc_wave1_consolidated.yml`が呼ぶ`verify_phase2_cleanup_w3.py`、`verify_phase2_cleanup_w1_links.py`、`audit_w4_exp042_*.py`、`audit_w4_exp046_exp047_sources.py`、`verify_phase2_bc_exp046_lossless.py`、`audit_phase2_issue93_consumers.py`等は本バッチの対象外。
- **旧Git historyの保全**：元のGit blobと実行入口は次表のmain確定SHAからいつでも取得できる。`git bundle`バックアップ器`backup_complete_git_history.py`とその復元テストは保持。
- 元結果CSV・JSON・W0～W5の考察・履歴報告は**変更・削除しない**。対象が古いからといって新しいRF-F003で数値実行済みと主張しない。

## 第1弾で退役を提案する全15パス

| 固定版の元ファイル | 元Git blob SHA |
|---|---|
| [`scripts/audit_phase2_cleanup_w0_links.py`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3/scripts/audit_phase2_cleanup_w0_links.py) | `b7393c1e71219f48ca23f8e54cb8412e1ce4e0d0` |
| [`scripts/audit_phase2_cleanup_w0_tree.py`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3/scripts/audit_phase2_cleanup_w0_tree.py) | `78f09f3949a24d403962bd6c1f02eca790f59628` |
| [`scripts/audit_phase2_cleanup_w4.py`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3/scripts/audit_phase2_cleanup_w4.py) | `dbf90d57b675223421413b8c9a131623f8181397` |
| [`scripts/audit_phase2_w4_replay_dependencies.py`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3/scripts/audit_phase2_w4_replay_dependencies.py) | `ffe7f447cefa0e671fe153a67d820fb823b33ec4` |
| [`scripts/audit_post_w5_cleanup_disposition.py`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3/scripts/audit_post_w5_cleanup_disposition.py) | `62f03edb29b1bdfa4bad28fc4202d1e692176f6f` |
| [`scripts/audit_repository_reorganization_step1.py`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3/scripts/audit_repository_reorganization_step1.py) | `a744db535849c707e3fd4fb12a8d3f159a572112` |
| [`scripts/audit_repository_reorganization_step4.py`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3/scripts/audit_repository_reorganization_step4.py) | `cb5be714f6af2c24a132a466a56c018fbebb2de1` |
| [`scripts/review_phase2_w4_action_runs.py`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3/scripts/review_phase2_w4_action_runs.py) | `3cc454ffd75bc7074a272ede41bdcf8b8cd3b84d` |
| [`scripts/review_phase2_w4_unindexed.py`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3/scripts/review_phase2_w4_unindexed.py) | `a0494ec6daf93cdf820b252d849be093d4720ae0` |
| [`scripts/verify_repository_step5_integration.py`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3/scripts/verify_repository_step5_integration.py) | `9a5561a72aa641385fbf17378611f278539d6f70` |
| [`scripts/verify_phase2_w5_closure.py`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3/scripts/verify_phase2_w5_closure.py) | `b4d531f2fe63cc0867b696906dfdf21b4012f6e1` |
| [`scripts/audit_branch_retention.py`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3/scripts/audit_branch_retention.py) | `146703ec32e8f4be9a7f7d0bac5a1437e72f97b5` |
| [`scripts/audit_git_storage_budget.py`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3/scripts/audit_git_storage_budget.py) | `b557dd1fb33b94e7d93e2a5f7763109d562888d6` |
| [`tests/test_branch_retention.py`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3/tests/test_branch_retention.py) | `d1a836ed56acbe2609b2fc518deccf311a31138b` |
| [`tests/test_git_storage_budget.py`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3/tests/test_git_storage_budget.py) | `61d6158678503128b85767bee43245b55ab265e5` |

**必要時の取り出し方法：**

```bash
git show f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3:scripts/audit_phase2_cleanup_w0_tree.py
git show f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3:scripts/verify_phase2_w5_closure.py
git show f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3:tests/test_branch_retention.py
```

旧版の実行が本当に必要な場合は、別の`git worktree`でこのcommitをチェックアウトし、当時の`uv.lock`と入力CSVを使って元のコマンドを確認する。これらの監査は**履歴固定の日付やGit tree構造を前提**とし、現在のmainでそのまま走らせるべきではない。元の実行コマンド・CLIオプションは上記固定版の各`__main__`、または対応する退役済みworkflowから確認する。

## 実行・受入ゲート

1. 削除差分は**スクリプト13＋テスト2**だけで、現行解析／検証・実験原本・manifest、固定S2P、正式RF-F003と試験RF-T005に変更がない。
2. 既存の軽量スモーク（24テスト）をPR-headのGitHub ActionsでPASSさせる。削除バッチに関係する残存テストのimportがないことを確認する。必要があれば**このバッチに限り全テストを手動で1回**実行する（常設CIは増やさない）。
3. 歴史文書の旧スクリプトへのリンクは削除されたmainパスではなく、元Gitコミットへの参照で復元可能にする。`scripts/README.md`のW0リンクは固定履歴リンクに変更。
4. 目標は`scripts/` 74→61、`tests/` 97→95（ファイル数）。**自動的な一律削除をしない**。旧RF-T003解析器／EXP-017の重要な独立検証テスト等は後続判断まで保持。
5. **所有者から、この15パス一括削除への明示承認を受けるまでdraft PRからmainへ統合しない。** 一括承認されてもGit履歴rewrite・原実験の削除・Phase 3への移行は含まれない。

### 未実施事項

この文書の追加・PR作成だけで元のRF計算を再実行したことにはならない。Step D（成果と文書の集約）や、その他の旧数値検証器の削減は今回のPR対象外。
