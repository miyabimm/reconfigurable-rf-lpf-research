# Phase 2 W3：旧二次文書7件の出典・固有情報・削除可否レビュー（2026-10-17）

> **後続の実施追補：** 以下の「削除承認0件、実削除0件」はPR #79の承認前監査時点の記録。その後、所有者はD-001～D-004の削除を承認し、[歴史文書統合資料](archive/w3_consolidated_documents_20261017.md)に固有事実・元blob・復元手順を保存して4旧pathを現行treeから削除した。D-005～D-007は保持。旧判定は当時の証拠として残す。

> **判定：7件すべて現在のtreeに保持。削除承認0件、実削除0件。** 本PRはレビュー台帳と検証ゲートを追加する段階で、所有者の個別承認による削除PRではない。研究はPhase 2を継続し、Phase 3には移行しない。

## 1. 起点・実施範囲

- **レビュー基準main**：`731e901e79cfa367fd06b4350844c6987b30caa5`（PR #72→#73→#75→#78を統合後）。
- [運用指示正本](chatgpt_project_instructions.md)、[W0固定main監査](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/727de04781cf42e6a9aaa710dc33f0ab0fb78b6d/docs/phase2_cleanup_w0_current_main_audit_20261017.md)、[W1リンク修正](phase2_cleanup_w1_completion_20261017.md)、[W2構造索引](results/phase2_topology_search_20261017.md)、[整理・削除計画](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/phase2_repository_cleanup_and_deletion_plan_20261017.md)に従う。
- GitHub上のmainにある7文書の本文とGit blob SHAを個別に取得し、W0の削除候補台帳と照合した。判定の機械可読正本は[W3個別台帳](../data/repository_reviews/w3_document_disposition_20261017.csv)。
- W0で判明したリンク元・静的参照と、mainに現存する[archive目次](archive/README.md)、[governance目次](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/governance/README.md)、[methods目次](methods/README.md)の参照を確認。**main現行全追跡treeの網羅的な逆参照スキャン・Git履歴全体・動的path・外部URLは本書のGitHub取得だけでは検証していない**。W3 CIで現行文書リンクと対象blobを検査する。
- 旧W0の「静的流入0」は**旧時点の旧監査値**であり、現在の参照不存在を意味しない。

## 2. 個別判定

| ID | 元ファイル・Git blob SHA-1（先頭8桁） | 独自性・削除障害 | W3判定 |
|---|---|---|---|
| D-001 | [repository_reorganization_plan.md](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/88562135dae2edf8ba7763aa529181c05f7c1ded/docs/repository_reorganization_plan.md) `1c0673ed` | 2026-10-12当時のR1～R5、R2内部シャントC一般化、P4-A探索対象、未実装ゲートが固有。単なる現況重複ではない。 | **条件付き保留**：日時付きR1～R5の処理状況と未実施項目を移記し、リンク更新・個別承認後に再判定 |
| D-002 | [research_result_governance.md](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/88562135dae2edf8ba7763aa529181c05f7c1ded/docs/research_result_governance.md) `946049b8` | 初期9→13候補の経緯、strict/tolerance/reported/historical区分、6実験の未連結manifestなど、訂正履歴の説明が残る。現行RF-F003正本と当時のRF-F002を混同禁止。 | **条件付き保留**：旧ルール・台帳推移・元訂正を出典付きで収録後に再判定 |
| D-003 | [phase2_actions_ci_repair_20261017.md](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/88562135dae2edf8ba7763aa529181c05f7c1ded/docs/phase2_actions_ci_repair_20261017.md) `4c45f2b0` | EXP-044/046 manifest修復、旧CI障害run `38993047810`、複数PRの修復・統合・run URLとSHAの時系列が固有。 | **条件付き保留**：インシデント記録の永久保存とリンク更新後に再判定 |
| D-004 | [repository_storage_audit_20261014.md](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/88562135dae2edf8ba7763aa529181c05f7c1ded/docs/repository_storage_audit_20261014.md) `2918391b` | 旧main `73c4f19b3b1264beeb5e8cbb2764ae3f82fb4f57`の707 tracked files/8.30 MB、実行時診断144件/約2.35 MB、同一blob34組・余分38path、分類方法が時点固有。 | **条件付き保留**：分母・日時・対象SHAを伴う監査履歴に移記後に再判定 |
| D-005 | [phase2_storage_pareto_review_20261015.md](phase2_storage_pareto_review_20261015.md) `7d97c8a5` | RF-F002／RF-T004の**13候補・8比較群**パレート表を含み、現在の24候補カタログとは条件・保存時点が異なる。535ファイル保全区分・旧CI成果も残る。 | **保持推奨**：表の全行と条件比較・出典を失わない移管実証までは削除対象外 |
| D-006 | [r2_handoff.md](r2_handoff.md) `ff757983` | EXP-015で4候補の保存値を各周波数区間7001点で再現、72周波数点/候補の3方式照合。最大利得差`3.17e-15`、電力収支残差`3.36e-17 W`。元独立監査JSONへ連結。 | **保持推奨**：独立MNAの方法と当時の合否判定を含むため、別の証拠レビューが必要 |
| D-007 | [p4_a_scope.md（2026-10-26退役前の固定版）](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/fd2db0d2bc0bdb2cd54d9c6c55e191da1180fdae/docs/p4_a_scope.md) `e254a785` | P4-Aの**内部ノード≤4、固定枝≤8、計算面積≤6**、`matching_only`、HV 0.4～12 nH限定・HQ未探索の境界は歴史的ソルバcoverageの出典。 | **保持推奨**：runner/manifestの当時の探索限界の突合まで保全 |

