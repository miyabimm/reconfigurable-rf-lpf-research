# 旧Stage 4：候補記録と条件別Pareto（履歴）

**この文書は#189/#191当時の限定APIに関する記録であり、現行の実行入口ではありません。** #343 D3で旧`candidate_records`/`candidate_audit`/`post_search_journal`は撤去済み。現行の候補と保存は[Campaignガイド](campaign_workflow.md)、[保存ポリシー](experiment_storage_policy.md)、[results.md](results.md)を使用する。

## 残す設計上の教訓

- 比較候補は完全vector（全L/C/Q、符号付きk、端子/role、物理列、全6設定Cv）、RF条件ID/実効SHA、bands/S2P、source/dirty、格子・objective・検証深度を固定する。
- 同じ条件のParetoでも**solver収束／部品・SPD適合／strict finite-grid／独立MNA・電力／35dB公称／連続帯域保証**は別の資格。record内のPASS表示だけで候補を昇格しない。
- `finite_grid_eligible`は採用格子での有限判定のみ。閾値直下を丸めてPASSとせず、旧1001点の外部参照値と粗格子の候補を同列比較しない。
- 旧C1/C2のseed・attemptリプレイは合成/mock・限定の配線確認で、SciPyの本実行、元EXPの出自署名、全面RF適合ではなかった。失敗/未収束とunknownは保存して区別する。
- 現行RF-F003の性能に旧RF-T008の局所結果を転用しない。実験値は[results](results.md#rf-t008-v3の横断比較2026-10-20の固定履歴)、再利用する手順は[methods](methods.md#pareto支配と配置選択の教訓rf-t008-rev3の歴史的局所探索)を参照。

## 出典

- [Issue #189](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/189)、[PR #191](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/191)、[旧ソース固定履歴](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/d3616b8/src/lpf/phase2_models)。従来の呼出例・検査対象・限定結果はこのファイルの変更前Git履歴にあり、新規の実行手順として複製しない。
- 旧実験のmanifest・数値証拠・重要checkpointは本書の短縮に伴って変更しない。
