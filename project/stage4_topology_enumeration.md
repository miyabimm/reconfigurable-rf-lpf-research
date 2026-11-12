# 旧Stage 4：有限トポロジー生成（履歴）

**#189/#190当時の有限列挙APIの説明。** #343 D3〜D4以降の現役設計・科学計算入口ではない。現在の構造は[topology_management](../src/lpf/topology_management/)、合法性は[search/component_constraints.py](../src/lpf/search/component_constraints.py)、RFは[rf_core/model.py](../src/lpf/rf_core/model.py)が基準。

## 残す設計上の教訓

- 端子番号、枝の向き・順序、物理列、チップ種類とcost、固定／可変C役割、符号付き結合を区別する。抽象的なグラフ同型だけで異なる物理配置や素子意味を潰さない。
- 有限列挙の件数・指定面積以下の探索済み集合は、その定義と上限内のものに限る。探索空間を拡張した一般の不可能性や大域最適性を主張しない。
- 構造生成と完全ベクトルの合法性、全L行列SPD、6設定/28区間の実RF性能、固定S2P、独立MNA・受動電力収支は別段階で検査する。
- 新しいトポロジーは回路理論の仮説→合法構造→初期値多様性→局所探索→密格子・独立検証の順で評価し、過去の小集合Paretoを形式的に昇格させない。

## 出典

- [Issue #189](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/189)、[PR #190](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/190)、[退役実装の固定Git履歴](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/d3616b8/src/lpf/phase2_models)。詳細な旧呼出例はこの文書の変更前Git履歴を参照。
- 科学的実績は[results.md](results.md)、汎用の手法は[methods.md](methods.md)に集約。#397の整理は新しいRF数値計算を行わない。
