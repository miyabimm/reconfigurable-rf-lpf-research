# Versioned RF constraints (Phase 2)

- **正式条件:** `formal/RF-Fxxx.json`。承認後は変更不可。現行は`RF-F003`、`registry.json`の`active_formal_id`で参照。
- **検討用仮条件:** `trial/RF-Txxx.json`。特定の正式版IDを`base_constraint_id`で固定し、変更点だけを`overrides`へ保存。仮条件は正式条件ではなく、正式採用にはユーザーの明示承認と**新たな正式ID**が必要。
- **既存互換:** `../design_constraints.json`は現行正式スナップショットと完全一致する互換ファイル。正本は`formal/`内の変更不可スナップショット。更新するときは必ず両者とregistryを同時更新し、監査テストで一致を確認。
- **旧条件:** `registry.json`の`historical`で元コミットを記録。旧候補の`spec_id`、性能、スクリプトを遡及変更しない。旧LPF-007/008等の再現・回帰と新条件への適合は別問題。
- **面積:** `RF-F001`では面積コストは**目的関数（ILとのパレート）**でありハード上限を設けない。P4-Aの最大コスト6などはジョブの有限探索範囲にすぎない。コスト0のPCB/IC資源は物理面積0を意味しない。
- **比較:** 同一の正式/仮条件、目的、減衰閾値、グリッド、検証水準で比較し、`best-found`と理論的最適値を混同しない。

## 2026-10-20：RF-T008改訂v3（IC可変C最大2枝・所有者承認済み）

RF-T008の**IC可変C設置数を最大2枝へ制限**（0～2枝、3枝は不可）。各可変枝と同じノード間に必ず1つ付随するIC内固定Cも**最大2枝**となる。元のRF-F003の最大2枝を継承し、RF-T008 v2の3枝への拡張を取り下げる。各枝の固定／可変容量・Q値・PCB-Cなど**その他のRF条件は変更しない**。

| 配置 | IC内固定C：全設定共通 | 可変C：6設定別 | 枝合計容量 |
|---|---|---|---|
| Hot-Hot（橋絡／直列） | 0.2～3pF、Q60 | 0～3pF、Q35 | 0.2～6pF |
| Hot-GND | 0.5～3pF、Q60 | 0～3pF、Q35 | 0.5～6pF |

通常のPCB-Cは**Hot-GND 0.02～1pF/Q60、Hot-Hot 0.02～0.2pF/Q40、最大3個**で不変。IC内固定CはPCB-Cの3個枠に含めず、旧0.5pF/Q40シャントDTC寄生をRF-T008に加算しない。可変0pF時もIC内固定Cは存続。Q60・チップ面積は従来どおりPhase 2の暫定モデル。RF-F003・他trialは変更しない。

`load_constraint("RF-T008", allow_trial=True)`による実効枝数`components.IC_VARIABLE_C.max_branches_principle=2`、`trial_variable_c_layout.branch_count=2`、`trial_ic_fixed_c_by_connection.max_composite_branches=2`の三者を揃える。回路検証器と独立MNAでは新仕様のIC内固定Cと可変Cを別枝で評価する。従来の3枝候補を**RF-T008 v3適合済みと称しない**。v2はGit統合コミット`2a6374cd6bc871873eac5cfa43eed4a8a0c68719`に記録済み。v3条件によるRF最適化・独立MNAは未実行、新実験のmain事前予約が必要。Phase 2継続、Phase 3未承認。

## 2026-10-20：RF-T008改訂v2（履歴：当時は最大3可変C）

ユーザー2026-10-20明示承認。RF-T008はPhase 2の試験条件（正式RF-F003ベース）であり、旧初版の単純なシャントDTC用0.5pF/Q40固定寄生を**削除・置換**して、**各IC可変C枝の端点間に1個の高Q IC固定Cを並列配置**する。正式RF-F003、RF-T005/006/007は不変更であり、RF-T007旧0.5pF/Q40シャント寄生は引き続き独自仕様として有効。

