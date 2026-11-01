# Issue #248 — 汎用L/C倍率・6設定Cv連動のopt-in初期値

基点main `6f4a5dacc6e986767120aeebea945732c894948c`、親 #245 / PR #246・#247。
正式active **RF-F003**、対象は明示trial **RF-T008 rev3 / full_lpf**、effective SHA
`7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`。
RF bounds・Q・固定S2P・source/load・RF数学・SLSQP v2・歴史証拠は不変更。

## API・仮説・停止規則

```python
generate_starts(SampledEpigraph(circuit, 2), nominal_vector, seed=23,
    selection='rf_pareto', candidate_pool='physical_transform',
    max_initial_samples=952)
```

nominal保持＋同seed/同次元の固定Sobol16枠。0/1枠は元の合法vectorをL/C共通倍率で変換、
2/3枠はCv連動、4..15枠は**元のSobolを完全に保持**。既定None、Stage A `sobol`、
旧B `design_prototype` は不変更。warmとの組合せは未提供。

- 全Lの倍率λ、全PCB/GJM/IC固定/6設定Cvの倍率μを、各boxの `lo/x..hi/x` の交差で決定。
  既存Sobolの座標0/1で区間内を線形補間。kは不変。固定座標は倍率区間を束縛し、0は倍率で0のまま。
  開下限は開区間として扱い、選択点が開端点なら除外。境界epsilon、clip、repairはしない。
  `α=sqrt(λ/μ), β=1/sqrt(λμ)`。理想LCのスケーリング仮説にすぎず、固定S2P・複素負荷・損失を
  含む実回路の整合や阻止特性の保存を主張しない。schema外の内蔵定数Cは変換しない。
- 各設定の実在するUL/DL pass sampleの平均に最も近い点を代表に選ぶ（同距離は低周波）。
  `u_s=(1/f_s²−min(1/f²))/ptp(1/f²)`、各Cv座標のboxへ `lo+u_s*(hi−lo)` と直接写像し、
  `Cnew=.5*Csobol+.5*Ctrend`。IC固定Cと枝順序は不変更。後続の全L/C/k/Cv自由度は独立のまま。
  4/12配分、ρ=.5、代表点、trendは試験仮説で、最適配分やhard monotonic制約ではない。
- 元vectorと変換後vectorをRF forward前に既存box/部品/SPD/roleで検査し、重複も除外。
  変換不能、n_variable=0、退化、非法vectorは理由付きで当該枠のみ廃棄。代替生成や追加forwardなし。
  GJM=0/未証明roleは既存explorationゲートのみ許容し、昇格禁止。0 GJMが開下限に触れる倍率枠は除外。
- 同じStage AのF=max(pass IL)、V=max(0,30−minH2,30−minH3)、Pareto/多様性選別。
  nominal以外に異なる2候補を確保できなければ停止。forward例外/非有限score/予算不足は
  `StartSelectionError.report` に部分費用・失敗を残しfail-closed。
  候補別完全vector/SHA、元vector SHA、seed/slot、倍率/ρ/代表周波数、採否理由と
  requested/completed sample・CPU/wall、全体条件/definition/schema SHAを記録。
  実測CPU/wallはsynthetic previewのrun IDへ混入しない。

## 実固定S2Pの限定対照（ソルバーなし）

[再現スクリプト](issue248_generic_starts.py)で上記mainのEXP-087/089/094 manifest blobから
**保存された完全definitionとnominal入力**を読み、3L0GJM/3L1GJM/4L0GJMを対照した。
歴史checkpointの再認定や完全checkout監査ではない。manifest SHA・完全definition・入力/S2P/帯域SHA・
環境・dirty source SHA・全候補/費用・選抜SHAは[JSON](issue248_generic_starts.json)に保存。
HEADは基点main、実行ソースはdirty treeのSHAで識別する（現行srcの全Pythonファイル指紋）。

全行seed23/coarse2、各 **17合法・0却下、17 forward / requested=completed=952 samples**。
総計 **102 forward / 5712 samples**、追加の候補forward・17/1001点・独立MNAはなし。
表の各候補は `(F,V) dB [vector SHA先頭12桁]`。nominalは両poolで同一。

|構成|pool|nominal (F,V)|選抜low-F候補 (F,V) [SHA]|選抜constraint側 (F,V) [SHA]|実測wall秒|
|---|---|---|---|---|---|
|3L0GJM|A Sobol|(3.368734,23.761742)|(18.127005,24.230656) [8b6f902d6e6c]|(19.301781,18.523372) [6c623b429a95]|0.034928|
|3L0GJM|B-2|(3.368734,23.761742)|(13.320960,28.208807) [0833c88c43c3]|(31.633479,18.426282) [520598010e69]|0.062471|
|3L1GJM|A Sobol|(3.368522,23.762820)|(23.824220,22.442818) [8421aa06bc99]|(44.440433,0) [cb889d5310ee]|0.030296|
|3L1GJM|B-2|(3.368522,23.762820)|(29.220046,23.509068) [1d7d66edcbd5]|(44.440433,0) [cb889d5310ee]|0.031180|
|4L0GJM|A Sobol|(4.038081,24.486336)|(6.753865,18.374574) [c18167a7d69e]|(17.151871,7.420170) [e1837621c693]|0.033941|
|4L0GJM|B-2|(4.038081,24.486336)|(11.294102,14.063590) [036623d55a94]|(17.151871,7.420170) [e1837621c693]|0.035081|

**一律改善は観測されず、有効性は未確定。** 3L0はILと違反のトレードオフ、3L1のlow-F候補は悪化、
4L0もトレードオフ。V=0でもIL適合ではない。初期RF値は最適化後性能・収束・RF適合証明ではない。
wallは短時間1回の実測で速度比較の証拠ではない。部品/SPD/roleの合法性と物理実装成立は別判定。

## 検証・未実施

- Python3.12 / `uv sync --frozen` PASS。新規synthetic 3テストで3L/4L、bridge/shunt、PCB/GJM、
  最大2Cv、固定k、0/開端点/固定・退化box、n_variable=0、SPD却下、非法変換、重複、予算/forward/非有限、
  決定性、12枠一致、preview run IDを検査。
- 既定の凍結SHAテスト、旧BとStage Aの候補全SHA digestを維持。
  mainの旧実装を読み込み、同一synthetic fixtureのA/旧B出力を実測時間だけ除いて直接比較し一致。
- Pi sparse workflowの16 unittestモジュール計**124件：123 PASS・既存実SciPy opt-in 1 SKIP**、
  `run_phase2_shared.py synthetic --mock --policy RF-T005 --inductors 3`、`git diff --check` PASS。
  shared-entryのEXP-050表示は隔離fixtureのみ。
- 実SLSQP/DE/L-SHADE、EXP予約/実行、Stage C、17/1001点・独立MNA・新候補power/passivity、
  連続周波数保証、SRF/Q(f)/EM/公差/実測は **not_run**。既存MNAのソフトウェア回帰とは区別。
  RF-F003適合認定・Phase 3移行・候補昇格はなし。Draft PR後のChatGPT独立レビュー待ち、マージしない。
