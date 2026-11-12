# 回路解析・探索手法の所在
**本書は研究ナレッジベースの理論・方法・トポロジー部分の正本です。** [Issue #397](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/397)に従い、過去の実験から得られた普遍的な教訓をここへ統合し、旧原データ・スクリプトの現行tree保管は要求しません。旧結果の出典リンクが将来Git固定履歴参照へ移る場合があります。現行RF条件の適合を示すものではありません。
**研究手法と出典の案内です。** 現行共通実装と固有の理論原典へ誘導し、退役済みの旧二次文書は固定Git原文から復元できるようにします。EXP原本・数値正本は移動していません。各出典の作成時のRF条件、実行済み検証と未実行計画、回路解析と物理実験の区別を確認してください。

## 統合済みの共通回路計算基盤
[PR #164](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/164)で共通回路レイヤーの実装を統合しました。その後の現役schema2の数値入口は[`rf_core/model.py`](../src/lpf/rf_core/model.py)、設計合法性の窓口は[`search/component_constraints.py`](../src/lpf/search/component_constraints.py)へ分離されています。巻線方向・結合符号とL/C接続の構造は[`topology_management/circuit_layout.py`](../src/lpf/topology_management/circuit_layout.py)が正本です。旧`phase2_models/api.py`とゼロ枝変換`vector_migration.py`は#343/D4で退役済みです。[退役前固定原本](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/d3616b8/src/lpf/phase2_models)は歴史確認用であり、新規探索の入口ではありません。[現役RF coreテスト](../tests/test_issue309_rf_core.py)と[構造テスト](../tests/test_phase2_circuit_layout.py)に実装上の不変条件を保持します。
全6設定・不連続28区間、L結合のSPD、固定／可変Cの接続・OFF状態、およびRF条件IDを混同しません。共通forward APIの一致は、外部S2Pを含む独立MNAの全面検証やRF要求適合を意味しません。旧Stage 1の判断経緯・DoDは[Issue #163](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/163)、[Issue #165](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/165)、PR #164、元設計文書の[固定履歴版](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs)から追跡できます。

## 共通回路モデル・実装方法
- 旧RF-F001／trialの[EXP-015 R2独立監査](../docs/r2/EXP015_COMMON_MODEL_AUDIT.json)は現行F003性能の根拠ではない。旧原文は[固定履歴](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/3370ea4/docs/r2_handoff.md)。

## 過去のLQP02HV/HQ設計仮定と出典
2026-10-12の当時の承認ルールは、LQP02HVの定数Q=25・0.4～27 nH・チップ面積コスト1を優先し、必要な場合にLQP02HQの定数Q=20・0.2～56 nH・コスト1を追加するというもの。HVのみとHQ併用を分け、HQの本数・最大L・総L・全6設定の最悪ILとH2/H3を比較する方針だった。**これは当時の計算モデル・探索方針であり、現行RF-F003の数値正本でも、Q(f)・SRF・部品実測の保証でもない。** 現行の制約ID・物理範囲は必ず[active registry](../rf/constraints/registry.json)の指定JSONから解決する。

## 凍結EXPから共通評価器への移行（実装履歴）
[PR #162](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/162)では以下の共通forward評価器へ移行しました。**下表の旧モジュールは後の#343/D4で退役済み**です。凍結EXP原本は変更せず、現役の数値入口は本ページ冒頭を参照します。
当時の検証は保存ベクトルと28不連続区間×3点・全6設定、固定入出力S2P、RF-T007の接地DTC付属0.5 pF/Q40、RF-T008 v3のIC固定Q60・可変Q35を区別する有限サンプルの数値パリティと、別経路の7×7/9×9枝電流MNA。PR #162の記録はこの比較範囲を超えた高密度帯域保証を意味しない。

## 磁気結合と伝送零点：統合した理論ノート
以下は2026-10-16の9文書から統合した**理想集中定数モデルの理論・限定ベンチ**です。
正式RF-F003への適合、LTE全帯域の最適化、3D EM、Q(f)、SRF、相互抵抗、寄生C、製造公差・実測は未検証。

### T型：電流拘束・全行列SPD・モードQ
IN→中央のL1、中央→OUTのL2、中央→GNDのL3を枝順(1,2,3)とし、`I1=I2+I3`。
基本仮定は `R=diag(ωLi/Qi)`（相互抵抗0）。全L行列SPDとR半正定値を別々に検査します。
3枝の正規化Kは主小行列に加えて `det K=1+2k12k13k23-k12²-k13²-k23²>0` が必要です。
- T型のバランス結合`(+κ,+κ,−κ)`では `n=(1,-1,-1)`、`K=(1+κ)Id−κnnᵀ`、固有値 `(1+κ,1+κ,1−2κ)`。
SPDにはκ<1/2。KCLが弱いn方向を排除し全許容モードを一様に改善します。

### 2組結合：枝選択的強化と不一致の限界
一般のTは非結合等価値
相互Mの絶対値を揃えると、A=(M,M,0)、B=(M,0,−M)、C=(0,M,−M)はそれぞれL1/L2/L3だけを2M強化します。
全モード非劣化には2組の**Mの一致**と未指定ペア0が必要です（非等Lではk一致ではない）。

### 幾何学的実現性と符号積
3ペアの符号積は枝基準反転で不変。単一共通磁束モデルの全正積を(+,+,−)へ変換できません。
- 限定した平面円形コイルでは中心距離2.05/2.10/2.50/3mmの結合絶対値 |k|=.068743/.055071/.020758/.009892。2.05mm時の表面間隔は約10µmで寄生・製造上の懸念があります。

### シャント大電流・整合位相・有限C損失
TのC型2組結合は `L3eq=L3+2M`、シャント直列Cの零点は `fz=1/(2π√(C3 L3eq))`。
循環I3=68.594→52.550mA、IL=1.3941→.7909dB。循環電流最大化は効率最大化ではありません。
IL=.462226/.428907/.379025dB。ただしCのESR `1/(ωC Qc)` を含むQc35では
.780725/.748909/.701240dBで、C損失が大きくなります。

### π型：零点を固定してから比較する
中央Ls（IsはIN→OUT）、両端からGNDへLa+Ca/Lb+Cb（Ia/Ibは下向き）の直列LC。
非退化・無損失・M≠0の零点は `fz=1/(2π√(C(Lh−M)))`（Lh>M）。
2GHz減衰43.087→14.644dBへ悪化。零点移動を補正した2GHz固定比較では
ただし1.9–2.1GHzの401点最小減衰は32.02→30.97dBで、帯域全域の優位ではありません。

### 検算・原典・引用の復元
決定論的な既存テスト：[モード理論](../tests/test_t_coupled_modal_theory.py)、
未実行提案の逐語原文は **Issue #352整理前コミット `a86f47b`** の

## 独立枝電流MNAと検証レベル
- hot-node電圧V、向き付きL電流I、incidence Bに対し `[Yc+Yterm, B; B.T, −Z] [V; I] = [J; 0]`、`Z=ω(diag(L/Q)+jM)`、`Mij=kij√(LiLj)`。Cは個別に`ωC/(1/Q−j)`でstamp。L方向反転では関連k符号も反転する。裸のsolverは部品適合ゲートではなく、`validate_components`等を別途実施する。
- 50Ω行／電流スケーリング後の条件数≥1e12、非有限、非SPDはfail closed。この条件数閾値は数値ガードでありRF制約や物理的不可能性ではない。
- 外部境界の独立解法はSHA確認済みRI S2Pを直接port Yへ変換し、源・負荷端点を消去する。forward LPFのnodal/Schur/ABCDを再利用しない。peak phasorの電力は`Re(VI*)/2`、1V peak Theveninの`Pavs=1/(8Re(Zs))`。上の旧RF-T003 **RMS**式と振幅規約を混ぜない。源抵抗損失を入力電力に含めず、S2P差分・L/C散逸・負荷を二重計上しない。

## 過去RF-F003と試験トポロジーの比較境界
**2026年10月の旧条件のみに適用する教訓：** [実行済みの正式/試験別結果](results.md#正式rf-f003旧版とrf-t005t007試験の固定比較2026-10)を参照。制約IDだけでなく実効SHA・可変C個数・接地DTC付属寄生・追加阻止帯・固定外部S2P・測定格子・検証深度を一致させて比較する。旧RF-F003 `f8571020...`や旧RF-T005/T006/T007の局所値を現行schema2の正式RF-F003 `e12c42b1...`の達成値に転用しない。
- **追加阻止帯は通過損失を増やしうる。** RF-T006の全設定3〜6GHz≥20dB追加によりEXP-048は面積5⅓でIL2.920706dB。EXP-049のQ33モデル・面積18でもIL1.166797dBで目標1.1dB未達。Lの公表値域（0.8nH下限）と定数Q/SRF実現性を区別し、20dB達成の狭い0.080dB余裕を物理保証としない。

## 多初期値・座標正規化・有限格子での探索上の教訓（RF-T008旧条件）
**適用範囲：** [#233多初期値](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/6ac982306cd5899dee99b40dee660d3a6986db89/data/validation/issue233_multistart_pilot/README.md)と[#237座標A/B](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/6ac982306cd5899dee99b40dee660d3a6986db89/data/validation/issue237_coordinate_ab/README.md)の**実行済み**有限探索。どちらも `full_lpf`、RF-T008 rev3 **trial**、当時の実効制約SHA `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`、固定外部S2P・全6設定／28不連続区間を使用。現在のschema 2 RF-T008の実効SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`とは別条件であり、現行RF-F003の実績へ転用しない。
- **開始点は収束とRF適合を分けて評価する。** #233は固定3構成×nominal/Sobol 2点の計9 startで数値収束7件、17点/区間の厳密H2/H3≥30dB適合0件。nominal 3本は既存1-startの損失値を再現し、3L0GJMのSobol index 1もnominalに近い損失へ到達したが、適合率や最悪ILの改善は観測されなかった。少数startで多初期値一般の無効性や最適解不在は結論できない。
- **正規化は単独の解決策ではない。** #237は保存済み9初期値を物理座標A／正規化座標Bで各1回比較し、収束A=7/9、B=8/9、17点strict適合は両方0/9だった。両方式ともSciPy 1.18.1の既定絶対有限差分 `eps≈1.49e-8` を各座標単位に適用するため、Bでは物理有限差分幅もbox幅倍に変わる。座標変換だけの因果効果、安定した速度優位、正規化の標準採用は示されていない（実消費stage・nfevも異なる）。

## Pareto支配と配置選択の教訓（RF-T008 rev3の歴史的局所探索）
**出典・有効範囲：** [EXP-058/059・062〜065の整理結果](results.md#rf-t008-v3の横断比較2026-10-20の固定履歴)。固定外部S2Pと6設定・28区間×1,001点、必須H2/H3≥30dB、当時のRF-T008 rev3 trial実効SHA `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`の探索済み部分集合に限る。
- **非劣性は再最適化後の同条件比較で判定する。** 面積4の旧4L/0GJM候補は低面積3⅔に支配されていたが、EXP-064のPCB-C配置探索で非劣点に変わった。局所探索で見つからないことを構成不可能の証明にせず、固定した面積クラスの異接続・異開始点を比較する。
- **探索停止・検証深度をParetoから分離する。** 数値収束、有限格子30dB、84点独立MNA報告、電力保存、35dB公称目標、IL≤0.30dB、連続帯域と製作可能性は異なるゲート。小さな内部guard（約0.005dB）を製造余裕と解釈せず、保存済みMNA結果の監査を新たな独立解法実行と呼ばない。

## 開発Pilotの未収束と性能計測の教訓（RF-T008 schema2、Issue #372/#375/#389/#391/#393）
**条件と出典：** 非EXP・Phase 2の開発専用診断。RF-T008 rev3 **trial opt-in**、実効SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、`full_lpf`、固定入力/出力S2P・全6設定/28不連続区間。#372/#375の同じ4L・2複合Cv入力の初期seedと、#389/#391/#393の最小Worker比較は**別の測定目的とコードHEAD**。正式RF-F003、旧RF-T008実効SHA `7de08611...`、10月の密格子Paretoの証拠とは混同しない。[代表結果・履歴固定リンク](results.md#開発pilotの未収束と限定性能診断2026-11)を参照。
- **予算増加・solver収束・strict RF適合は独立。** #372は2 seedとも3,000評価で予算切れ、#375ではseed1002を6,500まで延長しても予算切れ／RF不適合、seed1001は6,006評価でsolver収束したがRF不適合。局所反復の増量は必須減衰30dBもILも保証しない。科学順位のbest-observed vectorとsolver terminalも別に判定する。
- **目的値の単一指標化は危険。** #375 seed1002は84点格子で最大違反28.516→0.710dB、合計違反388.449→0.957dBへ低下しても、worst ILは途中の0.988dB（1,000評価）から9.279dB（6,500評価）へ悪化。各forward時点の値であり過去bestではない。70点search、84点anytime、476点terminalでは格子と選抜対象を明示し、失敗を低ILのParetoに昇格しない。
- **同等性と速度優位を分ける。** #389の限定最小Worker回帰、#393の旧詳細/新prepared各100-forwardのvector・RF・solver一致はその条件での数値同等性。#393のwall時間差は旧→新の単一順序で測定負荷・cacheを固定しておらず、再現した速度比や現行Worker全体の加速率ではない。plain/timed/profileで計測器の負荷が変わる（#391のcProfile solverはplain中央値より約35%長い）。比較には同じ入力・source SHA・seed・solver・grid/参照面での複数回、順序入替、無計時plain基準と分布の評価が必要。

## 旧RF-F002のsolver・manager設計の教訓（Issue #397）
[旧RF-F002の実測・非収束記録](results.md#旧datavalidationの整理とrf-f002の教訓issue-397)は、現在の正式RF-F003で再実行していない。学ぶべき点は次の四つである。
- **checkpoint端子の写像を保存前に検証する。** 旧EXP-034〜037では元output node 3とmanager node 2のremapを欠き、ベンチ・復旧の検査結果が候補RF再評価結果でない。端子・接地・接続roleと全設定のforward一致を新規実験のG1で明示する。
- **solver成功と厳密RF/ILを分離する。** 旧EXP-038の35dBは`1e−5dB`許容差内で、最悪ILは0.30dB未達。EXP-040のunscaledは非収束で、30dBと35dBの達成度も異なる。9/17点の局所安定性は28×1,001点・独立MNAや連続帯域の保証ではない。
- **旧証拠の退役と現役保存契約は別。** SHA固定のEXP-025〜041原manifestはそのまま保管。履歴索引に限って欠損した旧`data/validation/`補助証拠を除く。現存証拠・直接manifest検証・新規EXPのG0〜G5は厳格なSHA比較を維持する。

## BSF合成と有限Q損失からの設計仮説
以下は2026-10-14の文献・旧RF-T004研究の統合であり、**新規合成の実行報告や現行RF-F003適合の証明ではありません**。元の文献調査・導出全文は[整理前Git tree](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/3370ea4/docs/research)にあります。
- 古典的LPF→BSF変換は `s_LP = B s/(s²+ω₀²)`、`B=ω₂−ω₁`、`ω₀²=ω₁ω₂`。単一BSFの基準にはなるが二重阻止と低域整合を同時には解かない。
- 直接多項式法は `S21=P/E`, `S11=F/E`。Cameron法は有限伝送零点から一般化Chebyshev多項式、N+2結合行列、等価トポロジーへ進む。losslessの `|S11|²+|S21|²=1` は理想応答の条件であり、有限Qで厳密な実軸零点・無限減衰を要求しない。
- 正規化共振モード行列 **Mは物理Lの磁気結合kではない**。行列回転で合法LC・一列配置・全L行列SPDが自動的に得られるわけではない。Corralesの `M_BSF=M_BPF⁻¹` も論文の規格化・可逆条件に限定し、一般のLC行列に適用しない。多項式の反射／透過交換（阻止帯等リップル）と逆行列法（両側の反射等リップル）は別方式。
- 6個の独立合成行列を並べず、固定L/C/配置/結合を共有する低次元族 `M(C1,C2[,C3])` を設計する。H2/H3の中心比約1.5だけでなく、全28個別区間の縁で最小減衰を評価する。零点感度 `Jij=∂log(fzi)/∂Cj` の有効ランク・条件数と通過帯の電流損失を併せて調べる。
- 設計仮説は、固定広帯域阻止セル＋可変零点／整合、二経路の位相干渉、弱結合デュアルモード、extracted-pole/非共振ノードによる零点の局所化。応答合成→許可LCへの写像→有限Qの6設定同時最適化→独立MNA・電力・SPD→SRF/EM/公差を分離する。どの系統の優位性も文献調査だけでは未証明。
- BSFの直接合成の規格化上の制約は[Corrales et al. 2011](https://doi.org/10.2528/PIERL11091512)などが出典。理想合成行列を実回路の磁気kへ同一視しない。
旧RF-T004の手計算：IL≤0.30dBは`GT≥10^(−0.03)=0.933254`、反射＋散逸≤6.675%。旧50Ω→60−j40Ω直結は `GT=4×50×60/|110−j40|²=0.875912`、IL≈0.57539dB。固定LCトラップの `f0=1/(2π√LC)` にC=1.5pF、HV Q25/C Q50を置くと、1.4GHzでL≈8.616nH、`Rtrap=ωL/25+1/(ωCQ50)≈4.55Ω`。50Ω等終端の**孤立シャント1個**なら`|S21|=2Rtrap/(50+2Rtrap)`、減衰≈16.3dB（2.1GHzではL≈3.829nH、R≈3.03Ω、≈19.3dB）。全回路の到達上限ではなく、単発ノッチ依存への警告です。固定C＋0〜1.5pFで1.326〜1.830GHzを動かす比は`fmax/fmin=√((Cfixed+1.5)/Cfixed)`、Cfixed≤約1.658pF。大きな高Q固定Cの追加にも可動範囲の代償があります。
- 損失はワットで`PL=|IL|²ωL/Q`, `PC=|IC|²/(ωCQ)`、`Pavs=Pload+Pref+ΣPL+ΣPC`。反射は発熱ではなく、素子別dBを単純加算しない。実対称の相互誘導項はこのモデルでは無損失。素子だけQ→∞にした凍結回路感度は再最適化後の改善予測でなく、個別改善量も加算不可。

## MinimalWorker性能診断の運用（#401/#408）
開発専用の[単一ベンチ](../scripts/benchmark_minimal_worker.py)は同一Plan・grid・初期vector・source・環境で `plain`（無計時）、`timed`（L1/L2）、`deep`（L3）を区別する。`worker.solve()`の壁時計には前後の物理検査が含まれ、Hybrid単独ではない。後段のbest_x観察は別時間・追加1 forwardとして記録する。タイマー領域はinclusiveで、特に RF ⊃ port ⊃ node ⊃ matrices を加算しない。計器は実solver callbackを包み、失敗を再送出する。
高速化は一仮説ずつ科学回帰後に旧新plainを別process・warmup除外・交互順（例：旧新新旧、各10回以上）で比較する。source/条件/環境と全run・未収束・外れ値を記録し、揺れたら除外せず再測定する。deep値や合成noopの校正を実RFの速度比としない。6設定・28区間、S2P、SPD、受動性・電力保存、独立MNAを既存検証で確認し、ノイズ未満の変更は退役する。[#401原記録と報告](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/26427c9ce08fe166d5dec31640f417c8dfe2ec79/project/diagnostics)、[結果と限界](results.md#minimalworker性能診断issue-401)。正式EXP・RF合格の代用ではない。