| 接続 | 付随するIC内固定C（全6設定共通） | IC可変C（設定別） | 合計C |
|---|---|---|---|
| Hot-Hot（bridge／series） | **0.2～3.0pF、Q60** | **0～3.0pF、Q35** | **0.2～6.0pF** |
| Hot-GND（shunt） | **0.5～3.0pF、Q60** | **0～3.0pF、Q35** | **0.5～6.0pF** |

固定Cを可変3pFに含めず、各独立上限を適用する。IC固定Cは実装後切り替わらず、無スイッチRonの想定。可変Cが0pFでもIC固定Cは残り、特に直列DTC枝はOFFで開放にならない。**独立アドミタンスを加算**：`Y=ω*Cfix/(1/60-j)+ω*Cvar/(1/35-j)`。IC内固定Cは設置DTCと1対1で、独立した固定枝としての追加選択肢にはしない。最大3複合DTC枝。固定容量の合計／各枝値は回路設計記録に保存。Q60一定とシリコン面積コスト暫定0はPhase2数値モデルに過ぎず、面積・実測・Q(f)・SRF・製造公差の実現保証ではない。

**通常PCB-C条件は初版から不変：** **Hot-GND 0.02～1.0pF、Q60**、Hot-Hot 0.02～0.2pF、Q40、合計最大3個。**対GND PCB-CのQは既に60**だったため、今回の変更でもQ60を明記して維持する。IC内固定Cとは別カテゴリーでありPCB-C数に含めない。

`load_constraint("RF-T008", allow_trial=True)`は`trial_ic_fixed_c_by_connection`（上表）、`trial_pcb_pattern_c_by_connection`（PCB-C上表）を返す。旧`trial_shunt_dtc_parasitic`は**RF-T008から排除**し重複計上を防止する。RF-T007の従来機能`trial_shunt_dtc.py`はそのまま残るが、RF-T008には使用しない。新API`src/lpf/trial_ic_fixed_c.py`の`ic_fixed_c_branches`、`ic_c_pair_admittances`、`validate_ic_fixed_c_settings`で固定Cの端点、個数、固定／可変上限、Q値、6バンド固定値共通性を扱う。**既存ソルバー／旧EXPに自動で新枝が加わるわけではない。** 独立MNAでも新モデルを明示して全28区間×密格子を再検証する。

固定外部S2P、6設定、源50Ω／負荷60−j40Ω、H2/H3≥30dB必須・35dB目標、最悪IL≤0.3dB目標、結合k／面積の制約は維持。RF-T006の3～6GHz追加条件は合成しない。**新性能探索は未実施**で、過去のIL値をRF-T008 v2の最適化済み結果とすることは禁止。新EXPのmain台帳予約必須。以前の初版はGit履歴で追跡（main統合コミット`e70264726156512a0c7c9c0bf2e601799911a1cb`）。Phase2継続、Phase3未承認。

## 2026-10-20：RF-T008初版の履歴（後続v2でIC寄生モデル置換）

ユーザーの2026-10-20明示指示に基づく[RF-T008](trial/RF-T008.json)は、**RF-F003を正式固定基準とし、RF-T007の最大3可変Cと接地DTCごとの0.5pF/Q40常設寄生を維持**するPhase 2の独立試験条件です。**固定PCB_PATTERN_Cだけ**を接続先で区別します（制約検証APIではGNDノードを`0`、各実験の内部表現`-1`は明示変換）。

| 通常の固定PCB_PATTERN_C | C範囲 | 公称Q | 個数 |
|---|---:|---:|---|
| 片端がGND（対GNDシャント） | **0.02～1.00pF** | **60** | 両配置の合計で最大3 |
| 両端とも非GND（hot-hot／bridge／series） | **0.02～0.20pF** | **40** | 同上 |

