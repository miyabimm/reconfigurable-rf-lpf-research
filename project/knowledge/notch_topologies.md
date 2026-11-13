# シャント共振・整合とπ型ノッチ

**対象：** シャント電流、整合位相、有限C損失、π型の伝送零点とT/π比較。旧研究条件の数値・仮説を現行RF-F003適合と混同しない。
**出典：** [旧methods原文](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/d536a3f1a1b79b8e9be3db4752f1a8b05fa60e65/project/methods.md)（PR #411以前のmain固定版）。内容は既存研究の移設であり、新規RF/MNA実行ではない。

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

決定論的な既存テスト：[モード理論](../../tests/test_t_coupled_modal_theory.py)、
[幾何](../../tests/test_t_coupled_geometry.py)、[2組結合](../../tests/test_t_two_coupling_models.py)、
[シャント電流](../../tests/test_t_shunt_high_current.py)、[整合位相](../../tests/test_t_matched_shunt_high_current.py)、
[π零点](../../tests/test_pi_zero_retarget.py)。当時の会話環境のみのスクリプト・CSV・図はGit登録済みとは扱いません。
完全なベンチ表、参考文献（Neumann、IEEE TMTT 2007/2021の相互損失、Ruiz/Hinojosa 2014のLCノッチ等）、
未実行提案の逐語原文は **Issue #352整理前コミット `a86f47b`** の
[9原典](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/a86f47b/docs)から復元できます。
ファイル名は `phase2_t_coupled_inductor_{q_foundations,uniform_mode,planar_geometry}_20261016.md`、
`phase2_t_{two_pair_coupling,shunt_high_current_modes,shunt_current_matched_passband,pi_common_conditions_loss_comparison}_20261016.md`、
`phase2_pi_{two_pair_coupling,notch_retarget}_20261016.md`。
`git show a86f47b:docs/<ファイル名>` で元文書を読み戻せます。原blobと参照元の全件照合はIssue #352のPRに記録します。