### 保存すべき重要な旧数値の例

**D-005（旧13候補のPareto）**：正式RF-F002の30dB strictは面積5.333／IL 0.381014dB、35dB strictは面積5.333／0.460180dBおよび面積9.333／0.378798dB。旧RF-T004 35dB strictには面積13.667／IL 0.297114dBがある。**正式RF-F003の成果ではない**。個々の候補IDと残りの比較群は原文で保管し、要約への転記だけで原文と同等の保存と判断しない。

**D-006（EXP-015）**：3可変CのHV/HQ候補は当時のRF-T002接続条件に適合し、2可変C候補はRF-F001／RF-T001／RF-T002に適合しない。4候補とも旧有限格子のH2/H3最低30dBは満たすが35dB公称とIL≤0.30dBは未達。元の[EXP-015監査JSON](r2/EXP015_COMMON_MODEL_AUDIT.json)を必ず保つ。

## 3. 現行参照と復元ゲート

- [歴史資料索引](archive/README.md)は**7件すべて**へのリンクを持つ。[運用管理索引](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/governance/README.md)にはD-001～005のリンクがあり、[方法索引](methods/README.md)にはD-006/007のリンクがある。[docs目次](README.md)にはD-005の現行リンクもある。これらは削除の前に解消必須。
- 削除前の復元元は `git show 731e901e79cfa367fd06b4350844c6987b30caa5:<source_path>`。**GitHub上で旧時点のblobが現存することを確認済み**だが、当該コマンドを現在のGitHub runner上で実行した確認は本書の作成時点では未実施。W3 CIでread-only照合する。
- Git履歴へのforce push/rebase、実験originalの改変、固定S2P/条件JSONの書換、旧46件の削除・移動は対象外。古いGit履歴が存在することだけでは現在のリンク互換性や研究の再現性を保証しない。
- 全追跡Markdownのローカルリンクの現在値は[W1検証スクリプト](../scripts/verify_phase2_cleanup_w1_links.py)のPR CI実行により別に判定。外部リンク、アンカー、PRコメント中の参照、動的コード内のパスは完全な保証外。

## 4. 追加作業と削除許可条件

1. D-001～004はそれぞれ固有情報を完全に移した**独立の削除審査PR**を準備し、現行docsの索引とコード参照を更新する。
2. D-005～007は数値比較・独立検証・探索スコープの**原資料保持**を基本とし、代替資料との等価性が実証できた場合のみ再審査する。
3. 各pathの元blob SHA、実削除前main、復旧 `git show` の実行結果、破損リンク0、RF/EXP証拠の不変、CI成功をPRに記録する。
4. **所有者からpathを特定した削除承認を得るまで、`owner_delete_approval=not_granted`とする。**「整理を続ける」という一般指示を7ファイルの個別削除承認とは扱わない。
5. 現在のW3成果は**審査・保全のみ**。新規RF解析、EXP番号の予約、Phase 3移行、Git treeのファイル削減を実施していない。最終W5完了監査の成立も主張しない。

## 5. 検証状態

- **実施済み**：main上の7ファイルの読取・blob SHA照合、W0既存台帳との突合、現行目次のリンク確認、固有事実の抽出。
- **PR CI実行後に確定**：7ファイルの現在blob不変と旧commitからの復旧可能性、旧46件の保護、全追跡Markdownリンク整合、Phase 2回帰。
- **未実施**：全Git履歴・外部URL・PR会話の逆参照の網羅、削除PR作成、削除承認と実削除。