従来の「全PCB-C一律Q40／0.20pF上限」への**例外は対GND枝に限定**。一つの回路でQ60とQ40のPCB-Cを混在可能とする。対GNDの全固定PCB-Cに適用し、EXP-055派生の特定のNode3だけに限定しない。チップ面積コスト0は実PCB面積0を意味しない。Q60・1pFの製造可能性はオーナーの**試験用見込み値**であり、実測・EM・温度／公差／Q(f)の検証済み事実ではない。

**特に区別する寄生:** 接地したIC可変CにRF-T007で付加される常設 **0.5pF/Q40** は、固定PCB_PATTERN_Cではなく**別カテゴリー**。RF-T008でも**Q40のままで、PCB-Cの最大3個枠には入れない**。可変C自身はQ35、0～3pF／枝で最大3枝。接地していない可変Cには常設0.5pFはない。

登録は`data/constraints/registry.json`のstudy_authorizedと`load_constraint("RF-T008", allow_trial=True)`を使用する。接続別の上限・QとQ依存アドミタンスは`src/lpf/trial_pcb_pattern_c.py`の`validate_trial_pcb_pattern_c_branches`、`pcb_pattern_c_branch_admittance`で検査／計算する。**従来の`validate_pcb_pattern_caps`と旧ソルバーは接続依存のRF-T008条件に自動対応しない**。新探索器／独立MNAの両者で各PCB-Cの位置とQ60/Q40を明示的にstampすること。寄生固定Cは従来どおり`trial_shunt_dtc.py`を併用。

他の条件（固定入力／出力S2P、源50Ω／負荷60−j40Ω、6設定・全UL/DL/H2/H3、30dB必須・35dB公称目標、IL 0.3dB目標、L結合・個数・面積）は不変。RF-T006の3～6GHz追加条件は合成しない。**RF-F003およびRF-T005/T006/T007は不変更**。変更対象は研究試験RF-T008だけでありPhase3は未承認。RF-T008登録と数値探索の実行は別作業。旧Q40で得たCg(3,GND)=0.377pF、最悪IL=0.831046dBは**RF-T008(Q60)の新性能実績ではない**；正式な新EXP番号をmainで予約し、固定S2PとQ60モデルによる全帯域再最適化＋独立検証を完了する必要がある。

## 2026-10-19：追加試験 RF-T007（シャントDTC固定寄生0.5pF/Q40）

所有者の2026-10-19指示による[RF-T007](trial/RF-T007.json)は、**RF-F003の正式スナップショットに基づきRF-T005と同じ最大3可変Cを許可**し、さらにシャントDTCごとの固定寄生Cを追加するPhase 2専用試験。**RF-F003、RF-T005、RF-T006はすべて不変更**。RF-T006の3～6GHz追加阻止条件は継承しない。

- **各シャントDTCに必ず固定C=0.5pF、Q=40**を同じ信号ノード–GND間に並列接続する。設定共通・周波数一定、DTC OFF時（可変成分C=0）にも存在する。可変DTCは従来通り**各0～3pF、Q=35**であり、シャント枝の総Cは**0.5～3.5pF**。固定0.5pFを可変3pFに含めて上限を2.5pFにすることは禁止。
- **接地していないブリッジ・直列DTCにはこの寄生Cを付けない。** EXP-042ではCv0（Node4–GND）とCv1（Node5–GND）の2箇所に各0.5pF、Cv2（Node2–Node3）にはなし。以後の3L/4L等の任意トポロジーでも、**接地シャントDTCの本数だけ自動で固定Cを別枝として導入する**。
- 寄生Cの損失はPCB_PATTERN_Cと同じ**Q40**であるが、通常のPCB_PATTERN_C（1個0.02～0.2pF、最大3個）には数えず、別のDTC実装寄生として管理する。追加チップ面積コスト0（実装面積がゼロという主張ではない）。
- 損失を含む枝アドミタンスは既存の定Qモデル **Y=ω C/(1/Q−j)**。可変DTCと固定寄生の**別々のアドミタンスを加算**する。0.5pF/Q40をまとめてQ35とする代替は認めない。
- 使用時は`load_constraint("RF-T007", allow_trial=True)`で実効条件を取得。`src/lpf/trial_shunt_dtc.py::shunt_dtc_parasitic_branches`がMNAに加えるべき固定寄生枝の列を返し、`single_parasitic_admittance`が1枝の損失込みアドミタンスを返す。**メタデータの登録だけでは既存EXP-042ソルバーを自動変更しない。** 新しい最適化器と独立検証器は必ず寄生枝を回路にstampする。内部GND=-1を使用する計算器はAPIのGND=0へ明示変換する。
- **固定0.5pFの公称設計を先行**。個体差・温度変化などの許容範囲は未設定であり、現段階の合否には入れない。将来のロバスト解析で別途評価する。
- 従来の全6設定・28個のUL/DL/H2/H3区間、外部S2P2本、源50Ω、負荷60−j40Ω、必須H2/H3≥30dB・公称35dB、最悪ILの目標、L結合制約・面積パレートは継承。旧EXPのILや減衰はRF-T007の実績とみなさない。Phase 3は未承認・停止。

