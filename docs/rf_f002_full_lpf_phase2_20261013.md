# RF-F002 Phase 2：P4-A ベンチマークと Full-LPF 再合成の中間報告

**状態：Phase 2 継続。正式条件 RF-F002 を維持。Phase 3 移行・`main` へのマージ・制約変更はしていない。**

- 現在の追試ブランチ：`test/rf-f002-full-lpf-recovery-20261014`。基点は最新`origin/main`=`eb1de13841c1b4a74f18f4f9320e0316fbdd478f`（PR #47を含むmain）で、レビュー用[PR #48](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/48)はopen・未merge。
- 先行統合の保存・コミット履歴は2026-10-14の各節に記録。今回の実行は最新main上のEXP-034～041で追試し、mainのEXP-020～033や制約正本を変更していない。
- 後続コミット：scaled solver / Full-LPF runner=`03a6e9f...`、EXP-032条件=`132f6ce...`、EXP-032事前manifest=`c710e0a...`。最新の検証・概算は本書9節を参照。
- RF-F002 effective SHA-256：`f20d27e93451dcec2f823e6f7c3731c06d843050c4d2ace8b0b46ded605542e2`
- 数値実験時の worktree は clean。Python 3.12.15 / NumPy 2.5.4 / SciPy 1.18.1 / scipy-openblas、WSL2、AMD Ryzen 7 PRO 4750G（8 physical / 16 logical CPU、RAM 7.45 GiB）。BLAS/OMP/MKL thread は各1。

## 1. RF-F002 監査と修正

### 維持した正式条件

すべての新しい full-LPF 実験は正式 ID `RF-F002` とその上記 fingerprint を記録する。RF-T003/RF-T004 と PR #38 由来の回路は**初期値・接続候補としてだけ**利用し、過去の試験性能は RF-F002 成果に移し替えない。P4-A matching-only の合格を full-LPF 合格と呼ばない。

RF-F002 の設定値/Q/範囲・6設定で共通の固定部品・6設定別の2枝可変C・B13+B14 の単一設定・結合SPD・停止帯域30 dB必須/35 dB公称目標を変えていない。チップ面積コストは Pareto 評価軸で、hard cap ではない。IC可変Cは Q50、各枝0–1.5 pF。物理結合上限は現行 RF-F002 の強隣接チップペア |k|≤0.15、PCB-PCB |k|≤0.15、チップ-PCB k=0 とし、旧条件の|k|≤0.4を引き継いでいない。

### 発見した実装上の問題

`experiments/matching_limit/p4_batch.py` の `settings_for()` は固定 `GJM01` だけを pF→F 変換し、`PCB_PATTERN_C` は nH→H と誤解釈していた。また `bounds_for()` に PCB_PATTERN_C の明示範囲がなかった。既存の P4-A sampler はこの部品を生成していなかったため、今回の matching-only 数値結果には影響しないが、正式に許可された PCB-C を含む full graph で誤計算を招く。

修正：GJM01 と PCB_PATTERN_C の双方を pF→F 変換し、PCB-C を formal bounds 0.02–0.2 pF に設定。`tests/test_full_lpf.py::test_fixed_pcb_pattern_c_uses_pf_units_and_formal_bounds` で回帰検証した。直列C=0 pF は開放枝のままという試験も通過。

### 検索範囲の監査結論

現 P4-A sampler は正式に許される全グラフ・全部品集合を網羅しない有限 sampler であり、面積/ノード/部品種/配置の上限は実験上の計算範囲であって RF-F002 の正式 hard limit ではない。PCB_PATTERN_C と LQW04 を含むトポロジー生成の拡張、isomorphism を跨いだ全生成段階での重複排除、全cost帯を維持する汎用Pareto探索は今回完了していない。

## 2. P4-A 小規模ベンチマーク（`matching_only` のみ）

### 12 topology / 80 optimizer candidate の再開可能ベンチ

生の manager manifest・各 shard checkpoint は無視対象のローカル `results/` に保存。Run ID：`20261013T160125Z-6d7d7841`、`results/rf-f002-p4-benchmark/20261013T160125Z-6d7d7841/`。

| 指標 | 実測 |
|---|---:|
| 選択グラフ / planned candidate | 12 / 80 |
| 完了 / 収束 / 非収束 / 失敗 / 未実行 | 80 / 73 / 7 / 0 / 0 |
| 中断前 wall / resume 後 wall / 合計 wall | 902.260 / 583.586 / **1,485.846 s** |
| shard累積 worker秒 / candidate | 約2,767 s / **34.6 s** |
| objective評価 | 66,773、candidate当たり中央値638 |
| peak worker RSS / 2-worker合計 RSS | 83.8 MB / **167.4 MB** |
| minimum available RAM / peak host CPU | 6.37 GB / 19.6% |

