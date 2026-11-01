# Issue #233：固定3構成×3-start実SciPyパイロット

## 結論と範囲

**9 startを各1回実行、収束7・未収束2・例外失敗0・未開始0。18 stage / 12,206 nfev、回復操作0。**
3点checked選別0、17点のH2/H3厳密30dB適合0。35dB・IL≤0.30dBも0。
よって高密度1001点・独立branch-current MNA84点・passivity/power balanceは全件 `not_run`。
これは承認済み停止／検証条件に沿った結果であり、RF PASSや探索不能性の証明ではない。

- Issue: <https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/233>
- 明示trial **RF-T008 rev3 / full_lpf**、実効SHA `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`。
- source/main科学ソース：`355b977`（`f8c88e3`との差分は中央予約9行のみ）。実行途中の科学ソース変更なし。
- formal RF-F003、Phase 2、source50Ω/load60−j40Ω、全固定外部S2P、全6設定/28不連続区間、Q・signed k・IC固定C併設を不変更。
- seed=23、nominal＋scrambled Sobol index0/1。各構成16点blockのうち先頭2点が合法、再seed・warm差替え・再試行なし。
- 既存 `run_one_start(..., optimize_stage=scipy_slsqp_stage, timeout_seconds=300)` を使用。coarse2/fine3点、標準v2 240/120（回復上限500/280）、全thread指定1。timeoutはstage境界の協調式でありhard wall-clock制限ではない。
- 科学コード・ドライバ・RF入力・歴史EXP原本の変更なし。9件の新EXPのmanifestには後続17点overlayへの参照だけを追加し、実行結果・元summary・planned入力を上書きしていない。

## 全9 startの結果

順序は固定した生成順。中央予約の非同期完了によりEXP番号の大小とは一致しない。
IL・H2は17点/各区間（476 samples、6設定合計）のexternal-port forward診断値。
全件component/box/role/全L行列SPDはPASS。数値収束・EPIGRAPH・RF適合は別判定。
全精度のH3、2/3点各段階、完全vector・SHA・停止メッセージ・nfevは各overlayとEXP summaryを参照。

|順|構成/面積|EXP|start|粗/精status|17点worst IL [dB]|17点min H2 [dB]|厳密30dB|
|---:|---|---|---|---|---:|---:|---|
|1|3L0GJM / 3|087|nominal|0/0|1.361978466421|29.99999989789343|FAIL|
|2|3L0GJM / 3|086|Sobol 0|8/8|7.950033417043|16.79240454659588|FAIL|
|3|3L0GJM / 3|088|Sobol 1|0/0|1.361978466146|29.99999988586123|FAIL|
|4|3L1GJM / 11/3|089|nominal|0/0|1.120318970880|29.99999995132242|FAIL|
|5|3L1GJM / 11/3|090|Sobol 0|0/0|25.605759763818|29.999949257957148|FAIL|
|6|3L1GJM / 11/3|091|Sobol 1|0/0|31.148088710033|29.713319322336265|FAIL|
|7|4L0GJM / 4|094|nominal|0/0|1.110074108221|29.99999999883604|FAIL|
|8|4L0GJM / 4|092|Sobol 0|0/0|8.069326667902|29.99999999999385|FAIL|
|9|4L0GJM / 4|093|Sobol 1|4/4|30.203757366032|16.00793944728984|FAIL|

- **nominal3本はPR #230の対応する1-start診断値を再現。** 3L0GJM/Sobol 1も実質同ILへ到達。他のSobolは高損失または未収束。今回の範囲で適合率・ILの改善は観測しなかった。多初期値一般の有効性や大域最適性を判定したものではない。
- **EXP-091の格子依存**：3点ではH2=30.00000000002153、H3=35.20079203442586dB。しかしEPIGRAPHの最小passband残差は−1.2615686273420579e−11dBでchecked選別対象外。17点ではH2が29.713319322336265dB（B28、1422.875MHz）に低下。3点H2/H3だけをPASSと呼んではならない。
- EXP-090も3点H2=29.99999968509387から17点29.999949257957148dBへ低下。17点は1001点・連続帯域・独立MNAの代用ではない。
- **代表的未収束**：EXP-086はstatus8/8、EXP-093はstatus4/4。最終EPIGRAPH変数は各約−2.50e7、−5.15e16dBへ破綻しており、物理ILとして扱わない。表のILは最終完全回路vectorをforward再評価した値。粗非収束＋精非収束なのでv2で回復増額なし。
- **厳密判定**：30dB直下値を丸めや許容差でPASSへ変更していない。収束7件も全て17点厳密FAIL。適合Pareto集合は空で、ILだけの非劣点をRF適合Paretoとして昇格させない。