**実行区分：** 条件登録と寄生枝生成API/単体テストを準備した段階。EXP-042/043/045の新条件での再最適化、全域RFシミュレーション、独立MNA、SRF/EM、公差・実測は**未実行**。新しいRF探索の実行前にはmainへ条件の統合および新EXP番号のmain予約・照合PASSが必要。

## 2026-10-18：追加試験 RF-T006（正式RF-F003は変更しない）

ユーザーの2026-10-18指示による[RF-T006](trial/RF-T006.json)は、**正式RF-F003を固定ベース**とするPhase 2専用の明示opt-in試験条件。

- **追加された必須条件だけ**：外部入力→固定入力S2P→LPF→固定出力S2P→外部出力において、**3.000～6.000 GHzの全周波数で減衰量 ≥20 dB**。数値検査は3,000,000,000 Hzから6,000,000,000 Hzを**1 MHz刻み・端点含む3,001点**、6設定それぞれで実施（計18,006評価点）。GT=Pload/Pavs、減衰は-10log10(GT)。単なるLPF本体S21や50Ω両端のS21で代用しない。
- **継承・変更なし**：RF-F003のIC可変Cは**最大2枝（3枝ではない）**、各0～3 pF/Q35、固定S2P2本のSHA、源50Ω・負荷60−j40Ω、全6設定の28区間UL/DL IL、H2/H3最低30dB（公称35dB）、最悪IL公称目標0.30dB、結合・部品・面積方針。RF-T005（3可変C）は別の試験で変更しない。
- **利用方法**：`load_constraint("RF-T006", allow_trial=True)`で実効ポリシーを取得し、`src/lpf/trial_stopband.py::evaluate_trial_additional_stopband(policy, make_lpf_abcd)` にLPF本体だけの2×2 ABCDを返す関数（`setting, frequency_hz`）を渡す。H2/H3と合わせた必須適合判定には`summarize_full_lpf_trial_feasibility`へ広帯域評価結果も必ず渡す。必要条件の片方だけで適合としない。
- **適用範囲**：full_lpf探索の追加の必須阻止帯域。matching_onlyや旧EXP-047の結果を事後にRF-T006合格として再分類しない。有限格子PASSは周波数連続極値・Q(f)/SRF・EM/実測・公差適合を保証しない。trialからformalへの自動昇格は行わない。
- **実行状況**：条件登録・評価器と合否ゲートの整備であり、RF-T006の新しい候補最適化、実回路の全周波数検証、EXP番号予約は**未実施**。計算開始前にmainへ条件登録を反映し、main台帳で新しいEXPを事前予約する。研究はPhase 2、Phase 3未承認。

## 2026-10-16：新正式RF-F003および試験RF-T005

ユーザー承認により正式版[RF-F003](formal/RF-F003.json)を採用した。旧RF-F002は内容・識別子・ハッシュを維持したまま歴史的条件として保存する。