条件は RF-F002、HV、seed `20261014`、1 topologyあたり初期値2・coupling layouts 2・可変C layouts 最大2、SLSQP最大120 iteration、9 sample/各segment、独立確認21 sample/各segment。中断後は同じrunでresumeし80候補すべてを完了した。

この run の最良 matching-only IL は0.212330 dB、面積cost 4⅔だったが、同じ候補の最小H2=0.469 dB/H3=1.768 dBである。**停止帯域制約を最適化していない matching-only の測定であり、RF-F002 full-LPF 成果ではない。** P4-Aは既存互換の `matching_only` のままである。

### worker 1対2の小さな比較

同一seed・同一4グラフ/4候補、9点、60 iteration、single start、同一 source/BLAS条件。Run IDs：

- 1 worker：`20261013T170321Z-147811fe`、57.960 s、peak total worker RSS 83.5 MB、CPU peak 11.8%。
- 2 workers：`20261013T170428Z-5f59268c`、40.608 s、peak total worker RSS 166.5 MB、CPU peak 17.2%。
- 全候補のグラフID・結果数値は一致。小規模測定の実効 speedup は **1.43×**。

4候補では起動/manager overhead が大きいため、この倍率を大規模・full-LPFに直線外挿しない。両runとも RAM 余裕は約6.3 GB。full-LPF の並列スループットは未測定。

## 3. Full-LPF optimizer と統合試験

`experiments/matching_limit/full_lpf.py` に、既存MNA/正式ポリシー/band読込/独立検証を共有する**固定トポロジー単位の**RF-F002 full-LPF optimizerを追加した。

- 6設定のUL/DL全sampleについて epigraph `min t`, `IL(case,f)≤t` を用いたSLSQP minimax。
- H2/H3 の停止帯域要件を30→35 dBの継続で最適化。全6設定・H2とH3双方を制約に含む。
- 全固定L/C、6設定×2枝の可変C、物理列上の強隣接chip k、PCB-PCB kを同時更新。旧|k|≤0.4候補は初期値もしくは投影後seedにとどめる。
- K行列SPDを制約し、正式部品範囲・明示シリーズ・可変C接続を各設定に適用。
- 各継続stage候補を21点/区間で比較し、H2/H3の30dB必須・35dB目標・IL≤0.30目標を別々に報告。独立validationで全6設定の利得差、電力残差、最小L固有値を保存。
- 出力に実際の部品値・edge/type/unit、設定別可変C、K、面積cost、continuation stages、optimizer状態、資源・入力hashを記録する standalone converter を追加。

`tests/test_full_lpf.py` 9件を含め、**全 unit/integration tests 234件 PASS**。`uv lock --check`、`uv sync --frozen`、`uv pip check`、`git diff --check` もPASS。再現可能な `maxiter=1` integration smoke をLPF-007/T003-5L/T004 seedに対して実行済み。

なお、出力の35dB判定は数値許容差1e-5 dBを含む。密gridは21点/CSV segmentであって連続帯域証明ではない。反復収束、SRF/Q(f)、実部品、公差、寄生、EM、物理結合実現性も保証しない。

## 4. RF-F002条件での実測再合成

PR #38のRF-T004 seed、RF-T003 seed、LPF-007は**条件を固定して再最適化した実行結果だけ**を次表に示す。各raw JSONは `.gitignore` 対象のローカル `results/full-lpf/` にある。共通source commitは実装コミット `fc9d424...`、worktree clean、solver SHA-256 `21dc598203f0d720cd56dbeb9547d8565aa82f93f0978af82855331823c879f9`。9点/segmentで最適化し、独立三方式validationは21点/segment。各runはsingle start・逐次実行。

