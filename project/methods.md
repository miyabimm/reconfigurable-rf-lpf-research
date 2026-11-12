# 回路解析・探索手法の所在

**本書は研究ナレッジベースの理論・方法・トポロジー部分の正本です。** [Issue #397](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/397)に従い、過去の実験から得られた普遍的な教訓をここへ統合し、旧原データ・スクリプトの現行tree保管は要求しません。旧結果の出典リンクが将来Git固定履歴参照へ移る場合があります。現行RF条件の適合を示すものではありません。

**研究手法と出典の案内です。** 現行共通実装と固有の理論原典へ誘導し、退役済みの旧二次文書は固定Git原文から復元できるようにします。EXP原本・数値正本は移動していません。各出典の作成時のRF条件、実行済み検証と未実行計画、回路解析と物理実験の区別を確認してください。

## 統合済みの共通回路計算基盤

[PR #164](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/164)で共通回路レイヤーの実装を統合しました。その後の現役schema2の数値入口は[`rf_core/model.py`](../src/lpf/rf_core/model.py)、設計合法性の窓口は[`search/component_constraints.py`](../src/lpf/search/component_constraints.py)へ分離されています。巻線方向・結合符号とL/C接続の構造は[`topology_management/circuit_layout.py`](../src/lpf/topology_management/circuit_layout.py)が正本です。旧`phase2_models/api.py`とゼロ枝変換`vector_migration.py`は#343/D4で退役済みです。[退役前固定原本](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/d3616b8/src/lpf/phase2_models)は歴史確認用であり、新規探索の入口ではありません。[現役RF coreテスト](../tests/test_issue309_rf_core.py)と[構造テスト](../tests/test_phase2_circuit_layout.py)に実装上の不変条件を保持します。

全6設定・不連続28区間、L結合のSPD、固定／可変Cの接続・OFF状態、およびRF条件IDを混同しません。共通forward APIの一致は、外部S2Pを含む独立MNAの全面検証やRF要求適合を意味しません。旧Stage 1の判断経緯・DoDは[Issue #163](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/163)、[Issue #165](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/165)、PR #164、元設計文書の[固定履歴版](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs)から追跡できます。

## 共通回路モデル・実装方法

| 対象 | 元ファイル | 読み方 |
|---|---|---|
| 共通回路モデルとR2作業 | [R2引継ぎ原文](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/3370ea4/docs/r2_handoff.md)、[R2独立確認JSON](../docs/r2/EXP015_COMMON_MODEL_AUDIT.json) | 旧RF-F001／試験条件に関する保存検証。現行RF-F003性能実績ではない |
| コイル系列の過去の設計仮定 | 下記「過去のLQP02HV/HQ設計仮定」を参照 | 2026-10-12時点の承認・数値モデルの履歴。現在の正式制約はregistryが優先 |
| 探索手法から得た知見 | [topology_search_lessons原文](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/3370ea4/docs/topology_search_lessons.md) | 過去時点の探索改善・制約上の限界 |

## 過去のLQP02HV/HQ設計仮定と出典

2026-10-12の当時の承認ルールは、LQP02HVの定数Q=25・0.4～27 nH・チップ面積コスト1を優先し、必要な場合にLQP02HQの定数Q=20・0.2～56 nH・コスト1を追加するというもの。HVのみとHQ併用を分け、HQの本数・最大L・総L・全6設定の最悪ILとH2/H3を比較する方針だった。**これは当時の計算モデル・探索方針であり、現行RF-F003の数値正本でも、Q(f)・SRF・部品実測の保証でもない。** 現行の制約ID・物理範囲は必ず[active registry](../rf/constraints/registry.json)の指定JSONから解決する。

旧チェックポイントEXP011-01（L1=56 nHをQ25と扱う）およびEXP014-02（L1=28.56046 nHをQ25と扱う）等は旧仮定の履歴として維持し、現条件への性能達成実績に読み替えない。[EXP-015](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/experiments/chatgpt_topology_search/runs/EXP-015/README.md)を後続の当時の検証記録として区別する。当時の優先順位・留保事項を含む[原文（main固定コミット、Git blob `6eb073fc1b1a27e2bc45433e6d238d54e6606857`）](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/52a57cd5fe2e598267e9116fb78131d237f6f711/docs/inductor_series_policy.md)は読み取り専用で復元可能。

## 凍結EXPから共通評価器への移行（実装履歴）

[PR #162](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/162)では以下の共通forward評価器へ移行しました。**下表の旧モジュールは後の#343/D4で退役済み**です。凍結EXP原本は変更せず、現役の数値入口は本ページ冒頭を参照します。

| 凍結EXPソース | 共通評価器 |
|---|---|
| EXP-042 `optimize.py` | `lpf.phase2_models.exp042` |
| EXP-055 `adapt_f003_4l.py` | `lpf.phase2_models.exp055` |
| EXP-058 `sweep_area3.py` | `lpf.phase2_models.exp058_area3` |
| EXP-058 `sweep_area4.py` | `lpf.phase2_models.exp058_area4` |
| EXP-058 `sweep_area4l_gjm.py` | `lpf.phase2_models.exp058_area4l_gjm` |

当時の検証は保存ベクトルと28不連続区間×3点・全6設定、固定入出力S2P、RF-T007の接地DTC付属0.5 pF/Q40、RF-T008 v3のIC固定Q60・可変Q35を区別する有限サンプルの数値パリティと、別経路の7×7/9×9枝電流MNA。PR #162の記録はこの比較範囲を超えた高密度帯域保証を意味しない。

EXP-050、056/057、059～067の保存済みスクリプトに残るEXP間直接importは**SHA固定された歴史原本**であり、新規EXPの実装入口として許可しない。実験ソースの書換えはmanifestの出典SHAを破壊し得る。共有モジュールのforward一致は独立MNA・電力収支の代替ではなく、元の最適化の再実行、RF-F003正式適合、EM・SRF・Q(f)・製作可能性を証明しない。[実装メモ原文（main固定コミット、Git blob `6b9ce1382a94ebb208059eafd7129a2fd74bb4c7`）](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/52a57cd5fe2e598267e9116fb78131d237f6f711/docs/phase2_shared_evaluator_imports_20261027.md)と[当時の凍結比較テスト](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/d3616b8/tests/test_phase2_shared_exp_evaluators.py)を併せて参照する。

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

## 独立枝電流MNAと検証レベル

Issue #163/#168の開発記録を統合します。現役実装・対応条件・完了ゲートは[roadmap](roadmap.md)を確認し、旧WIPの「未実装／レビュー待ち」を現在の状態としません。

- hot-node電圧V、向き付きL電流I、incidence Bに対し `[Yc+Yterm, B; B.T, −Z] [V; I] = [J; 0]`、`Z=ω(diag(L/Q)+jM)`、`Mij=kij√(LiLj)`。Cは個別に`ωC/(1/Q−j)`でstamp。L方向反転では関連k符号も反転する。裸のsolverは部品適合ゲートではなく、`validate_components`等を別途実施する。
- 50Ω行／電流スケーリング後の条件数≥1e12、非有限、非SPDはfail closed。この条件数閾値は数値ガードでありRF制約や物理的不可能性ではない。
- 外部境界の独立解法はSHA確認済みRI S2Pを直接port Yへ変換し、源・負荷端点を消去する。forward LPFのnodal/Schur/ABCDを再利用しない。peak phasorの電力は`Re(VI*)/2`、1V peak Theveninの`Pavs=1/(8Re(Zs))`。上の旧RF-T003 **RMS**式と振幅規約を混ぜない。源抵抗損失を入力電力に含めず、S2P差分・L/C散逸・負荷を二重計上しない。
- 当時の5保存ベクトル×28区間×端点/中点=420 canonical sampleは**6×28の直積ではない**。最大IL差4.476419235288631e−13dB、電力残差5.833007687972014e−17W（元ローカル記録）。cross scanは診断であってcanonical RF判定ではない。局所極値refinementの成功も不可視ピークの不存在・連続区間保証にはならない。
- candidate-bound限定監査は部品／電気役割を再検査し、小格子のforward/MNA/powerを再計算して初めてprior recordと比較する。definition/vector/source/dirty state、policy、bands/S2P、環境、sample座標・許容差を結ぶ。保存record単独は認証でも元EXP出自の証明でもなく、dense/physical/owner証拠を代替しない。限定成功後に`not_checked`の二重表示を除くことと、昇格条件の緩和は別である。
- CI棚卸し#174の区別を維持する：凍結EXP対共通forward、公開API境界、独立MNA/外部電力は似たILを検査しても別の検出能力。非有限・SPD・符号・設定間固定値、S2P SHA/範囲/28区間欠落、ゼロ枝と寄生、出典/予約/保存整合性を保持する。人工的な特異行列・極深零点fixtureは失敗分類のテストで、物理的到達の証明ではない。裸solverの巨大有限入力を部品範囲外だけで契約外と断定しない。

旧T01〜T13と退役assertionの細目・当時のCI値は[固定開発文書](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/3370ea4/docs)にあり、現在のCI分類・モジュールは`scripts/select_ci_tests.py`とそのテストを正本とします。45/66 inventory不一致等の旧known FAILを、後日の文書整理で過去PASSにしません。

## 多初期値・座標正規化・有限格子での探索上の教訓（RF-T008旧条件）

**適用範囲：** [#233多初期値](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/6ac982306cd5899dee99b40dee660d3a6986db89/data/validation/issue233_multistart_pilot/README.md)と[#237座標A/B](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/6ac982306cd5899dee99b40dee660d3a6986db89/data/validation/issue237_coordinate_ab/README.md)の**実行済み**有限探索。どちらも `full_lpf`、RF-T008 rev3 **trial**、当時の実効制約SHA `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`、固定外部S2P・全6設定／28不連続区間を使用。現在のschema 2 RF-T008の実効SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`とは別条件であり、現行RF-F003の実績へ転用しない。

- **開始点は収束とRF適合を分けて評価する。** #233は固定3構成×nominal/Sobol 2点の計9 startで数値収束7件、17点/区間の厳密H2/H3≥30dB適合0件。nominal 3本は既存1-startの損失値を再現し、3L0GJMのSobol index 1もnominalに近い損失へ到達したが、適合率や最悪ILの改善は観測されなかった。少数startで多初期値一般の無効性や最適解不在は結論できない。
- **正規化は単独の解決策ではない。** #237は保存済み9初期値を物理座標A／正規化座標Bで各1回比較し、収束A=7/9、B=8/9、17点strict適合は両方0/9だった。両方式ともSciPy 1.18.1の既定絶対有限差分 `eps≈1.49e-8` を各座標単位に適用するため、Bでは物理有限差分幅もbox幅倍に変わる。座標変換だけの因果効果、安定した速度優位、正規化の標準採用は示されていない（実消費stage・nfevも異なる）。
- **格子と制約残差は段階別に厳密判定する。** 粗2点／精3点のsolver `status=0` は密格子でのRF適合を意味しない。#233のEXP-091は精3点のH2/H3自体が30dBを上回っても、passband epigraph残差が微小負でchecked対象外となり、17点再評価ではB28のH2が29.713319dBへ低下した。30dB直下を丸め・許容差でPASSにせず、H2/H3・passband残差と測定格子を別々に報告する。
- **epigraph変数 `t` を物理ILと取り違えない。** #233の非収束EXP-086/093では最終`t`が巨大な負値へ破綻した。報告するworst ILは**最終完全回路ベクトルをforward評価した値**であり、`t`でもsolver successでもない。破綻を含む開始点をRF適合Paretoへ昇格しない。
- **次回の探索設計への示唆（未実行提案）：** まず失敗を「非収束／epigraph破綻」「厳密閾値直下」「周波数格子内部の見落とし」に分ける。回復法・座標系を比べるなら、初期値・有限差分の**物理**摂動量・制約閾値/guard・評価格子・予算を固定し、収束、strict適合、IL、費用を別指標で比較する。17点も連続帯域保証ではなく、今回strict候補0のため1,001点/区間・84点独立MNA・電力／受動性の後段検証は**未実施**。方法の採用や追加実験を承認したものではない。

代表値・9ペアの全記録と限界は[結果の整理](results.md#rf-t008旧条件の多初期値と座標ab比較)および各[元集計](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/6ac982306cd5899dee99b40dee660d3a6986db89/data/validation/issue233_multistart_pilot/report.json)・[対照集計](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/6ac982306cd5899dee99b40dee660d3a6986db89/data/validation/issue237_coordinate_ab/report.json)を参照する。集計README/JSONへのリンクは削減前の固定Gitコミットを指す。27件の17点検証overlayはEXP-086〜112の各`validation/17pt.json`へ元JSONのGit blob/SHA-256を変えずに移動し、保存manifest／storage_recordの**参照パスだけ**を更新した。旧metadataの原文は移動前の固定Git履歴に残る。この統合は既存結果の読取りであり、新しいRF計算・EXP・独立検証を実施していない。

## Pareto支配と配置選択の教訓（RF-T008 rev3の歴史的局所探索）

**出典・有効範囲：** [EXP-058/059・062〜065の整理結果](results.md#rf-t008-v3の横断比較2026-10-20の固定履歴)。固定外部S2Pと6設定・28区間×1,001点、必須H2/H3≥30dB、当時のRF-T008 rev3 trial実効SHA `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`の探索済み部分集合に限る。

- **非劣性は再最適化後の同条件比較で判定する。** 面積4の旧4L/0GJM候補は低面積3⅔に支配されていたが、EXP-064のPCB-C配置探索で非劣点に変わった。局所探索で見つからないことを構成不可能の証明にせず、固定した面積クラスの異接続・異開始点を比較する。
- **PCB-Cの配置・損失・枝数を独立に考える。** EXP-059ではhot-hot Q40のPCB-C橋絡の代わりにN3–GND/N4–GND（接地Q60）を使う4L/1GJM配置が有利だった。最良に3枝目のPCB-Cは装着されない。配線・Q・値とDTC接続を含む共同再最適化の観測なので、単一枝削除や接地化だけの因果効果と断言しない。
- **部品費増加は性能改善を保証しない。** 面積6⅔/4GJMのbestは面積6/3GJMに支配された。他方、面積5⅓の96回路同時組合せではEXP-062基準から小幅改善した。L/GJM/PCB-C個数だけで候補を並べず、接続役割・物理列・結合SPD・選抜ベクトルと全設定の性能を同時に検証する。
- **探索停止・検証深度をParetoから分離する。** 数値収束、有限格子30dB、84点独立MNA報告、電力保存、35dB公称目標、IL≤0.30dB、連続帯域と製作可能性は異なるゲート。小さな内部guard（約0.005dB）を製造余裕と解釈せず、保存済みMNA結果の監査を新たな独立解法実行と呼ばない。

これらは次の探索で配置と初期値の多様性を確保する**設計上の示唆**であり、新たなRF最適化やPhase移行の承認・実施記録ではない。

## 開発Pilotの未収束と性能計測の教訓（RF-T008 schema2、Issue #372/#375/#389/#391/#393）

**条件と出典：** 非EXP・Phase 2の開発専用診断。RF-T008 rev3 **trial opt-in**、実効SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、`full_lpf`、固定入力/出力S2P・全6設定/28不連続区間。#372/#375の同じ4L・2複合Cv入力の初期seedと、#389/#391/#393の最小Worker比較は**別の測定目的とコードHEAD**。正式RF-F003、旧RF-T008実効SHA `7de08611...`、10月の密格子Paretoの証拠とは混同しない。[代表結果・履歴固定リンク](results.md#開発pilotの未収束と限定性能診断2026-11)を参照。

- **予算増加・solver収束・strict RF適合は独立。** #372は2 seedとも3,000評価で予算切れ、#375ではseed1002を6,500まで延長しても予算切れ／RF不適合、seed1001は6,006評価でsolver収束したがRF不適合。局所反復の増量は必須減衰30dBもILも保証しない。科学順位のbest-observed vectorとsolver terminalも別に判定する。
- **目的値の単一指標化は危険。** #375 seed1002は84点格子で最大違反28.516→0.710dB、合計違反388.449→0.957dBへ低下しても、worst ILは途中の0.988dB（1,000評価）から9.279dB（6,500評価）へ悪化。各forward時点の値であり過去bestではない。70点search、84点anytime、476点terminalでは格子と選抜対象を明示し、失敗を低ILのParetoに昇格しない。
- **データ完全性の停止を科学的不適合にすり替えない。** #372の初回診断はlegacy summaryにない`io`キーを参照する集計コードの`KeyError`で停止しただけで、RF計算やwindow100が失敗したという証拠ではない。後続の固定vector実RF/IO readback照合は当時成功したが、全最適化と全帯域保証は別。window100の予約／確定／unknown、readbackと終端状態は分ける。
- **性能のボトルネックは計測契約に依存する。** #391の100-forward測定ではrequirements `0.105035s`、RF `0.080692s`、physical `0.050532s`（1回の詳細計時）。包含区間の`evaluate/residual`と二重加算しない。固定grid fingerprintや詳細出力の事前計算は**未実装の高速化候補**であり、候補依存の全6設定/28区間、H2/H3、SPD、NaN/STOP、S2P、残差の科学的契約を省略しない。
- **同等性と速度優位を分ける。** #389の限定最小Worker回帰、#393の旧詳細/新prepared各100-forwardのvector・RF・solver一致はその条件での数値同等性。#393のwall時間差は旧→新の単一順序で測定負荷・cacheを固定しておらず、再現した速度比や現行Worker全体の加速率ではない。plain/timed/profileで計測器の負荷が変わる（#391のcProfile solverはplain中央値より約35%長い）。比較には同じ入力・source SHA・seed・solver・grid/参照面での複数回、順序入替、無計時plain基準と分布の評価が必要。

以上は当時の診断から再利用する**判断基準**であり、新しいPilot、RF/EXP、ベンチマーク、最適化を今回実行・承認したものではない。旧raw・一回限りの診断コードを削除しても、現役の`MinimalWorker`・科学的回帰、後続#394でも使用した共通`issue391_benchmark.py`は残す。

## BSF合成と有限Q損失からの設計仮説

以下は2026-10-14の文献・旧RF-T004研究の統合であり、**新規合成の実行報告や現行RF-F003適合の証明ではありません**。元の文献調査・導出全文は[整理前Git tree](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/3370ea4/docs/research)にあります。

### 合成の座標と適用限界

- 古典的LPF→BSF変換は `s_LP = B s/(s²+ω₀²)`、`B=ω₂−ω₁`、`ω₀²=ω₁ω₂`。単一BSFの基準にはなるが二重阻止と低域整合を同時には解かない。
- 直接多項式法は `S21=P/E`, `S11=F/E`。Cameron法は有限伝送零点から一般化Chebyshev多項式、N+2結合行列、等価トポロジーへ進む。losslessの `|S11|²+|S21|²=1` は理想応答の条件であり、有限Qで厳密な実軸零点・無限減衰を要求しない。
- 正規化共振モード行列 **Mは物理Lの磁気結合kではない**。行列回転で合法LC・一列配置・全L行列SPDが自動的に得られるわけではない。Corralesの `M_BSF=M_BPF⁻¹` も論文の規格化・可逆条件に限定し、一般のLC行列に適用しない。多項式の反射／透過交換（阻止帯等リップル）と逆行列法（両側の反射等リップル）は別方式。
- 6個の独立合成行列を並べず、固定L/C/配置/結合を共有する低次元族 `M(C1,C2[,C3])` を設計する。H2/H3の中心比約1.5だけでなく、全28個別区間の縁で最小減衰を評価する。零点感度 `Jij=∂log(fzi)/∂Cj` の有効ランク・条件数と通過帯の電流損失を併せて調べる。
- 50Ω等終端の反射等リップルを旧負荷60−j40Ωに直接移さない。`GT=Pload/Pavs`を最終MNAで求める。周波数一定の複素負荷にFanoの式をそのまま適用し、厳密な広帯域下界と呼ばない。
- 設計仮説は、固定広帯域阻止セル＋可変零点／整合、二経路の位相干渉、弱結合デュアルモード、extracted-pole/非共振ノードによる零点の局所化。応答合成→許可LCへの写像→有限Qの6設定同時最適化→独立MNA・電力・SPD→SRF/EM/公差を分離する。どの系統の優位性も文献調査だけでは未証明。

### 再利用する文献

公開要旨・目次・公開論文を調査した範囲であり、他方式の実測値を本件へ転用しません。

| 著者・年／主題 | 出典と本件での位置づけ |
|---|---|
| Cameron 1999／一般結合行列合成 | [10.1109/22.754877](https://doi.org/10.1109/22.754877)、有限零点からの合成 |
| Cameron 2003／advanced N+2合成 | [10.1109/TMTT.2002.806937](https://doi.org/10.1109/TMTT.2002.806937)、transversal・直接源負荷結合・再構成 |
| Cameron, Yu, Wang 2005／単一・二重BSF | [10.1109/TMTT.2005.859032](https://doi.org/10.1109/TMTT.2005.859032)、Cul-de-Sacを優先仮説。具体的LC化は未検証 |
| Corrales, de Paco, Menéndez 2011／BSF直接合成 | [10.2528/PIERL11091512](https://doi.org/10.2528/PIERL11091512)、多項式交換と逆行列の区別 |
| Cameron, Kudsia, Mansour 2018／extracted pole・trisection、第10章§10.2 | [10.1002/9781119292371.ch10](https://doi.org/10.1002/9781119292371.ch10)、共振セルへの写像 |
| Saeedi, Lee, Sigmarsson 2015／位相相殺型可変BSF | [10.1109/TMTT.2015.2490075](https://doi.org/10.1109/TMTT.2015.2490075)、異なる物理技術 |
| Amari, Rosenberg, Wu 2006／非共振ノードと位相 | [10.1109/TMTT.2005.860494](https://doi.org/10.1109/TMTT.2005.860494)、反射零点制御 |
| Xiao 2016／一般Chebyshev直接合成 | [10.1002/cta.2095](https://doi.org/10.1002/cta.2095)、BSF領域多項式 |
| Cheng et al. 2026／dual-mode二重BSF | [10.1002/mop.70705](https://doi.org/10.1002/mop.70705)、分布定数の例、L/C値転用不可 |
| Fathelbab, Steer 2005／可変Cによる有限零点 | [10.1109/TMTT.2005.843502](https://doi.org/10.1109/TMTT.2005.843502)、BPFでの原理 |
| Ohira et al. 2019／少数制御・周波数依存結合 | [10.1109/TMTT.2018.2873366](https://doi.org/10.1109/TMTT.2018.2873366)、集中定数低Qへの適用未検証 |
| Feng et al. 2024／extracted-pole複数零点 | [10.1016/j.aeue.2024.155317](https://doi.org/10.1016/j.aeue.2024.155317)、主経路外のモード |
| Cai, Wang, Zhang 2015／可変LPF・固定阻止 | [10.1049/el.2015.0829](https://doi.org/10.1049/el.2015.0829)、役割分離の仮説 |
| Liu et al. 2015／hairpin広域阻止 | [10.1049/el.2014.3673](https://doi.org/10.1049/el.2014.3673)、抽象共振グラフのみ参照 |
| IEICE 2016／集中定数整合網の内部損失 | [E99.C/10/1182](https://www.jstage.jst.go.jp/article/transele/E99.C/10/E99.C_1182/_article/-char/en)、R\|I\|²診断 |
| Fano 1950／広帯域整合限界 | [10.1016/0016-0032(50)90006-8](https://doi.org/10.1016/0016-0032(50)90006-8)、上記の負荷モデル制限あり |
| Keysight Genesys S/Filter／直接合成 | [5990-6999](https://www.keysight.com/tw/zh/assets/7018-02793/white-papers/5990-6999.pdf)、メーカー資料、MNA再確認が必要 |

### 局所近似の意味

旧RF-T004の手計算：IL≤0.30dBは`GT≥10^(−0.03)=0.933254`、反射＋散逸≤6.675%。旧50Ω→60−j40Ω直結は `GT=4×50×60/|110−j40|²=0.875912`、IL≈0.57539dB。固定LCトラップの `f0=1/(2π√LC)` にC=1.5pF、HV Q25/C Q50を置くと、1.4GHzでL≈8.616nH、`Rtrap=ωL/25+1/(ωCQ50)≈4.55Ω`。50Ω等終端の**孤立シャント1個**なら`|S21|=2Rtrap/(50+2Rtrap)`、減衰≈16.3dB（2.1GHzではL≈3.829nH、R≈3.03Ω、≈19.3dB）。全回路の到達上限ではなく、単発ノッチ依存への警告です。固定C＋0〜1.5pFで1.326〜1.830GHzを動かす比は`fmax/fmin=√((Cfixed+1.5)/Cfixed)`、Cfixed≤約1.658pF。大きな高Q固定Cの追加にも可動範囲の代償があります。

### 旧探索から採用する操作と訂正

- [EXP-011の原発見履歴](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/experiments/chatgpt_topology_search/runs/EXP-011/DISCOVERY_HISTORY.md)：同一端点・同一Q/fモデルの固定Cと可変Cだけが設定ごとの容量加算で厳密統合可能。各設定の上限と独立MNA同値を確認する。配線変更、部品削除、異QのGJM→PCB置換は等価変換ではなく、全L/C/k/Cvの再最適化が必要。豊かなグラフを生成してから合法縮約し、追加と削除の両方を試す。
- 磁気結合された並列Lも端点一致だけでは合成できない。別の結合相手・枝電流自由度・損失を持つ。PCB-Cのチップ費0は損失0・実装面積0を意味しない。複数枝接続と物理列を同時に変える探索を、単一枝編集とは区別する。
- 損失はワットで`PL=|IL|²ωL/Q`, `PC=|IC|²/(ωCQ)`、`Pavs=Pload+Pref+ΣPL+ΣPC`。反射は発熱ではなく、素子別dBを単純加算しない。実対称の相互誘導項はこのモデルでは無損失。素子だけQ→∞にした凍結回路感度は再最適化後の改善予測でなく、個別改善量も加算不可。
- 旧RF-T003 4LのB28/803MHzではL3発熱0.181057mW（内部発熱の43.94%）、反射0.003117mW。5L配列変更でIL 0.361230713→0.348361188dBへ改善した際、L3損失は0.137645→0.145584mWへ**増加**し、L0減少と全体整合が寄与した。特定素子の損失だけで総ILや因果を断定しない。異なる3C候補との比較も部品値・Q・配置が違い、追加Cv一本の効果とは言えない。
- [EXP-021](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/experiments/chatgpt_topology_search/runs/EXP-021/README.md)のHV35 B71：一定Qの2GHzスポットIL 37.388863dBに対し3GHzは3.276839dB。二重BSF的再透過の解釈であり、3GHzは仕様外のモデル外挿。孤立L3/C枝は低域側で容量性で、「BSFの誘導性領域を整合に使う」は未検証仮説。Schur縮約のY21零点、枝電流、零点感度を別途調べる必要がある。
- [EXP-022の発見・再監査原本](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/experiments/chatgpt_topology_search/runs/EXP-022/topology_discovery_lessons.md)：L1端点(3,4)→(2,4)、PCB-C(3,4)→(1,4)を共同再最適化しIL≈0.352300→0.337988→0.318917→0.305720dB。差分は単独素子の因果効果ではない。「現行直列ESRで再現しない」という前段監査は**撤回**。7,001点/区間＋84点独立MNAでC-H30p0002はIL0.305481244/H2,H3 30.0002dB、C-H30p02は0.305720112/30.0200dB、いずれもIL未達。旧PRのEXP-021はID衝突によりEXP-022へ改番。面積6の大域最適性や旧W3-F4の性能維持を意味しない。

現役の数値正本は[RF registry](../rf/constraints/registry.json)、結果・訂正・保全境界は[results](results.md)。この統合による新規RF計算・EXP・Phase移行はありません。