## 歴史比較（外部参照のみ）

同じRF実効SHAの保存済み参照値：面積3でEXP-058 **1.0103502552079047dB**、11/3でEXP-058/063 **0.9340275796118456dB**、4でEXP-064 **0.9291267813958661dB**。
出典は `data/pareto_snapshots/rf_t008_exp062_exp063_exp064_cross_pr_20261020.json`。
原manifestと全登録証拠のファイルSHAを照合し、格子・独立検証深度を `report.json.historical` に記録した。
EXP-063は28×1001点/独立7×7 branch-current MNA84点、EXP-064は28×1001点/独立9×9 MNA84点。
EXP-058のmanifestはanalysis_grid欄nullだがsearch_scopeにdense1001点と3 probes/intervalを記録している。この区別をそのまま保存した。

歴史側の探索は粗7/精17点、30.005dB内部guard等を含む。今回の粗2/精3点・内部30.0dBとは異なり、接続も同一ではない。
同じ条件IDだけを根拠に今回の17点結果と同水準のPareto順位へ混合しない。snapshotの当時Draft記載は歴史状態として保持し、現在のマージ状態へ書き換えない。今回歴史vectorの密格子/MNAを再実行したものではない。

## 証拠とゲート

- G0：指定main CI [41204162115](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/41204162115) SUCCESSを確認後、3構成のキー/面積/元manifest/合法性と全9 startをsolver0回で固定。正式予約はmain `355b977` までの `issue233-start1..9`。
- G1：全9件planned manifest/storage/indexをcommit **`f6ed6d4312d215284330215e2ef0adae38a8d1da`**、push。remote refから全ファイルのbyte読戻しと、全9件 `prepare_one_start` / storage preflightをPASS後に最初のG2を開始。
- G2/G3：各1回の既存SciPy driver実行→local finalizeの2 commit/HEAD読戻し→push/remote読戻し/保存監査PASS後に次startへ。各remote SHAは各overlayの `gates` に記録。例外・STOP・timeout・容量超過なし。全18 stage、最大36 stageの範囲内。
- 後続17点は各 `EXP-NNN-17pt.json` に別overlayとして保存。`storage_record.validation_overlays.status=failed` は**17点厳密30dBの不適合**を示す。forward計算や保存監査の失敗、solver例外の意味ではない。
- 新9件以外のindex行・歴史manifest/ベクトル/検証状態は不変更。rawは `results/EXP-086..094/run.json` に保持し、G5削除なし。
- 保存完了は科学PASSではない。独立MNA/密格子/power/passivityは対象候補0のためnot_run。Q(f)/SRF/EM/公差/測定、実レイアウト、物理的同時signed k成立も未確認。

## 検証とレビュー

実行済み：`uv sync --frozen`、`test_phase2_problem_seed.py` **8件PASS**、`test_phase2_shared_entry.py` **5件PASS**、全9 G1/G3監査・遠隔byte読戻しPASS。
初回の `test_phase2_multistart.py` 指定は該当ファイルなしで0件/exit5だったため、既存 `test_phase2_problem_seed.py` のmultistart/17点テストを実行し直した（科学EXPの再試行ではない）。
初回PR CI [41207481103](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/41207481103) は `Experiment index differs from manifests` でFAIL。新9行を生成順に追加したが、既存index生成器はEXP番号順を要求するため、新9行だけを番号順へ並べ替えた。歴史行・科学結果・生成順記録は不変更、追加solver実行なし。`audit_provenance` と既存回帰テストで確認する。最終の全保存監査・差分／遠隔読戻し・CI結果は結果Draft PR本文を正本とする。

ChatGPT独立レビュー待ち。レビュー前にmainへマージしない。101start本格探索、内部guard変更、別seed/再試行、追加トポロジー、Phase 3は本Issueに含まない。
