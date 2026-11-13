# BSFの合成理論と有限Q設計仮説

**対象：** BSF変換、結合行列の適用限界、文献、有限Q・固定/可変Cの探索仮説。旧研究条件の数値・仮説を現行RF-F003適合と混同しない。
**出典：** [旧methods原文](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/d536a3f1a1b79b8e9be3db4752f1a8b05fa60e65/project/methods.md)（PR #411以前のmain固定版）。内容は既存研究の移設であり、新規RF/MNA実行ではない。

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