| RF-F002で再実行した候補 | cost | wall | IL最悪（setting/region） | min H2 / H3 | 30dB必須 | 35dB公称 | IL≤0.30 | optimizer収束 |
|---|---:|---:|---:|---:|---|---|---|---|
| LPF-007 / 120 iter | 6 | 302.0 s | 4.72700 dB (B8/DL) | 34.95895 / 34.78654 dB | PASS | FAIL | FAIL | 未収束 |
| RF-T003 historical 5L `LOW_IL_30p01` seed | 6⅓ | 158.0 s | 3.74501 dB (B26/DL) | 12.28709 / 16.82567 dB | FAIL | FAIL | FAIL | 未収束 |
| RF-T003 historical 5L `MARGIN_30p100` seed | 6⅓ | 276.8 s | 0.639754 dB (B28/DL) | 34.99999999 / 34.99999999 dB | PASS | 1e-5 dB tolerance内 | FAIL | 未収束 |
| RF-T004 `T004-B35`, 第3可変Cを固定化 | 6 | 202.2 s | 9.38691 dB (B28/DL) | 35.00000 / 34.99995 dB | PASS | FAIL（H3不足） | FAIL | 未収束 |
| RF-T004 `T004-D35`, 第3可変Cを固定化 | 6 | 203.9 s | 5.90845 dB (B28/DL) | 34.99730 / 34.99720 dB | PASS | FAIL | FAIL | 未収束 |

RF-T003 5Lの元seedは旧試験の±0.4隣接kおよび一部1.5 pF超のCを含むため、RF-F002開始値に使う際、隣接kは0.15上限にscaleし、超過Cは1.5 pFへclipした。全固定L/Cと設定別2枝CはRF-F002の範囲内で再最適化。旧数値をRF-F002へ流用していない。5L `MARGIN_30p100` runは30dBを満たすbest-foundで、35dBはfloat差9e-9 dB程度のため1e-5許容差内扱い。**ただし最適化は未収束でIL目標0.30 dBから0.340 dB不足**し、正式目標達成とはしない。

共通して三方式間最大gain差は約2.8e-15–4.7e-15、最大電力残差は約8.8e-18–1.0e-17 W。run別最小L固有値は正。これは数値実装間の整合であって連続帯域・物理実装の証明ではない。

Full-LPF solver上で今回測定したwall範囲は**158–302秒/seed**（中央値204秒）、process peak RSSは約82 MB/逐次worker。観測runの中に `converged=True` かつIL≤0.30 dBを同時に満たすものはない。最良harmonic-feasible（30 dB、35 dBは数値許容差内）もIL 0.639754 dBで未達。LPF-007/T004も大幅にIL未達。area/performance frontierはこの限定された5 startの観測に限り、大域最適性を示さない。

## 5. S1/S2/S3 実測ベース概算と安全な次段階

以下は**full-LPFの1 topology × 1 layout × 1 seed start**だけを行う場合の概算。実測5 runの158–302秒を使用し、systematic topology generation、複数layout/start、失敗・resume overhead、frequency refinement、runner overheadを含めない。2-worker理想欄は完全に線形分割できる仮定であり、full-LPF 2-workerをまだ実測していない。

| 規模 | 1 worker（実測158–302 s/seed） | 2 worker・理想半減 | 実行状態 |
|---|---:|---:|---|
| S1 100 candidate seed | 4.4–8.4 h（中央値約5.7 h） | 2.2–4.2 h | **未起動** |
| S2 1,000 seed | 43.9–83.9 h（中央値約56.7 h） | 22.0–42.0 h | **未起動** |
| S3 10,000 seed | 18.3–35.0 日（中央値約23.6日） | 9.2–17.5 日 | **未起動** |

別測定の小規模 P4 matching-only では2-worker speedup 1.43×だった。これを仮に当てはめると2-workerの見積もりは理想欄より約40%長くなるが、問題設定が異なるため参考値にとどめる。現状は8 physical core・16 logical・約6.4 GB空きRAM。P4 2-worker runのRSSは167 MB、full-LPF single workerは82 MB。最初の実full-LPF 並列試験は**2 workers・BLAS各1 thread**、常時1.5 GiB以上の空きRAMをmanagerでゲートする設計が妥当。4 workerへ増やす実測根拠はない。

### 大規模S1をまだ起動しない理由

Full-LPF 数値solverと候補個別の変換器はあるが、**full-LPF用の複数トポロジー生成・費用層を保つ重複排除・multi-start orchestration・shard/checkpoint/resume manager・全結果Pareto aggregatorは未統合**である。当時のmatching-only managerはfull-LPFの実行入口ではなかった。従って上表はS1/S2/S3の測定ベース予算であって、実行可能なfull-LPF run plan/完了runではない。無制限バッチは起動していない。


## 6. 保存証跡

`.gitignore`対象の`results/`にある実行時raw filesを、監査可能なチェックポイントとして次の追跡対象にも保存した：