- 入力側・出力側の固定寄生S2Pを `../parasitics/` に保管し、SHA-256をRF-F003へ固定する。各S2PはDC～6GHz、1MHz格子、50Ω・RI形式。計算プロセスごとに1回ロードしてキャッシュし、複素Sの実部・虚部を線形補間する。オンザフライRLC再計算、範囲外の外挿、ハッシュ不一致時の暗黙フォールバックは禁止。
- カスケード順は **外部入力 → 入力寄生Port1→Port2 → LPF → 出力寄生Port1→Port2 → 外部出力**。信号源50Ω・負荷60−j40Ω、総合伝達電力に対してIL・H2/H3を評価し、旧指標閾値は変更しない。固定寄生は最適化対象外・LPF本体の面積コスト外。
- チップ隣接強結合・PCB-L相互結合はいずれも`|k|≤0.10`。非強結合チップLは公称0・弱結合感度`|k|≤0.03`、chip-PCBは0。
- IC可変Cは正式版では最大**2枝**、各0～**3pF**・**Q35**、従来の接続許可を継承。
- 明示試験条件[RF-T005](trial/RF-T005.json)は**RF-F003固定ベース**で可変Cの上限**3枝**のみを変更。各0～3pF・Q35を維持、明示opt-in必須。RF-T004（RF-F002ベース）とは別系列。
- 現在のS2Pは手書き回路図から数値化した**理想集中定数モデル**の計算値（実測・EM抽出ではない）。回路①の手書き容量桁と抽出基準面は現物確認が必要。新しい総合LPF評価／再最適化は未実行。Phase 2継続、Phase 3停止。

## 2026-10-12：旧RF-F001に基づく比較研究条件（当時の記録）

以下は2026-10-12の履歴で、見出し中の「現行」は**当時のRF-F001**を指す。2026-10-13以降の正式デフォルトはRF-F002である。

**2026-10-12時点の正式版RF-F001（2独立対GND可変C）に関する履歴記述。** この時点では2可変Cを目標としてRF-T001/T002比較を許可し、正式採用とは区別していた。現行正式版は下記2026-10-13節に記載のRF-F002です。

| 条件ID | 状態 | 可変C構成 | 正式条件との差分 |
|---|---|---|---|
| RF-F001 | formal / historical | 当時の原則2独立枝、いずれも対GND | 旧基準。現行ではない |
| [RF-T001](trial/RF-T001.json) | trial / study_authorized | **3独立枝、すべて対GND** | 最大枝数2→3 |
| [RF-T002](trial/RF-T002.json) | trial / study_authorized | **3独立枝：対GND2＋非GNDブリッジ1** | 最大枝数2→3、ブリッジ接続を追加 |

**追加承認RF-T003（2026-10-12、Phase 2限定）：** [RF-T003](trial/RF-T003.json) は**可変Cが計2枝：対GND 1＋非GNDブリッジ 1**。研究条件のUL H2/H3目標は**30dB**（正式版RF-F001の35dB公称値は維持）、全設定UL/DL最悪IL目標≤0.30dB、Q80、各0～4pF、L/固定部品/面積等は変えない。非GNDブリッジは固定導通経路を迂回する位置のみ、**主経路直列可変Cは禁止**。T001/T002はそれぞれ3枝・35dBのまま不変更。必ず`load_constraint("RF-T003", allow_trial=True)`でopt-inし、グラフと30dB研究閾値、検証水準を記録する。正式仕様への採用ではない。

