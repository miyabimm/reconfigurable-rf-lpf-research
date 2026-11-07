# 回路解析・探索手法の所在

**研究手法と出典の案内です。** 現行共通実装と固有の理論原典へ誘導し、退役済みの旧二次文書は固定Git原文から復元できるようにします。EXP原本・数値正本は移動していません。各出典の作成時のRF条件、実行済み検証と未実行計画、回路解析と物理実験の区別を確認してください。

## 統合済みの共通回路計算基盤

[PR #164](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/164)で共通回路レイヤーの実装を統合しました。その後の現役schema2の数値入口は[`rf_core/model.py`](../src/lpf/rf_core/model.py)、設計合法性の窓口は[`search/component_constraints.py`](../src/lpf/search/component_constraints.py)へ分離されています。巻線方向・結合符号とL/C接続の構造は[`topology_management/circuit_layout.py`](../src/lpf/topology_management/circuit_layout.py)が正本です。旧[`phase2_models/api.py`](../src/lpf/phase2_models/api.py)とゼロ枝変換[`vector_migration.py`](../src/lpf/phase2_models/vector_migration.py)は歴史caller・科学回帰用に残存し、新規探索の入口ではありません。[現役RF coreテスト](../tests/test_issue309_rf_core.py)と[構造テスト](../tests/test_phase2_circuit_layout.py)に実装上の不変条件を保持します。

全6設定・不連続28区間、L結合のSPD、固定／可変Cの接続・OFF状態、およびRF条件IDを混同しません。共通forward APIの一致は、外部S2Pを含む独立MNAの全面検証やRF要求適合を意味しません。旧Stage 1の判断経緯・DoDは[Issue #163](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/163)、[Issue #165](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/165)、PR #164、元設計文書の[固定履歴版](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs)から追跡できます。

## 共通回路モデル・実装方法

| 対象 | 元ファイル | 読み方 |
|---|---|---|
| 共通回路モデルとR2作業 | [R2引継ぎ](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/r2_handoff.md)、[R2独立確認JSON](../docs/r2/EXP015_COMMON_MODEL_AUDIT.json) | 旧RF-F001／試験条件に関する保存検証。現行RF-F003性能実績ではない |
| コイル系列の過去の設計仮定 | 下記「過去のLQP02HV/HQ設計仮定」を参照 | 2026-10-12時点の承認・数値モデルの履歴。現在の正式制約はregistryが優先 |
| 探索手法から得た知見 | [topology_search_lessons](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/topology_search_lessons.md) | 過去時点の探索改善・制約上の限界 |

## 過去のLQP02HV/HQ設計仮定と出典

2026-10-12の当時の承認ルールは、LQP02HVの定数Q=25・0.4～27 nH・チップ面積コスト1を優先し、必要な場合にLQP02HQの定数Q=20・0.2～56 nH・コスト1を追加するというもの。HVのみとHQ併用を分け、HQの本数・最大L・総L・全6設定の最悪ILとH2/H3を比較する方針だった。**これは当時の計算モデル・探索方針であり、現行RF-F003の数値正本でも、Q(f)・SRF・部品実測の保証でもない。** 現行の制約ID・物理範囲は必ず[active registry](../rf/constraints/registry.json)の指定JSONから解決する。

旧チェックポイントEXP011-01（L1=56 nHをQ25と扱う）およびEXP014-02（L1=28.56046 nHをQ25と扱う）等は旧仮定の履歴として維持し、現条件への性能達成実績に読み替えない。[EXP-015](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/experiments/chatgpt_topology_search/runs/EXP-015/README.md)を後続の当時の検証記録として区別する。当時の優先順位・留保事項を含む[原文（main固定コミット、Git blob `6eb073fc1b1a27e2bc45433e6d238d54e6606857`）](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/52a57cd5fe2e598267e9116fb78131d237f6f711/docs/inductor_series_policy.md)は読み取り専用で復元可能。

## 凍結EXPから共通評価器への移行（実装履歴）

[PR #162](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/162)の共通forward評価器は、以下の凍結ソースを**変更せず**に再利用するための実装。現行の共通回路公開API・接続制約は本ページ冒頭および[PR #164](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/164)を参照。

| 凍結EXPソース | 共通評価器 |
|---|---|
| EXP-042 `optimize.py` | `lpf.phase2_models.exp042` |
| EXP-055 `adapt_f003_4l.py` | `lpf.phase2_models.exp055` |
| EXP-058 `sweep_area3.py` | `lpf.phase2_models.exp058_area3` |
| EXP-058 `sweep_area4.py` | `lpf.phase2_models.exp058_area4` |
| EXP-058 `sweep_area4l_gjm.py` | `lpf.phase2_models.exp058_area4l_gjm` |

当時の検証は保存ベクトルと28不連続区間×3点・全6設定、固定入出力S2P、RF-T007の接地DTC付属0.5 pF/Q40、RF-T008 v3のIC固定Q60・可変Q35を区別する有限サンプルの数値パリティと、別経路の7×7/9×9枝電流MNA。PR #162の記録はこの比較範囲を超えた高密度帯域保証を意味しない。

EXP-050、056/057、059～067の保存済みスクリプトに残るEXP間直接importは**SHA固定された歴史原本**であり、新規EXPの実装入口として許可しない。実験ソースの書換えはmanifestの出典SHAを破壊し得る。共有モジュールのforward一致は独立MNA・電力収支の代替ではなく、元の最適化の再実行、RF-F003正式適合、EM・SRF・Q(f)・製作可能性を証明しない。[実装メモ原文（main固定コミット、Git blob `6b9ce1382a94ebb208059eafd7129a2fd74bb4c7`）](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/52a57cd5fe2e598267e9116fb78131d237f6f711/docs/phase2_shared_evaluator_imports_20261027.md)と[凍結比較テスト](../tests/test_phase2_shared_exp_evaluators.py)を併せて参照する。

## 磁気結合と伝送零点：統合した理論ノート

以下は2026-10-16の9文書から統合した**理想集中定数モデルの理論・限定ベンチ**です。
正式RF-F003への適合、LTE全帯域の最適化、3D EM、Q(f)、SRF、相互抵抗、寄生C、製造公差・実測は未検証。
指定範囲内の解析的モード上限と、実装・ILの大域最適性を区別します。新規EXPやPhase 3移行ではありません。

### T型：電流拘束・全行列SPD・モードQ

IN→中央のL1、中央→OUTのL2、中央→GNDのL3を枝順(1,2,3)とし、`I1=I2+I3`。
端子電流は両端とも回路へ流入する向きで、`I=B i`、`B=[[1,0],[0,-1],[1,1]]`。
符号付き `Mij=kij sqrt(Li Lj)`、`Zport=Bᵀ(R+jωL)B`、
`Qmag=ω I†L I/(I†R I)`。Qmagはコイル群の無効電力/散逸であり、部品intrinsic Q・loaded Q・最小ILではありません。
基本仮定は `R=diag(ωLi/Qi)`（相互抵抗0）。全L行列SPDとR半正定値を別々に検査します。
3枝の正規化Kは主小行列に加えて `det K=1+2k12k13k23-k12²-k13²-k23²>0` が必要です。

等自己L・等Q0の全複素電流モードは `(BᵀKB,BᵀB)` の一般化固有値で評価できます。
`β=I3/I1`、`D=1+|1-β|²+|β|²` とすれば
`Qmag/Q0=1+2[k12 Re(1-β)+k13 Re β+k23 Re((1-β)*β)]/D`。

| (k12,k13,k23)、κ≥0 | Qmin/Q0 | Qmax/Q0 |
|---|---:|---:|
| (0,+κ,0) | 1−κ/3 | 1+κ |
| (0,+κ,+κ) | 1−2κ/√3 | 1+2κ/√3 |
| (+κ,+κ,+κ) | 1−κ | 1+5κ/3 |
| (0,+κ,−κ) | 1 | 1+4κ/3 |
| (+κ,+κ,−κ) | 1+κ | 1+κ |

最後のバランス配置は `n=(1,-1,-1)`、`K=(1+κ)Id−κnnᵀ`、固有値 `(1+κ,1+κ,1−2κ)`。
SPDにはκ<1/2。KCLが弱いn方向を排除し全許容モードを一様に改善します。
`|kij|≤κ<1/2` 下の最悪モードQの解析的上限Q0(1+κ)を達成しますが、IL最適性ではありません。
κ≥1/2でもSPDとtrace K=3より全モード下限は1.5Q0未満。
同一リアクタンスで自己Lを1/(1+κ)に縮め、Q0不変なら抵抗も同率で減ります。
1GHz、50Ω/50Ω、Q0=25、κ=.4、基準各10nH、シリーズC=2.533029591pF・シャント直列C=.1pFの
限定ベンチはIL .427508→.307808dB。独立MNA/電力収支の点検記録であり、RF制約外です。

非等L・等Qでは `M12=g(L1+L2)/2`、`M13=g(L1+L3)/2`、`M23=−g(L2+L3)/2` により
`BᵀLB=(1+g)Bᵀdiag(Li)B`。`H=sqrt((ΣLi)(Σ1/Li))` としてSPD条件は `g<2/(1+H)`。
Li比が不均衡なほど大きい|kij|が必要です。等Lの結合誤差 `|δkij|≤ε` なら
`Qmin/Q0≥1+g−2ε`、`λmin(K)≥1−2g−2ε`（L/Q固定・相互Rなしの保守的下界）。

### 2組結合：枝選択的強化と不一致の限界

一般のTは非結合等価値
`L1'=L1+M12+M13+M23`、`L2'=L2+M12−M13−M23`、`L3'=L3−M12+M13−M23`。
相互Mの絶対値を揃えると、A=(M,M,0)、B=(M,0,−M)、C=(0,M,−M)はそれぞれL1/L2/L3だけを2M強化します。
等L・等Qでは `Qh/Q0=1+2k|Ih|²/Σ|Ii|²`、全モード範囲 `[1,1+4k/3]`、SPD条件k<1/√2。
同一端子電流・同一等価Lでの銅損差は `Puncoupled−Pcoupled=2ωM|Ih|²/Qh`。
実際の電源/負荷電流は変わるため最終ILは回路全体で解きます。

等価枝10nH・他枝10nHを固定するとハブ自己Lは `10nH(√(1+k²)−k)²`。
k=.4の1GHz/50Ω・理想整合ベンチ（シリーズC=3.715808pF、シャント直列C=1.176035pF）で
ILは非結合 .554499、A/B .437433、C .487889dB。ハブ抵抗改善にはQnew>11.46（基準Q25）が必要。
k=.1ならQnew>20.48。単体Qや面積がL縮小後も不変という保証はありません。

全モード非劣化には2組の**Mの一致**と未指定ペア0が必要です（非等Lではk一致ではない）。
等Lで `(k12,k13,k23)=(a,b,−c)`、a,b,c≥0の場合の必要十分条件は
`(a+b−c)²≤4ab`、かつ別途K SPD。c=0ではa=bが必要。
例a=b=.01,c=.10はSPDでもQmin/Q0=.98。Aの残留k23=+.02ならQminはQ0−.02Q0。
混合Qの同相2コイルは `Qmode=2(1+k)/(1/Qh+1/Ql)`、Qhより改善するには `k>(Qh/Ql−1)/2`。
同Rで相互抵抗rRがあればQ比は `(1+k)/(1+r)` となり、r≥kで理想的利益は失われます。

### 幾何学的実現性と符号積

3ペアの符号積は枝基準反転で不変。単一共通磁束モデルの全正積を(+,+,−)へ変換できません。
同一平面・同巻方向の非重複円形フィラメント3個を正三角形に置くと全負Mとなり、
`S=diag(1,−1,−1)` により(+,+,−)へ変換できます。ただし配線・リード込みの実現証明ではありません。
Neumann式 `M=μ0/(4π)∮∮ dl1·dl2/|r1−r2|` の1024²中点積分と、
完全楕円積分ベクトルポテンシャルの4096点1D積分を照合した記録です。
半径1mm・導体半径20µmでは `Lself≈μ0a[ln(8a/rwire)−2]=5.015822nH`。
中心距離2.05/2.10/2.50/3mmのMは−.344802/−.276225/−.104117/−.049618nH、
|k|=.068743/.055071/.020758/.009892。2.05mm時の表面間隔は約10µmで寄生・製造上の懸念があります。
この形状でk=.4に届かないことは、全電磁形状で不可能という意味ではありません。
2.10mm基準からL3を+xへ0/.05/.10/.20mm動かした限定計算のQmin（Q0=25）は26.377/26.231/26.090/25.751。
一般公差保証ではありません。N枝でnᵀI=0、等L/Q、`K=(1+g)Id−gnnᵀ` なら
残るN−1モードはQ0(1+g)、SPDには `g<1/(N−1)` が必要です。

### シャント大電流・整合位相・有限C損失

TのC型2組結合は `L3eq=L3+2M`、シャント直列Cの零点は `fz=1/(2π√(C3 L3eq))`。
等価Tで `|I3/I2|=|Z2+Zload|/|Z3eq|` が大きいノッチ電流は、通過IL改善とは別です。
並列CならKCLは `I1−I2=I3+IC` に変わり、全モード非劣化証明は適用できません。
自己共振 `ω²L3C3=1` では `(1+ω²C3M)(I3+IC)=jωC3R3I3` なので相互磁気エネルギー寄与は0。
1GHz/各1nH/Q25/並列C25.3303pF/50Ωのベンチではk=0→.4でQmag=25のまま、
循環I3=68.594→52.550mA、IL=1.3941→.7909dB。循環電流最大化は効率最大化ではありません。

一方、無損失対称TのシリーズjX・中央−jYは `Y=(R0²+X²)/(2X)` で整合し、
`I2/I1=exp(−jθ)`、`θ=2 atan(X/R0)`、`|I3/I1|=2X/√(R0²+X²)`。
X=R0なら出力と同振幅を通しつつシャントへ√2倍の電流が流れます。
1GHz/50Ω・2GHz理想ノッチでL1=L2=7.957747nH、L3eq=2.652582nH、C3=2.387324pF。
`L3=(√(L3eq+k²L1)−k√L1)²` とすれば同じ理想応答を保ち、Q25・理想Cでk=0/.1/.4の
IL=.462226/.428907/.379025dB。ただしCのESR `1/(ωC Qc)` を含むQc35では
.780725/.748909/.701240dBで、C損失が大きくなります。
別の低シリーズL1nH/L3eq10nH/C3=.6332573978pFベンチではk=0→.4の
1GHz IL=.059673→.056185dB、2GHz減衰16.127997→18.005922dB。比較条件を混ぜません。

### π型：零点を固定してから比較する

中央Ls（IsはIN→OUT）、両端からGNDへLa+Ca/Lb+Cb（Ia/Ibは下向き）の直列LC。
対称La=Lb=Lh、Ca=Cb=C、Msa=M、Msb=−M、Mab=0では
`Z=[[zs,m,−m],[m,zh,0],[−m,0,zh]]`、`m=jωM`、`zh=Rh+j(ωLh−1/(ωC))`。
`Ye=1/zh`、`Yo=1/zh+2(zh−m)²/[zh(zs zh−2m²)]`、`Y12=(Ye−Yo)/2`。
非退化・無損失・M≠0の零点は `fz=1/(2π√(C(Lh−M)))`（Lh>M）。
M=0はLC共振で分母分子同時0になるのでY12=0へ直接代入せず極限を扱います。
整合条件は `Ye Yo=1/R0²`。TのKCLによる全モードQ保証はπに適用できません。
等L/QでQ比は `1+2k Re(Is*(Ia−Ib))/Σ|Ii|²`。磁気Q上昇とIL改善は同義でありません。

1GHz/50Ω、Lh=5nH、Q25・理想Cの旧設計ではk=+.1/−.1でIL .227139→.199417dBながら
2GHz減衰43.087→14.644dBへ悪化。零点移動を補正した2GHz固定比較では
非結合 `(Ls,C)=(6.588979nH,1.266515pF)` のIL .244453dBに対し、
**逆符号**−.1/+.1 `(5.675550nH,1.144570pF)` は .209827dB（2GHz減衰51.203→51.532dB）。
ただし1.9–2.1GHzの401点最小減衰は32.02→30.97dBで、帯域全域の優位ではありません。
C±1%では零点2.01008/1.99007GHz、2GHz減衰50.779/51.003dB。一般公差保証ではありません。
節点解 `I=Z⁻¹AV, (AᵀZ⁻¹A+G)V=J` と独立ブロックMNA `[[G,Aᵀ],[−A,Z]]` を照合した記録です。

T/πを同じ1GHz整合・2GHz理想零点・QL25/QC35・|k|=.1で比較した特定設計では
IL T=.748909、π=.3694dB、局所0.85–1.15GHz/301点最大IL 1.606/.544dB。
しかし3GHz減衰は21.81/9.32dBで、πはH3用途に不十分です。
TのXを25/50/100Ωへ変えたIL .3843/.7489/1.4228dBと2GHz減衰26.70/36.80/45.68dBはトレードオフを示します。
同一全帯域制約・同一コストの最適化ではなく、TはC1個、πはC2個です。

### 検算・原典・引用の復元

決定論的な既存テスト：[モード理論](../tests/test_t_coupled_modal_theory.py)、
[幾何](../tests/test_t_coupled_geometry.py)、[2組結合](../tests/test_t_two_coupling_models.py)、
[シャント電流](../tests/test_t_shunt_high_current.py)、[整合位相](../tests/test_t_matched_shunt_high_current.py)、
[π零点](../tests/test_pi_zero_retarget.py)。当時の会話環境のみのスクリプト・CSV・図はGit登録済みとは扱いません。
完全なベンチ表、参考文献（Neumann、IEEE TMTT 2007/2021の相互損失、Ruiz/Hinojosa 2014のLCノッチ等）、
未実行提案の逐語原文は **Issue #352整理前コミット `a86f47b`** の
[9原典](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/a86f47b/docs)から復元できます。
ファイル名は `phase2_t_coupled_inductor_{q_foundations,uniform_mode,planar_geometry}_20261016.md`、
`phase2_t_{two_pair_coupling,shunt_high_current_modes,shunt_current_matched_passband,pi_common_conditions_loss_comparison}_20261016.md`、
`phase2_pi_{two_pair_coupling,notch_retarget}_20261016.md`。
`git show a86f47b:docs/<ファイル名>` で元文書を読み戻せます。原blobと参照元の全件照合はIssue #352のPRに記録します。

## BSF合成・旧試験トポロジーの理論／探索出典

2026-10-14時点の基礎文献・仮説および旧RF-T004試験の記録です。いずれも現行RF-F003の適合候補と同一視しません。

| 原典 | 記録の性質と確認境界 |
|---|---|
| [RF-T004のトポロジー文献調査](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/research/rf_t004_literature_survey_2026-10-14.md) | 文献からの設計仮説・探索計画。**数値最適化や独立RF検証は未実行** |
| [BSF/Cameron結合行列法の文献調査](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/research/bsf_cameron_synthesis_literature_2026-10-14.md) | 文献上の合成法、パッシビティと実現可能なLCへの変換条件。研究モデルでの実証とは区別 |
| [EXP-021の二重BSF解釈](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/research/exp021_dual_bandstop_review_2026-10-14.md) | 保存EXPに対する応答上の解釈と次の合成仮説。提案した系統探索の**実行済み報告ではない** |
| [RF-T004/EXP-022の面積6探索索引](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/research/rf_t004_exp022_area6_discovery_index.md) | 旧条件での数値訂正・全格子／独立MNA追試とIL未達を含む歴史索引。旧ID衝突と元EXPの区別を維持 |

固有の式・実験条件・引用文献・訂正経緯は各原文に残します。T/π型とBSF型の研究を名称だけで統合せず、受動性・結合行列SPD・電力保存・独立MNAなどの検証範囲を分けて読む必要があります。

## 正本と証拠に戻る

- [現行正式RF-F003 JSON](../rf/constraints/formal/RF-F003.json)、[試験RF-T005](../rf/constraints/trial/RF-T005.json)。
- [2026-10-17の3L/4L保存候補・制約別パレート](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/pareto_rf_t005_rf_f003_20261017.md)。
- [旧資料の分類・処置](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/170) と [W3固有情報の保全](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/archive/w3_consolidated_documents_20261017.md)。

**本索引は研究の新たな数値解析や実験結果を提供しません。**
