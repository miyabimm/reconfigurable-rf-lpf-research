# 回路解析・探索手法の所在

本書は**ナレッジベースの目次**。詳細はテーマ別の`project/knowledge/`に置く。正式RF数値は[active registry](../rf/constraints/registry.json)、実行・承認は[instructions](instructions.md)、実測値は[結果索引](results.md)で区別する。

**参照原則：** 条件ID・effective SHA、全6設定／28区間、格子、source、実施/未実施・未収束を区別。短縮ではなく関連する知識を複数ページへ配置し、旧見出しのリンク先を維持する。

## 統合済みの共通回路計算基盤
[共通回路モデルと独立MNA検証](knowledge/circuit_foundations.md) — 現役RF Coreへの接続、旧モデル境界、独立枝電流MNAと電力・SPDの検査。

## 共通回路モデル・実装方法
[共通回路モデルと独立MNA検証](knowledge/circuit_foundations.md) — 現役RF Coreへの接続、旧モデル境界、独立枝電流MNAと電力・SPDの検査。

## 過去のLQP02HV/HQ設計仮定と出典
[共通回路モデルと独立MNA検証](knowledge/circuit_foundations.md) — 現役RF Coreへの接続、旧モデル境界、独立枝電流MNAと電力・SPDの検査。

## 凍結EXPから共通評価器への移行（実装履歴）
[共通回路モデルと独立MNA検証](knowledge/circuit_foundations.md) — 現役RF Coreへの接続、旧モデル境界、独立枝電流MNAと電力・SPDの検査。

## 磁気結合と伝送零点：統合した理論ノート
[T型結合インダクタのモード・幾何学](knowledge/coupled_inductor_modes.md) — T型のKCL、モードQ、全L行列SPD、結合符号と幾何学的実現限界。

### T型：電流拘束・全行列SPD・モードQ
[T型結合インダクタのモード・幾何学](knowledge/coupled_inductor_modes.md) — T型のKCL、モードQ、全L行列SPD、結合符号と幾何学的実現限界。

### 2組結合：枝選択的強化と不一致の限界
[T型結合インダクタのモード・幾何学](knowledge/coupled_inductor_modes.md) — T型のKCL、モードQ、全L行列SPD、結合符号と幾何学的実現限界。

### 幾何学的実現性と符号積
[T型結合インダクタのモード・幾何学](knowledge/coupled_inductor_modes.md) — T型のKCL、モードQ、全L行列SPD、結合符号と幾何学的実現限界。

### シャント大電流・整合位相・有限C損失
[シャント共振・整合とπ型ノッチ](knowledge/notch_topologies.md) — シャント電流、整合位相、有限C損失、π型の伝送零点とT/π比較。

### π型：零点を固定してから比較する
[シャント共振・整合とπ型ノッチ](knowledge/notch_topologies.md) — シャント電流、整合位相、有限C損失、π型の伝送零点とT/π比較。

### 検算・原典・引用の復元
[シャント共振・整合とπ型ノッチ](knowledge/notch_topologies.md) — シャント電流、整合位相、有限C損失、π型の伝送零点とT/π比較。

## 独立枝電流MNAと検証レベル
[共通回路モデルと独立MNA検証](knowledge/circuit_foundations.md) — 現役RF Coreへの接続、旧モデル境界、独立枝電流MNAと電力・SPDの検査。

## 過去RF-F003と試験トポロジーの比較境界
[探索手法・Pareto・数値判定の教訓](knowledge/optimization_lessons.md) — RF-F003対trialの比較境界、多初期値・座標・格子、Paretoと旧RF-F002の失敗、実行済みA/B数値。

## 多初期値・座標正規化・有限格子での探索上の教訓（RF-T008旧条件）
[探索手法・Pareto・数値判定の教訓](knowledge/optimization_lessons.md) — RF-F003対trialの比較境界、多初期値・座標・格子、Paretoと旧RF-F002の失敗、実行済みA/B数値。

## Pareto支配と配置選択の教訓（RF-T008 rev3の歴史的局所探索）
[探索手法・Pareto・数値判定の教訓](knowledge/optimization_lessons.md) — RF-F003対trialの比較境界、多初期値・座標・格子、Paretoと旧RF-F002の失敗、実行済みA/B数値。

## 開発Pilotの未収束と性能計測の教訓（RF-T008 schema2、Issue #372/#375/#389/#391/#393）
[非EXP PilotとMinimalWorkerの性能計測](knowledge/pilot_performance.md) — 未収束Pilot、測定契約・inclusiveタイマー、#401の実測・限界（正式EXPではない）。

## 旧RF-F002のsolver・manager設計の教訓（Issue #397）
[探索手法・Pareto・数値判定の教訓](knowledge/optimization_lessons.md) — RF-F003対trialの比較境界、多初期値・座標・格子、Paretoと旧RF-F002の失敗、実行済みA/B数値。

## BSF合成と有限Q損失からの設計仮説
[BSFの合成理論と有限Q設計仮説](knowledge/bsf_synthesis.md) — BSF変換、結合行列の適用限界、文献、有限Q・固定/可変Cの探索仮説。

### 合成の座標と適用限界
[BSFの合成理論と有限Q設計仮説](knowledge/bsf_synthesis.md) — BSF変換、結合行列の適用限界、文献、有限Q・固定/可変Cの探索仮説。

### 再利用する文献
[BSFの合成理論と有限Q設計仮説](knowledge/bsf_synthesis.md) — BSF変換、結合行列の適用限界、文献、有限Q・固定/可変Cの探索仮説。

### 局所近似の意味
[BSFの合成理論と有限Q設計仮説](knowledge/bsf_synthesis.md) — BSF変換、結合行列の適用限界、文献、有限Q・固定/可変Cの探索仮説。

### 旧探索から採用する操作と訂正
[BSFの合成理論と有限Q設計仮説](knowledge/bsf_synthesis.md) — BSF変換、結合行列の適用限界、文献、有限Q・固定/可変Cの探索仮説。

## MinimalWorker性能診断の運用（#401/#408）
[非EXP PilotとMinimalWorkerの性能計測](knowledge/pilot_performance.md) — 未収束Pilot、測定契約・inclusiveタイマー、#401の実測・限界（正式EXPではない）。