- [`data/validation/rf_f002_phase2_20261013/summary.json`](../data/validation/rf_f002_phase2_20261013/summary.json)：条件hash、実行commit、ベンチマーク/Full-LPF主要指標と限界。
- [`p4-benchmark/`](../data/validation/rf_f002_phase2_20261013/p4-benchmark/)：matching-only 80候補のmanager manifest・aggregate・status。
- [`worker-compare/`](../data/validation/rf_f002_phase2_20261013/worker-compare/)：1/2 worker比較の両manifest・statusと、同一4候補の保存値をbyte-for-byte比較した`candidate-comparison.json`。
- [`full-lpf/`](../data/validation/rf_f002_phase2_20261013/full-lpf/)：LPF-007、RF-T003 5Lの2 seed、RF-T004 B35/D35の5回分の完全JSON（設定、stage候補、独立MNA結果、resource metadataを含む）。
- 最新mainとの統合時、先行するmainのEXP IDを上書きしないよう、このローカル系列のmanifestはEXP-025～EXP-031へ再採番した（対応表は本書末尾）。`data/experiment_index.csv`には再採番後のIDのみ登録。これらのmanifestは実行後にraw recorderから作成したことをlimitationsに残し、事前manifest生成済みとは主張しない。

元のローカル実行ディレクトリも保存してある：P4-A 80候補は`results/rf-f002-p4-benchmark/20261013T160125Z-6d7d7841/`、worker比較は`results/rf-f002-worker-compare/20261013T170321Z-147811fe/`と`.../20261013T170428Z-5f59268c/`、Full-LPFは`results/full-lpf/rf-f002-*-current.json`。追跡されたJSONはそのraw fileの内容をSHA付きで保存したコピーである。

これらはRF-F002の有限局所探索記録であり、RF-F002目標IL≤0.30 dBの達成解ではない。

## 9. 2026-10-14 統合後のFull-LPF runner実測・optimizer追試・資源予測更新

### 統合・runner・bounded smoke

作業ブランチは最新main `5dbd832...` を基点とし、main側の既存EXP-020～024を保持した。ローカル既存manifestはEXP-025～031へ移し、索引を再生成。RF-F002 JSON、registry、`data/bands.csv` は不変更。統合コミット`ce2f8c7...`に続き、専用runner/worker・scaled optimizerを`03a6e9f...`へ記録した。正式条件SHA-256は全実行で`f20d27e93451dcec2f823e6f7c3731c06d843050c4d2ace8b0b46ded605542e2`。

当時のRF-F002用full_lpf managerとworkerはRF-T003 seedを初期値のみに限定した。bounded task count / wall-time / worker timeout、最低1.5GiB空きRAM gate、最大2 worker、各BLAS/OpenMP/NumExpr thread=1、config・source・policy・band hashによるresume互換性、atomic result/status、manager/worker OS lock、欠落/重複-aware aggregateを実装。再開/資源gate/lock/aggregate試験は追加した。P4-A `matching_only` は変更しない。統合branch全体のregressionは**240 tests PASS**。`uv lock --check`、`uv sync --frozen`、`uv pip check`、experiment manifest/result/provenance audits、PCB-tunable guard、`py_compile`、`git diff --check`もPASS。RF-F002正本・registry・bandsの差分はない。

EXP-032は**事前登録済み**の1 topology・4 start runner smoke。最適化は各stage5 iteration、9点/segment（independent check 21点/segment）のみで、4 startすべて非収束・30dB mandatory H2/H3未達である。したがって性能候補の探索結果ではなく、runner起動・resource・worker scaling確認だけである。結果・両runのmanifest/status/aggregate・全task JSONは[`rf_f002_full_lpf_manager_benchmark_20261014/`](../data/validation/rf_f002_full_lpf_manager_benchmark_20261014/)に保存。

| worker | 4 start wall | speedup | 最大aggregate worker RSS | minimum available RAM | 結果値の一致 |
|---:|---:|---:|---:|---:|---|
| 1 | 136.633 s | 1.00× | 82.1 MB | 6.34 GB | 基準 |
| 2 | 73.734 s | **1.853×** | 164.2 MB | 6.29 GB | time/RSS除外後、全taskの数値結果一致 |

2-worker倍率は5 iterationの短いsmokeで測定したものであり、120 iterationの長時間runへ保証付き外挿はしない。RAM gate 1.5GiBに対して実測available RAMは十分残った。中断/resumeのhash/lock機構はunit testで検証したが、この4-start smokeを実停止させたわけではない。

### Scaled optimizer追試

EXP-033は実行後登録であることをmanifestに明記した1 seed追試。旧trial `MARGIN_30p100`の初期値をRF-F002下で再最適化し、solver内の物理設計変数を[-1,+1]へ正規化（dB epigraphは非scale）、最大120 iteration/stage、9点/segment、独立check21点/segmentとした。実行commit`03a6e9f...`はcleanで、solver/runner source snapshotのSHAはoutputと一致する。

