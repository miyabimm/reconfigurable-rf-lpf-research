# Phase 2：現行ステータス（2026-10-17）

> **基準：** 2026-10-17の[統合PR #71](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/71)マージ後main `055b222c79c73c7fbeacb19383f21c1da0625195`を歴史起点とし、[#72/#73/#75/#78](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/78)統合後main `731e901e79cfa367fd06b4350844c6987b30caa5`の文書整理状況を反映。このページは閲覧用要約であり数値正本ではない。以後の変更は[ロードマップ](../roadmap.md)と[制約レジストリ](../../data/constraints/registry.json)で確認する。
>
> **フェーズ：Phase 2継続。Phase 3への移行は所有者の明示的承認まで禁止。**

## 2026-10-18：追加試験RF-T006（条件追加のみ・探索未実施）

**新しい承認済み試験条件** [RF-T006](../../data/constraints/trial/RF-T006.json) は正式RF-F003をベースに、可変C最大2枝を維持したまま、**全6設定で外部端子間3～6GHzの減衰≥20dB**を必須化する。既存のUL/DL・H2/H3最低30dB/公称35dB・固定S2P・RF部品制約は不変更。1MHz刻み・端点含む3,001点/設定の有限格子で判定する。現行のF003/T005パレート値は旧条件の既存結果でありRF-T006合格値ではない。**新しいRF-T006探索は未実行**。Phase 2継続、Phase 3はユーザー明示承認待ち。

## 現行条件と評価方法

| 区分 | 内容 |
|---|---|
| 正式条件 | **RF-F003**。正本は [registry.json](../../data/constraints/registry.json) の active ID が指定する [RF-F003.json](../../data/constraints/formal/RF-F003.json) |
| 試験条件 | **RF-T005**。RF-F003基準で可変Cの最大独立枝数だけ2→3に緩和。正式成果と混同禁止 |
| 信号経路 | 入力の固定S2P → LPF本体 → 出力の固定S2P、外部50Ω源・60−j40Ω負荷 |
| 周波数 | [6設定・不連続28区間](../../data/bands.csv)、外部端子間のIL／UL H2・H3を評価 |
| 可変C | RF-F003最大2枝、RF-T005最大3枝。各0～3pF、Q35 |
| 結合上限 | chip隣接強結合・PCB-Lペアとも`|k|≤0.10`。他の物理条件は正式JSON |
| 必須／公称 | **H2/H3≥30dBが必須**、35dBが公称目標。最悪IL目標≤0.30dB。chip面積はILとの二目的比較軸 |
| S2P出典 | 固定された入力／出力モデル由来のS2Pであり、実測ではない |

[正式仕様の概要](../specification.md) ／ [運用指示正本](../chatgpt_project_instructions.md)

## 2026-10-17に保存されたbest-foundパレート

| 条件 | 区分 | 非支配候補 | 代表的面積・IL範囲（保存済み候補内） | 元証拠 |
|---|---|---:|---|---|
| RF-F003 | **正式**・最大2Cv | **4件** | chip面積4⅔～6⅔、worst IL 0.882647～0.833188 dB（4L） | EXP-047 |
| RF-T005 | **試験**・最大3Cv | **6件** | chip面積3～6、worst IL 0.944268～0.805149 dB（3L・4L） | EXP-042/043/045 |

**判定：** 既存に保存された局所・有限探索候補集合の中で、H2/H3必須30dBに有限格子適合する**観測済み非支配点**。全設計空間のパレート最適性の証明ではない。**両条件ともIL≤0.30dB、公称H2/H3≥35dBは未達**。数学的極値・実装物理性能・全公差の成立は未保証。

詳細値、各候補の完全L/C/k・全6設定Cvと元checkpoint、独立検証の範囲は [結果の入口](../results/README.md) → [パレート元レポート](../pareto_rf_t005_rf_f003_20261017.md) → [不変JSON](../../data/pareto_snapshots/rf_t005_rf_f003_20261017.json) を参照する。

**EXP-047の記録訂正：** 4GJM候補について原独立検証JSON中の`chip_area=6`は記録誤り。正しい面積は**6⅔**。元証拠を改変せず、訂正根拠を明記して閲覧用表示に使用する。

**候補の回路構造検索：** [W2構造索引](../results/phase2_topology_search_20261017.md)（PR #78）は既存24件からの読み取り専用派生。新たなRF解析結果ではなく、旧14件の接続情報は未抽出、磁気結合の物理実現性は未検証。[W3審査](../phase2_cleanup_w3_document_review_20261017.md)でD-001～D-004の元path4件を承認済み削除し、固有事実は[歴史統合資料](../archive/w3_consolidated_documents_20261017.md)に保存。D-005～007は保持。

## 実行済み・未完了の境界

- **実行済み：** EXP-042～047等の既存局所数値探索と、候補ごとに保存された有限格子／独立MNA検証。条件別の2026-10-17パレートスナップショットを記録。検証格子・深度は実験ごとに異なるため、全候補の同一深度検証を保証しない。
- **未実行・未保証：** RF-F003対応の共通`full_lpf`ソルバー／ローカルrunnerによる網羅的な探索を完了した実績はない。連続帯域極値、Q(f)、SRF、EM、組立・温度・公差、実測、物理面積は未保証。S2Pは手書き回路のモデル由来。
- **過去の数値：** RF-F002/ RF-T004のILや旧Q・可変C条件を、現行正式RF-F003の達成値として使わない。[履歴索引](../historical_results.md)。
- **実験番号：** [番号予約レジストリ](../../data/experiment_number_registry.csv)ではEXP-042～047が予約済み、EXP-018/019は永久欠番。新規実験は必ずmainへ事前予約して照合する。今回の文書整理は新規EXPではない。
- **回帰CIの確認済み範囲：** 旧run `39015048662` はEXP-047 manifest欠損で失敗した**当時の記録**。その後[統合PR #71のPhase 2 regression](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39028160775)は325件の単体テストを含め**マージ前SUCCESS**。原EXP-047 manifestは非標準のまま保全し、[出典固定の索引専用アダプター](../../src/lpf/legacy_manifest_adapter.py)を用いて照合する。元の実行SHA／seed／環境は未復旧であり完全な再現性を主張しない。マージ後mainのpush CIはこのページでは未確認。

## 次に確認する場所

[現在の研究・実装課題](open_research_questions.md) ／ [ロードマップ（履歴併記）](../roadmap.md) ／ [RF-F003再ベースライン計画（2026-10-16当時の未実行表示を含む）](../rf_f003_phase2_rebaseline_plan_20261016.md) ／ [データ正本の案内](../../data/README.md)