- 各枝0～4pF、Q80（暫定）。固定C、全6設定の不変素子・可変値のみの設定依存、部品・磁気結合・面積パレート方針はRF-F001から**変更しない**。
- H2/H3最低30dB、公称35dB目標、最悪IL 0.30dB目標を全系列で維持。同じ減衰閾値・周波数グリッド・検証水準の結果だけを比較する。
- 3可変Cの接続内訳はtrialの`study_variable_c_layout`を実効ポリシーにも含め、SHA-256で区別する。`validate_variable_c_connections`は枝数と端点・非GND枝のroleを検査する。**ブリッジが実際に直列経路を構成していないことはグラフ検証が必要**であり、現状の検証関数だけでは証明されない。主信号経路に直列挿入する可変Cは今回承認していない。
- 現行の`src/lpf/constraints.py::check_counts`および既存探索器は**デフォルトでRF-F001を参照する**。trialの登録だけで3個回路のP4-A/専用最適化器が自動対応したことにはならない。後続のR2/R3で実効ポリシーと接続検証を明示的に利用する。
- 新規実験は`load_constraint("RF-T001", allow_trial=True)`または`RF-T002`を指定。manifestはtrialのresolved policy、hash、固定基準`RF-F001`、可変C配置、減衰閾値、計算予算を明記。既存EXP-001～015の履歴を遡及的にtrial実験へ分類変更しない。
- 可変Cの数量自体は現在のチップ面積換算では0でも、追加のIC実装面積、スイッチの寄生/損失、制御資源、可変枝間相互作用を別途評価する。2枝 vs 3枝のコスト–ILパレート比較から最終仕様を判断する。
- 3個構成を正式条件に採用する場合、別途ユーザーの明示承認により**新正式ID（例RF-F002）**を発行する。RF-F001は変更しない。

仮条件の汎用登録例（以下は未登録の模式例）：

```json
{
  "constraint_id": "RF-T999",
  "status": "trial",
  "base_constraint_id": "RF-F001",
  "study_authorized": false,
  "study_variable_c_layout": {"branch_count": 3, "shunt_to_ground": 3, "non_ground_bridge": 0},
  "description": "Example only: proposed trial that has not been registered",
  "overrides": {
    "components": {"IC_VARIABLE_C": {"max_branches_principle": 3}}
  }
}
```

実行する場合は`registry.json`の`trial`へ承認状態を登録する。実行時は基準正式版へ差分を適用した**実効制約全体**とSHA-256、目的`matching_only/full_lpf`、探索範囲、コードSHA、乱数seed、数値環境をmanifestに保存する。


## 登録の整合性検証（R1）

`validate_registry` は正式版の `state=approved`、ID/パス、実効JSONの
`effective_constraint_sha256` を照合する。正式版の内容を変えて登録済みハッシュを
維持した読み込みは拒否する。RF-F001には変更せず台帳へハッシュを追加した。
新しい正式条件は新IDで登録し、既存版のハッシュを差し替えない。

trial登録には台帳の `base_constraint_id` とファイルの同項目が一致すること、
台帳の `state=study_authorized` とファイルの `study_authorized=true` が一致することが必要。
未承認は `proposed`、不採用は `rejected`、取下げは `withdrawn` とし、ファイル側はfalse。
いずれも実行時opt-inだけでは読み込めない。制約ID/状態、旧policy_version、Phase 3の
状態をtrial差分で上書きすることはできない。正式昇格APIは存在しない。

実験マニフェストの仕様・履歴の不明値・新規実験開始手順は
[docs/experiment_manifests.md](../../docs/experiment_manifests.md)を参照。

## 2026-10-13 RF-F002とRF-T004

現行正式制約は[RF-F002](formal/RF-F002.json)、従来RF-F001は不変の履歴。新正式条件はチップ隣接|k|≤0.15、非強結合公称k=0・感度|k|≤0.03、PCB間|k|≤0.15、chip–PCB k=0、PCB-L≤2nH、可変C最大2枝・各0–1.5pF・Q50・配置自由、LQW04 Q33。旧セクションの「現行正式RF-F001」は2026-10-12時点の記述。

[RF-T004](trial/RF-T004.json)はRF-F002を固定基準とする明示opt-in試験条件。可変Cのみ最大3枝まで拡張し、0〜3枝、位置自由。RF-T001/T002/T003はRF-F001基準の履歴試験のままとする。Phase 3停止。
