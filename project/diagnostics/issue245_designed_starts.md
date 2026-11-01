# Issue #245 B — インピーダンス変換型初期値の限定prototype

## 範囲と判定

基点 main `f21d828`（Stage A / PR #246）。正式RF-F003、trial RF-T008 rev3/full_lpf
（effective SHA `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`）、
RF forward、全合法bounds、SLSQP v2、歴史EXPは不変更。
**実RFで良い初期値を得られた実装ではない。単純L-match仮説の適用限界を示したprototypeで止める。**
Stage C、本番探索、EXP予約・実行は提供しない。

## APIと候補予算

```python
generate_starts(SampledEpigraph(circuit, 2), nominal_vector, seed=23,
    selection='rf_pareto', candidate_pool='design_prototype',
    max_initial_samples=952)
```

既定は `candidate_pool='sobol'` でStage A/従来の出力を維持。
prototypeはnominal＋設計2本＋同seedのSobol blockのindex 2..15。
設計候補を追加するのではなく、最初のSobol 2枠を置換する。
選別は同じF/V Pareto・正規化多様性、forwardは同じ6設定28区間×2点、strict30。
設計候補は `sobol_index=None, pool_index=0/1`、根拠は `design` に記録。
最大17 forward / 952 requested sample。生成の解析式自体はRF forwardではなくsampleに課金しない。
モデルの入力S2P/出力S2Pは既存evaluatorのSHA検証済配列を使用する。
実際の費用は合法性・停止に依存し、**同じ上限は常に同じ実消費を意味しない**。
`baseline_kind='pool_prefix_only_not_legacy_sobol'` のbaseline列は混合poolの先頭3本であり、
legacy Sobol対照ではない。対照には同じ入力で `candidate_pool='sobol'` を別に実行する。

非法設計・非対応接続・近似解なし・予算不足は `StartSelectionError.report` でfail-closed。
clip/epsilon/修復・黙ったSobolへのfallbackなし。warmとの組合せも拒否する。
全候補vector/SHA・費用/採否・固定座標・最終昇格禁止はStage Aの記録/ゲートを継承する。

## 物理的な仮説（一般的な回路合成器ではない）

対象は**全Lが入出力間の単一路で、Cは入力または出力に1組のIC固定/可変Cだけ**という小範囲。
分枝L、bridge、固定PCB/GJMを含む一般回路は未対応と明示して停止する。
保存3構成への射影やGJM=0の削除はしない。この制限は探索boundsの縮小ではない。

1. 各設定の実在する粗格子pass sampleから、その設定のpass周波数平均に最も近い点を選ぶ。
   同距離では低周波側。ギャップ内に仮のpass sampleを作らない。
2. 出力S2Pに対し `ZL_int=(A ZL+B)/(C ZL+D)`。
   入力S2Pの逆向きABCD `[[D,B],[C,A]]` を外部sourceで終端し `ZS_int` を得る。
   裸の60−j40Ωだけを補償しない。
3. 出力shuntでは `Y=1/ZL_int=G+jH` とし、
   `B=sqrt(G/Re(ZS_int)-G²)-H`, `X=-Im(ZS_int)-Im(1/(Y+jB))`。
   入力shuntでは `Ytarget=1/conj(ZS_int)` とし、
   `t=sqrt(Re(ZL_int)/Re(Ytarget)-Re(ZL_int)²)`,
   `X=t-Im(ZL_int)`, `B=Im(Ytarget)-Im(1/(Re(ZL_int)+jt))`。
   実根なし、X/B<=0はこのlow-pass仮説に適用不能。RFの不可能性証明ではない。
4. B71/B8の2つをanchorに、`Ltotal=X/omega` を直列L数で等分する。
   IC固定Cは既存合法下限を初期仮説に使い、各Cvは
   `Ctotal(anchor)*(f_anchor/f_setting)^2-Cfix`。
   kはゼロの初期仮説。完全vectorを既存box/部品/SPD検査へ渡し、範囲外なら停止する。
   最適化のsigned k、全L/C/Cv独立座標・全合法範囲は一切変更しない。
   LC周波数スケーリングは仮説であり、複雑なLPFの伝送零点ではない。
5. `R_L=omega*L/Q` は各L別の二次損失診断のみ。選別に使うのは既存forwardのF/V。
   高Lのhard cutoffや新しい加重和なし。純直列経路の同一電流近似であり、一般分枝の電流重みは推測しない。

`design.approximate_response` は無損失・非結合・集中L/C仮説を固定S2Pで挟んだ
外部 `Zin=(A ZL+B)/(C ZL+D)` とGTを6代表点で記録する。
これは解析的設計診断で、Q損失を含む既存RF forwardのスコアとは区別する。
S11だけで低IL/H2/H3適合と扱わず、代表点のGTも全区間性能の代わりにしない。

## 検証と限定read-only診断

- `test_phase2_problem_seed.py` の限定1テストに、合成端子条件の生成/全6設定/再現性/合法性、
  固定CとCv、conjugate整合の式、代表点GT、Stage Aと同じ952 sample、Sobol残り14枠一致、
  非法設計と予算不足の部分記録/停止、非対応接続拒否を集約。
  合成正常系はS2P配列をidentity、source=50Ω、入力shuntはload=40−j40Ω、
  出力shuntはload=100−j40Ωへ置いた**テスト内だけのmock**。
  この正常系をRF-T008の科学的結果と主張しない。
- Python 3.12 / `uv sync --frozen` PASS。Pi sparse workflowと同じ15 unittestモジュールを
  分割して実行し、計121件中120 PASS・既存opt-in実SciPy smoke 1件SKIP。
  最初の一括shellは180秒で打ち切られたため、未完のshared-entryとbudgetを別途実行してPASSを確認した。
  `run_phase2_shared.py synthetic --mock --policy RF-T005 --inductors 3` と `git diff --check` PASS。
  shared-entryテストのEXP表示は隔離fixtureで、本リポジトリの実EXP実行ではない。
- 実固定S2Pのread-only診断：L-tree `((0,1),(1,3),(3,2))`、3×LQP02HV、
  physical order `(0,1,2)`、couplings `((0,1),(1,2))`、IC枝1本、固定C枝なし、
  nominal完全vector `[2,2,2,0,0,0.5,1,1,1,1,1,1]`、seed23/coarse2/上限952。
  入力shunt `(0,-1)` と出力shunt `(2,-1)` の2接続だけを確認した。
  - 入力shunt：B71代表652MHzで X=48.908Ω, B=−0.000459352S → 停止。
  - 出力shunt：B12代表716MHzで X=50.748Ω, B=−0.0000720605S → 停止。
  - どちらもnominalの1 forward / 56 requested sampleだけ実行し、設計候補のRF評価前に停止。
  - actual S2PでのA対Bの完成pool比較・性能改善は**未成立**。保存3構成の歴史checkpoint比較は未実施。

単純port-shunt L-matchを一般回路へ無理に投影しない。次に必要なのは、固定Cの最低容量を含む
多段インピーダンス変換と分枝roleを扱う別の小さな仮説のレビューであり、ここではsolverを増設しない。
17点/1001点、独立MNA、電力/passivity、SRF/Q(f)/EM/公差、実SLSQP/DE/L-SHADEは未実施。
後続の公正な実SLSQP対照Issueの予算/G0〜G4案は[Stage A診断](issue245_start_selection.md)を継承するが、
本prototypeを保存3構成へ適用できるようになるまでA+B実対照は開始できない。