30dB stageは120 iterationで未収束・最大制約違反0.00302dB。35dB stageは54 iterationでSLSQP成功、H2/H3は34.9999999972/34.9999999992 dBで1e-5 dB tolerance内。worst ILは0.6397543678dB、壁時計480.911sであり**IL≤0.30dBを満たす解ではない**。これは1 startのlocal SLSQP結果で一般収束性や最適性は示さない。eps=1e-5の有限差分診断は不適合停止したため棄却し、SciPy既定epsに戻した。中間diagnostic outputとそのprovenance caveatを含む[`rf_f002_convergence_20261014/`](../data/validation/rf_f002_convergence_20261014/)を参照。

### S1/S2/S3予算の更新

Full-LPF単一startの実測時間158–481s（初期の3 seedとscaled 120-iteration追試の範囲）から単純比例した計画値。これは統計的上限/信頼区間ではなく、トポロジー生成・失敗・再試行・適応格子overheadも含まない。2-worker欄はEXP-032の1.853×を仮置きした**未検証の参考シナリオ**。

|規模|1 worker|2 worker（短時間倍率が続く仮定）|
|---|---:|---:|
|S1 100 starts|4.39–13.36 h|2.37–7.21 h|
|S2 1,000 starts|1.83–5.57 d|0.99–3.00 d|
|S3 10,000 starts|18.29–55.66 d|9.87–30.04 d|

4-start smokeのpeak RSSは1 worker約82.1MB、2 worker合計164.2MB。S1/S2/S3は**すべて未起動**。大規模探索前に、拡張component alphabet/cost-bin coverageを含むtopology generator、grid adaptation、長めの2-worker throughput、fresh resume実機試験を別途レビューする。

### 維持する境界・統合状態

