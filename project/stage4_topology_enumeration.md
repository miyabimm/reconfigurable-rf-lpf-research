# Issue #189 / PR-S4A：有限トポロジー生成API

対象は **開発Stage 4の先行パッケージS4A**。研究はPhase 2のまま。
S4B（完全候補記録／証拠深度別Pareto）、Stage 5保存runner、実験実施承認は含まない。
RF正本・歴史的EXP・SLSQP予算を変更しない。

## 入口と既存ゲート

`src/lpf/phase2_models/topology_enumeration.py`:

- `labelled_trees(n_inductors, limit=..., reverse_edges=...)`：3L/4L、n+1 hot nodeの
  ラベル付き全辺集合を辞書順に調べ、接続したn枝を上限まで返す。
  任意のsource/load指定が可能。L枝の順列は列挙しない。
  向きマスクを要求した場合もL枝方向を保持し、符号補正や同一視をしない。
- `capacitor_choices(node_count, kind=..., max_branches=..., limit=...)`：
  空配置と、相異なる辺の固定C（GJM01/PCB_PATTERN_C）または可変C
  （接地shunt／hot-hot bridge/series）の有限prefix。最大0〜3枝はこのhelperの
  **計算上の範囲**であり、新RF上限ではない。IC固定CやT007寄生は自由な固定C候補にしない。
- `TopologySpace`：tree、明示L種別割当、固定C配置、可変C配置、結合スロット数、
  物理chip順の採用上限、raw候補の検査上限を指定する不変入力。
  入力軸をソートするため、同じ軸の入力順を入れ替えても結果・fingerprintは同じ。
  RNG／seedは使用しない。重複入力の多重度は件数に残す。
- `enumerate_topologies(resolved_trial, space)`：明示opt-in済みの承認済み
  RF-T005/T007/T008だけを受理。F003/T006、改変policyは開始時に拒否。

各raw組合せを `CircuitDefinition → build_nominal_circuit → connection_role_audit`
に通し、既存`circuit_box`の中点vector（k=0、全6設定のCvを含む）を既存
`validate_components`に通す。これは構造が**少なくともこの代表vectorでは**
部品範囲・Q・結合・完全L行列SPDに適合することの限定チェックであり、
探索vector全域の適合やRF性能を保証しない。Cの同一クラス内の重複辺は拒否する。
固定Cと可変Cの並列、T008の可変CとIC固定Cのペアは意図した配置として許す。

`series`はpolicy上許容でもL spanning treeだけでは物理的直列成立を証明できない。
既存role auditの未証明結果とpromotion blockerをそのまま返す。

## 小さな使用例（列挙のみ、RF計算なし）

```python
from lpf.constraint_versions import load_constraint
from lpf.phase2_models.topology_enumeration import (
    TopologySpace, labelled_trees, capacitor_choices, enumerate_topologies,
)

trial = load_constraint("RF-T008", allow_trial=True)
space = TopologySpace(
    trees=labelled_trees(3, limit=2, reverse_edges=True),
    inductor_assignments=(("LQP02HV",) * 3,),
    fixed_layouts=capacitor_choices(4, kind="fixed", max_branches=1, limit=3),
    variable_layouts=capacitor_choices(4, kind="variable", max_branches=1, limit=8),
    coupling_slot_counts=(0, 1),
    physical_order_limit=2,
    max_candidates=12,
)
report = enumerate_topologies(trial, space)
assert report["counts"]["visited"] <= 12
assert report["candidate_promotion_blocked"]
```

出力の各候補には定義、代表vector、構造／vector key、component検査、role audit、
nominal面積・部品件数・出典policy fieldを保持する。候補完全証拠の保存形式はS4Bで扱う。
本APIの出力にはdataclassが含まれ、S4BのJSON候補記録形式を先取りしていない。

## 件数・有限範囲・再現性

- L種別は明示割当のみ（対応名HV/HQ/PCB_L）。物理chip順は非PCBインダクタの
  全順列の辞書順prefix。選択した結合スロット数に対する全Lペアの部分集合を生成し、
  vector軸の順を保持する。非隣接chip／chip-PCBのスロットも持てるが、
  **nominal k boundsは既存policyによって0に固定**される。非zero結合の許可ではない。
- 走査順はtree/type/physical order/coupling slots/fixed C/variable C。
  `configuration`と`space_sha256`はソート済み入力軸・多重度・各上限・policy実効SHA・
  順序versionを保持する。`output_sha256`は採用vector key列のSHA。
- `counts.raw_space`は**入力された軸と物理順prefixの直積**の件数。
  helperのprefix外、辺順列、他のL種別割当や物理順上限外の件数は含めない。
  `visited = rejected + duplicates + retained`、`raw_space = visited + unvisited`。
  拒否理由ごとに件数を記録する。構造入力の形式自体が不正な場合は例外で開始を拒否する。
- `max_candidates`は採用数ではなく**拒否・重複を含む検査raw数**。
  `truncated`はこの直積内の未訪問suffixがある意味のみ。falseでも網羅的な
  トポロジー探索ではない（`exhaustive_topology_search=false`）。

## 保守的な重複排除と面積

`exact_candidate_key(circuit)`はラベル・順序付きの完全一致だけを扱う。
source/load、電気的L方向／k軸、L種別、物理順、固定／可変／IC固定Cの配置・順序・役割、
schema、stampされるQ／定数寄生、policy ID＋実効SHAを含む。
ノード置換、辺逆転＋符号補償、series↔bridge、物理順置換を同値とみなさない。
同値類は過大であることを`overcomplete_equivalence_classes=true`で明示する。

`exact_candidate_key(circuit, vector)`は追加で完全L/C/符号付きk／全6設定を含む。
**構造だけのkeyで異なるvectorを削除してはならない**。keyは同一性であり、
未検査vectorを合法と認定するものではない（別途既存component gateが必要）。

`nominal_area`は承認済みpolicyの部品別fieldからFractionで計算し、合計と各項の
出典path、policy SHA、件数を返す。歴史的18/3面積・PCB-L探索予算を参照しない。
可変CがOFFでも実装枝は計数する。T007接地寄生を区別し、T008 IC固定Cの追加面積0も
**現nominal会計の暫定値**としてのみ扱う。PCB footprint・routing・実IC面積や
外部固定S2Pの面積を実装ゼロと証明したものではない。

## 検証と未実施の境界

新規`tests/test_phase2_topology_enumeration.py`はsyntheticな小規模回帰のみ。
3L/4L×3 trial、HV/HQ/PCB-L、全6設定、正負k、L方向・端子・物理順・k軸・C順序を
誤統合しない反例、T007寄生／T008 IC固定C、policy改変、不合法枝・枝数・Q/k、
series未証明、入力順不変、件数・上限・fingerprintを確認する。
通常smokeとPi sparse CIの両方にこのテストを追加する。

S4AはRF evaluator・独立MNAを新規候補に実行せず、それぞれ`not_run`を返す。
既存Stage 1〜3の限定RF／MNA／電力・凍結vector回帰はソフトウェアの退行確認であり、
新規EXPや科学的認定ではない。dense／連続帯域／Q(f)／SRF／EM／公差／測定・owner承認は
未実施。`candidate_promotion_blocked=true`を維持する。
完全checkoutを要する既存回帰とPi sparseの実行範囲はPRで別記する。
旧inventory 45/66 FAIL（#170）は未解消であり、このPRで監査PASS扱いにしない。
