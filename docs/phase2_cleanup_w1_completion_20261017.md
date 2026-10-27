# Phase 2 W1：現行文書・リンク整合修正の検証記録（2026-10-17）

> **W1実装済み・レビュー中。** [整理計画PR #72](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/72) → [W0監査PR #73](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/73) → [W1 PR #75](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/75)の積み上げ。2026-10-17時点でこれらはmain未マージ。**元実験ファイルの削除・移動0件、研究Phase 2継続、Phase 3未承認。**

## 1. 修正した現行入口

| 種別 | 文書 | 更新内容 |
|---|---|---|
| メイン入口 | [README.md](../README.md) | PR #67レビュー中→統合PR #71マージ済み、旧CI失敗→マージ前SUCCESS、条件別24候補への導線 |
| 現行ロードマップ | [roadmap.md](roadmap.md) | EXP-047の監査失敗と14+10候補未統合のP0/P1記述を、解消済みと残課題へ分離 |
| 現況 | [Phase 2状態](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/current/phase2_status.md)、[未解決課題](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/current/open_research_questions.md) | 既知CI成功の範囲、元manifest非標準のまま、構造検索不足と実行出典不明を保持 |
| 成果 | [結果一覧](results/README.md)、[data案内](../data/README.md) | 旧14＋新10件の[派生24候補CSV](../data/catalog/phase2_candidate_catalog_20261017.csv)を現行案内に追加。条件混合禁止 |
| 実験・スクリプト | [実験索引](../experiments/README.md)、[scripts索引](../scripts/README.md) | `--catalog`、派生生成の`--check`、旧EXP-047専用互換アダプターの用途を区別 |
| 文書運用 | [docs索引](README.md) | 整理Step 1～5統合済み、追加整理PR #72・W0を区別 |
| 原時点の歴史 | [Step 1計画](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/12b1dfd7a91ab466a6cfbbb8b4db968715e91d5f/docs/phase2_repository_reorganization_plan_20261017.md)、[Step 5検証記録](phase2_repository_step5_final_verification_20261017.md) | 原文は書き換えず、冒頭にPR #71マージ後の事実を追補 |

**現在の数値条件は[RF-F003正式制約](../data/constraints/formal/RF-F003.json)／[RF-T005試験条件](../data/constraints/trial/RF-T005.json)を区別。** H2/H3必須30dB有限格子、IL≤0.30dB、公称35dBの判定区分と、物理EM・SRF・Q(f)未検証の限界を維持する。今回数値計算は再実行していない。

## 2. EXP-004の旧リンクと原実験証拠の保護

[EXP-004の元README](../experiments/chatgpt_topology_search/runs/EXP-004/README.md)は原manifestの証拠SHAとして検査されるため、**原文を直接修正すると**`scripts/audit_results.py`が失敗することを実際のW1初回CIで確認した。

W1の対応：

- 一旦試みた旧READMEのリンク直接修正は**撤回**。Git blob SHA `639261f3e4f49c8fc7618e365c672019518b1108` を完全復元。
- 元READMEの`../../../../actions/workflows/lpf-target040.yml`が解決するよう、**通常ファイル**`actions/workflows/lpf-target040.yml`を新設。これは旧リンクの閲覧用案内であり、**実行可能なworkflowでもシンボリックリンクでもない**。実際の定義は[.github/workflows/lpf-target040.yml](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/lpf-target040.yml)、操作画面は[GitHub Actions workflow](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/workflows/lpf-target040.yml)。元READMEの旧pathから画面に自動転送されるわけではない。
- `uv.lock`、EXP-004の元manifest／README、EXP-047の元manifest／候補checkpoint、外部固定S2P、RF制約JSONは変更せず、Git blob同一性を検査。
- 元研究の説明中に残る旧RF条件は、当時の実験条件の記録として保持。2026-10-17の正式RF-F003の現況へ昇格させない。

## 3. W1専用の検証ゲート

[W1全追跡Markdownリンク監査](../scripts/verify_phase2_cleanup_w1_links.py)を新設し、**現在checkoutしたブランチ**を対象に検査する。W0の固定main時点の[監査](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/727de04781cf42e6a9aaa710dc33f0ab0fb78b6d/docs/phase2_cleanup_w0_current_main_audit_20261017.md)とは独立。

- 初回修正後の[W1 CI run 39035667408](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39035667408)：**SUCCESS**。当時の追跡ファイル1,120件／Markdown137件／リンク997件、ローカル解決840件、外部URL等未確認140件、同一文書アンカー未確認17件、**欠落したローカルリンク0件**。
- 現行statusの9入口、原RF/実験の6 blob、README内旧リンクと通常ファイルの互換案内を照合。ファイル削除0件。通常のPhase 2回帰は当初シンボリックリンクを禁止する保存予算監査で失敗したため、安全規則を緩和せず通常ファイルに変更した。
- 旧[Step 5統合検証workflow](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/5a1d32099541f6ab561401494893457bbbd10376/.github/workflows/phase2_step5_integration.yml)は過去の1,043元pathに対する**日付固定監査**であり、2026-10-17より後の正当な文書変更を許可できない構造だったため、通常のPRゲートから分離し手動`workflow_dispatch`で当時のmerge treeを再検証する形へ変更。現行のPRは[Phase 2 regression](../.github/workflows/audit.yml)＋[W1リンク専用CI](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/5a1d32099541f6ab561401494893457bbbd10376/.github/workflows/phase2_cleanup_w1.yml)で検査する。

**注意：** GitHub外部URLの到達性、文書アンカー、任意の動的生成リンクの網羅は未保証。CIは**全元実験の新しいRF独立解析・物理実測・連続帯域の保証ではない**。

## 4. 残作業と保全ゲート

- [全追跡W0監査](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/727de04781cf42e6a9aaa710dc33f0ab0fb78b6d/docs/phase2_cleanup_w0_current_main_audit_20261017.md)で7件の旧二次文書が削除候補。今回のW1は**旧文書自体を削除しない**。次のW3で固有の数値・出典を確認し、所有者の明示承認と復旧実証後に処分を検討する。
- W2の候補接続・結合符号の検索属性拡充は**未実施**。2026-10-17の固定24候補カタログを上書きしない。
- マージ対象のW1ブランチに対する**最終Phase 2 regression SUCCESS**を別途確認しなければ、main反映完了・W1全面完了とは呼ばない。

**Phase 2を継続し、Phase 3を開始しない。**