当時のEXP-032/033を含む先行統合ではRF-F002でIL≤0.30dBを満たす候補がなかった。先行レビュー[PR #47](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/47)はその後mainへ統合され、現行baseは`eb1de138...`。今回のEXP-034～041追試branchは未mergeであり、Phase 2を継続する。

## 7. 最新main統合・保存チェックポイントの数値再現（2026-10-14）

成果保全後、最新GitHub main `5dbd83217f7c8bb9acd0c9fefd9f4f1ea07d4f89` から作業ブランチを作成し、先行するP4-A由来EXP-020～024の回路記録・manifest・索引行を一切上書きせず、ローカル成果を統合した。RF-F002 effective SHA-256は引き続き`f20d27e93451dcec2f823e6f7c3731c06d843050c4d2ace8b0b46ded605542e2`で不変。再採番は実験分類や条件を変更せず、既存raw結果・チェックポイント・元run ID・制約ハッシュ・検証履歴も変更しない。

| 統合前ローカルID | main上の保存ID | 内容 |
|---|---|---|
| EXP-020 | EXP-025 | P4-A `matching_only` 12 topology / 80 candidates |
| EXP-021 | EXP-026 | P4-A `matching_only` 1/2 worker microbenchmark |
| EXP-022 | EXP-027 | LPF-007 seedのRF-F002再最適化 |
| EXP-023 | EXP-028 | RF-T003 LOW_IL seedのRF-F002再最適化 |
| EXP-024 | EXP-029 | RF-T003 MARGIN seedのRF-F002再最適化 |
| EXP-025 | EXP-030 | RF-T004 B35 seedのRF-F002再最適化 |
| EXP-026 | EXP-031 | RF-T004 D35 seedのRF-F002再最適化 |

mainの既存EXP-020（RF-T004 PR #38 archive）、EXP-021（4L bridge）、EXP-022（area-six trial）、EXP-023（RF-F002 2-variable-C）、EXP-024（branch archive）はそのまま保持した。新IDは実験索引で未使用であることを確認し、索引はmanifestから再生成・監査する。最適化器を後続改良するため、旧runで実際に使った`full_lpf.py`とT003再最適化scriptは [`code_snapshot/`](../data/validation/rf_f002_phase2_20261013/code_snapshot/) にSHA一致のまま保存し、新しいcurrent sourceを過去runの実行コードとして読み替えない。

保存回路を7001点/各CSV区間で再評価した結果（metric差は保存checkpointとの差）：

| 候補 | 保存IL / 再評価IL [dB] | 保存min H2 / 再評価 [dB] | 保存min H3 / 再評価 [dB] | 最大絶対差 |
|---|---:|---:|---:|---:|
| EXP-023 30dB | 0.381014384960942 / 0.381014384960938 | 30.009999998420 / 30.009999998420 | 30.009999997441 / 30.009999997441 | 2.2×10⁻¹⁴ dB |
| EXP-023 35dB | 0.460180295393763 / 0.460180295393757 | 35.019999999861 / 35.019999999861 | 35.019999999736 / 35.019999999736 | 1.2×10⁻¹³ dB |
| EXP-017 `EXP017-LQW2-H35` | 0.378797914107362 / 0.378797914107364 | 35.029999999610 / 35.029999999610 | 35.029999998751 / 35.029999998751 | 1.3×10⁻¹³ dB |

上記3回路は保存したチェックポイントと1e-5 dB以内で再現した。これは有限周波数格子上の数値再現であり連続帯域証明ではない。IL≤0.30 dBはいずれも未達。再計算出力、checkpoint/script SHA-256、期待値との差分は[`data/validation/rf_f002_checkpoint_reproduction_20261014/`](../data/validation/rf_f002_checkpoint_reproduction_20261014/)に保存。

EXP-017 READMEに記載の近接30dB候補（最悪IL 0.301248245 dB）については、最新mainのtracked historyにも利用可能な回路定数JSON/6設定可変Cベクトルがなく、**数値再現できなかった**。`data/validation/exp017_20261012/checkpoints.json`にある別の過去候補は旧/非canonical条件で異なる回路であり代用していない。値を推定・再構築してRF-F002チェックポイントと呼ぶことはしない。回路ベクトルを保存する追加が必要。

## 8. 維持する判定境界

- 現時点でRF-F002 IL≤0.30 dBを満たす収束・独立検証済み候補は確認できていない。
- `matching_only`、RF-T003/RF-T004の元性能、再最適化後のRF-F002性能は別々に保持する。
- 有限グリッドの数値/MNA再現は、連続周波数保証・大域最適・SRF/Q(f)/寄生/EM/公差/実装の証明ではない。
- 本変更・検証をもってPhase 3には進まず、制約正本は変更しない。mainへのmergeは実施していない。

## 10. 最新mainからのrunner実停止・再開、候補warm-start、スケーリング追試（2026-10-14）

今回の追試branchは`test/rf-f002-full-lpf-recovery-20261014`、基点は`origin/main`=`eb1de13841c1b4a74f18f4f9320e0316fbdd478f`（PR #47を含むmain）。RF-F002 fingerprintは引き続き`f20d27e93451dcec2f823e6f7c3731c06d843050c4d2ace8b0b46ded605542e2`。正式制約JSON、registry、`data/bands.csv`、Phase 2判定は不変更。最終unittest discoveryは**246件PASS**。`uv lock --check`、`uv sync --frozen`、`uv pip check`、manifest/result audit、PCB-tunable guard、`py_compile`、制約ファイルのorigin/main比較、`git diff --check`もPASS。

### 10.1 実プロセス停止・resume・hash/lock integrity

- EXP-034で2 worker稼働中にmanagerへSIGINT。managerは両workerへSIGTERMを送り、結果未完了taskをpendingとして保存した。最初の試験configは`max_attempts=1`だったため、停止分を再試行できずresume結果はpartialになった（設定した総試行回数を正しく守った結果）。
- 同EXP-034でmanagerだけにSIGTERMを送り異常終了させたケースでは、子workerは継承file descriptorのOS lockを保持して処理を継続。残存PID/lockがある間のresumeは拒否され、両worker終了後にresumeするとatomic resultを採用し、attempts=1のままcompletedとなった。完了済みtaskは再実行されていない。
- EXP-036では`max_attempts=2`を事前登録してSIGINT試験を反復。稼働中の両PIDを確認後にSIGINTを送り、managerがworkerを停止。resumeはSLSQP途中状態ではなく各初期ベクトルから再実行し、2件completed（attempts=2）。最大5 iteration/stageのrunner testであり、性能候補ではない。
- 完了runのresult JSON変更、task payload変更、source hash変更、RF-F002 fingerprint変更を**各独立の使い捨てcopyでのみ**試し、aggregate/resumeが全件拒否することを確認。元の完了runは変更していない。lock fileは削除していない。
- raw manifest/status/task/result/logと判定は[`rf_f002_recovery_20261014/`](../data/validation/rf_f002_recovery_20261014/)に保存。EXP-034の初回SIGINT configは最大試行回数不足でpartial、EXP-036が再試行可能設定での成功証拠である。

### 10.2 1/2 worker 完了benchmarkとseed import端子対応の修正

事前登録EXP-035は同一4 task・same config hash・20 iteration/stage・9点/segment・21点/segment検証を1 worker/2 workerで正常完了した。manager wallは**347.126/201.347秒**、speedup **1.724×**、peak aggregate worker RSS **82.36/163.98 MB**、最低available RAMは6.34/6.29 GB。worker実行数値はruntime/resource/integrity fieldを除いて完全一致。これは4 taskの短いthroughput測定であり長時間runへspeedupを保証しない。

実行後のseed import監査で重大な注意点が判明した。保存EXP-017/023はground=0/source=1/load=3を使う一方、`FullLPFProblem`のcanonical graphはground=0/source=1/load=2を前提にする。EXP-034/035/036/037の初期configの一部はsource edge番号を正規化せず渡しており、**その数値出力を保存checkpointのwarm-start再評価として扱ってはならない**。EXP-035の同一入力によるworker scaling・RAM・数値再現確認は有効なmanager benchmarkだが、候補のIL/H2/H3結果はcheckpoint性能の比較から除外する。EXP-037の長いrunも候補品質 evidence から除外し、manager task実行recordとしてのみ保持した。

再発防止として[`scripts/full_lpf_checkpoint_import.py`](../scripts/full_lpf_checkpoint_import.py)を追加し、saved node IDsをground/source/load=0/1/2へ明示的にremap。回帰テストは初期MNA値をチェックし、21点/segmentでEXP-023の0.460180295/35.020000/35.020000 dB、EXP-017の0.378797914/35.030000/35.030000 dBを再現する。managerの一般graph validatorだけでは端子の意図は復元できないため、保存候補importにはこのhelperを使う。

### 10.3 正しいterminal mappingでのwarm-start・multi-startとstaged grid

**EXP-038**はcanonical remap済みのEXP-023/017 exact warm-startと、各0.5%-of-bound deterministic perturbationの計4 task（2 topology）を60 max iteration/stage、`ftol=1e-8`、scaled variables、30→35 dB continuationで実行。4件すべて30/35 dB stageがSLSQP成功し、独立21点/segment検証で35 dB目標を1e-5 dB tolerance内で満たした。perturbed startsは各exact startとほぼ同じ局所解（IL差<6e-12 dB）に収束。

| source warm-start | 保存IL [dB] | EXP-038 exact-start IL [dB] | min H2/H3 [dB] | IL≤0.30 |
|---|---:|---:|---:|---|
| EXP-023 4L/2C | 0.4601802954 | **0.4598082052** | 34.9999999990 / 34.9999999994 | 未達 |
| EXP-017 `LQW2-H35` | 0.3787979141 | **0.3783490996** | 34.9999999975 / 34.9999999963 | 未達 |

これは改善だが差はそれぞれ約0.000372/0.000449 dBで、最終目標0.30 dBを達成しない。35 dB minimaは両方とも30→35継続のSLSQP結果で、1e-5 dB feasibility tolerance内。完全な周波数証明ではない。

**EXP-039**ではEXP-038の最適化出力をwarm-startとしてuniform frequency gridを9→17点/segmentへ段階増密し、独立21点/segmentで確認。IL差はEXP-023で−6.0e-12 dB、EXP-017で−9.6e-13 dB。両解は安定して35 dB条件を保ったがIL≤0.30には届かない。これはstaged uniform refinementであってlocal adaptive refinementではなく、連続帯域保証でもない。

### 10.4 scaling・FTOL・residual分類・unscaled follow-up

EXP-040では同一2 checkpoint starts/initial vectors、同一9点grid、同一60 maxiter/stageでscaled/unscaledとFTOLを対比した。

- **scaled / FTOL=1e-8**（現行推奨）：両startで収束し、EXP-017 IL 0.3783490996 dB、H2/H3は35 dB within 1e-5、stage最大制約違反3.7e-9 dB。
- **scaled / FTOL=1e-6**：同等のIL（差<2e-10 dB）で両start収束。最大residualは2.1e-7 dBで1e-5 tolerance内。収束品質向上は見えず、既定FTOLを変更する根拠にはならない。
- **unscaled / FTOL=1e-8**：4 stageすべて60 iteration上限に到達し、SLSQPは全2 startで未収束。EXP-023はIL0.464235 dB、35 dBを約0.0081 dB miss。EXP-017はIL0.3186931915 dBの30 dB stageを見つけたがraw H2/H3は29.999999819/29.999998786 dB（1e-5 feasibility tolerance内）、35 dB stageは未達。unscaledは同候補のscaled 35 dB結果より低ILだが減衰余裕と収束を失うtradeoffで、標準solver条件にはしない。

optimizer成功statusとpost-hoc constraint residualは別々に読む。EXP-040 unscaled EXP-017はSLSQP未収束だが30 dB stage residualは1e-5 tolerance内、名目35 dB residualは未達。feasibility toleranceだけをoptimizer convergenceと読み替えない。

EXP-041でEXP-040 unscaledのEXP-017 30 dB stageをwarm-startし、120 iteration/stageで継続。30 dB stageは3 iteration、35 dB stageは72 iterationで収束。requirement別best-foundは:

| requirement stage | worst IL [dB] | min H2/H3 [dB] | 状態 |
|---|---:|---:|---|
| mandatory 30 dB（1e-5 dB tolerance内） | **0.3186931893** | 29.9999999969 / 29.9999999987 | 30dB boundary近傍、35dB未達 |
| nominal 35 dB（1e-5 dB tolerance内） | 0.3783490996 | 34.9999999958 / 34.9999999990 | 35dB内、IL未達 |

30 dB点のILは元EXP-017 H35保存値0.3787979141 dBより約0.060105 dB低いが、H2/H3は生値で厳密な30 dBを約3e-9 dBだけ下回り、optimizer toleranceでのみfeasibleと分類されている。IL≤0.30 dBとの差は0.018693 dB。1001点/segmentの追加確認でも同じ極値を得て、独立MNA gain mismatch≤3.4e-15、power residual≤2.9e-17 W。有限gridの結果であり、連続band・実装保証ではない。候補としては境界的なPhase 2 数値seedにとどめ、35dB nominal解と同一の要件として扱わない。

### 10.5 更新されたS1/S2/S3予算と開始判断

EXP-038の正しくmappedされた4 warm/multi startsは各約96.7–145.0 worker seconds（60 max iteration/stage、実際は収束で早期停止）。この限定sampleを単純100倍し、topology generation・failure/retry・grid refinement overheadを除いた予算は:

| batch | 1 worker換算 | 2 worker仮置き（1.724×を仮定） | 実施 |
|---|---:|---:|---|
| S1: 100 starts | 2.7–4.0 h | 1.6–2.3 h | **未実施** |
| S2: 1,000 starts | 1.12–1.68 d | 0.65–0.97 d | **未実施** |
| S3: 10,000 starts | 11.2–16.8 d | 6.5–9.7 d | **未実施** |

2-worker欄は4 task/20 iterationのEXP-035で観測した倍率を仮置きしただけで、長いcorrectly-mapped runで1/2-workerの対照測定はしていない。EXP-038は2workerだけの実測wall 264.0s/4 tasks。CPU/RAM上は2-workerで問題なかったが、**現時点ではS1を開始しない**。理由はIL目標0.30 dB未達、30 dB点は厳密閾値に余裕なし、unscaled改善はnominal35/convergenceとtradeoff、P4-Aのfull component/cost topology coverageが未証明であり、100グラフを追加しても候補品質改善の根拠が弱い。次は境界候補の数値robustnessとsolver条件を小さくレビューし、必要なら同一correctly-mapped candidatesでworker count比較を長めに行ってから新たな有限S1案を事前登録する。S1/S2/S3・Phase 3はいずれも開始していない。

### 10.6 保存先と最終境界

追試全体の集約summaryは[`rf_f002_phase2_followup_20261014/summary.json`](../data/validation/rf_f002_phase2_followup_20261014/summary.json)。実験ledger EXP-034～041は`data/experiment_index.csv`と対応manifestで監査。live recovery raw evidenceは[`rf_f002_recovery_20261014/`](../data/validation/rf_f002_recovery_20261014/)、corrected checkpoint/importer/warm-startは[`rf_f002_checkpoint_warmstarts_20261014/`](../data/validation/rf_f002_checkpoint_warmstarts_20261014/)、9→17 gridは[`rf_f002_grid_refinement_20261014/`](../data/validation/rf_f002_grid_refinement_20261014/)、scaled/unscaled/FTOLは[`rf_f002_solver_ablation_20261014/`](../data/validation/rf_f002_solver_ablation_20261014/)、1001点 unscaled follow-upは[`rf_f002_unscaled_followup_20261014/`](../data/validation/rf_f002_unscaled_followup_20261014/)にある。誤mappingで作られた過去taskはlimitationsに明記して候補比較から除外した。

**判定：Phase 2継続、RF-F002不変、`matching_only`と`full_lpf`は別目的、trial条件は初期値だけ、100 graph S1未開始、Phase 3停止、main未変更・未merge。** 数値結果はfinite-grid/MNAのみ。SRF、実Q(f)、parasitic、EM、tolerance、manufacturing、physical implementationは未確認。
