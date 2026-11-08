# Issue #367：中断Pilotに対する小規模タイミング診断

## 範囲と結果

[#367](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/367) の指示とユーザー起動により、最新main `9a3f9caae2d2ade4f2fd050757615fe45046f978` 上で、**新しい独立した開発用診断**として5 forwardを実行。Hybrid solver、探索、Pilotのretry/resume、Main/Extension、正式EXPは実施していない。同じ合法seed1001 vectorを5回使用したが、中断した393点の再生や継続ではない。診断側のrequested/completedは**350/350**、各batch completed、Job状態は意図的にunknownのままで完走・収束ではない。既存の予算検査と各forward前unknown課金・原子保存、forward後保存をそのまま通した。rawを読戻し各回の費用を照合した。

診断では、同一設定の5回に限り、**snapshot生成が最も大きい**。元Pilotの18.9秒/forwardは計測点、rawサイズ、実行状態が異なり、元rawとCPU記録がないので直接分解・原因確定できない。ここでのプロファイラは時間取得とevent記録を追加しており、無計測時の速度ではない。

## 実行同一性

- RF-T008 rev3 trialを `allow_trial=true` で明示opt-in。effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。formalではない。
- #361 PilotのYAMLそのものから凍結したPlan canonical SHA `8e472fd5a223eaef4aab24cc48e9dbcae6796f3930355b7871b62d3c76ab9ac4`、YAML byte SHA `27f5fc515403805a956cd799d638328a81a1fee7c1eb59913e1e30765a75166a`。definition SHA `bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068`、definition file byte SHA `e8ac857c063e0b9d2eb8eaf629c2e4b700a694e9241f3bbc596d99f6374487f6`。seed1001 vector SHA `49f9f53b0220f4e81332fbe94cebe2482e436b1a313aaabbae696a6b015761e5`。Pilot YAMLの既存パスに同一byteの一時コピーを配置してpreflightし、計測後にそのコピーだけ削除した。
- 6設定・28個別区間（pass 14×2、H2/H3各7×3）・70点、grid SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`。物理/role検査PASS、全L行列の最小固有値 `1.56892805649937e-09 H`。外部S2Pを含む既存モデル。dense/独立MNA、受動性・電力の独立照合、実装性検証は未実施。
- bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、入力S2P `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、出力S2P `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。各ファイル、source全71ファイル、Python等の記録は [timings.json](issue367/timings.json) 内metadata参照。
- 計測時source identity SHA `d8098073ffbee52c29365a947076e0757ee735366f3d1b81aaaf529608fc09a4`、tracked dirty patchは空SHA `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。#361実行時HEAD `5609cc84f9f738cc93041f35363b57c3188bc1bc` から計測時HEADへの `src`、`scripts/run_rf_search.py`、`pyproject.toml`、`uv.lock`、`rf` 差分はなし。ただしHEADが異なるためsource identityは#361の `3d9e18e0520ba8739edf1f0ec9b23e3f7b5ab78659ccff5ecec6439261804828` と一致しない。現Job内で現在sourceと凍結sourceの一致を毎回検査した。
- Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、BLAS/OMP/MKL各1 thread。Ryzen 7 PRO 4750G、WSL2 Linux、`/tmp` とcheckoutは同じ `/dev/sdd` ext4。system tempへ保存。共有マシン負荷やcacheの制御なし。子プロセスCPUはprocess CPUとは別計上。

## forward時間（秒）

各行は**forward 1回分の同名呼出し合計**の、5回の中央値 / 最大。process CPUはPythonプロセス分でGit子プロセスを含まない。`contract_base` は `FixedStageEvaluation._contract()` 本体、`source_identity` はその後の `FixedJobEvaluation._contract()` 内source照合であり独立。`snapshot` と `atomic` は別呼出しであり加算可能。`atomic` の子区間は親に内包され、合計に重ねて加算しない。

| 区間 | 呼出し数/forward | wall 中央値 / 最大 | process CPU 中央値 / 最大 |
|---|---:|---:|---:|
| evaluate全体 | 1 | 1.503929 / 1.662943 | 1.356023 / 1.506558 |
| contract_base：preflight/RF/S2P/grid照合 | 1 | 0.130827 / 0.135606 | 0.120591 / 0.125177 |
| source_identity：src SHA + git diff | 1 | 0.012344 / 0.012397 | 0.005057 / 0.005135 |
| validate_values | 1 | 0.011516 / 0.013202 | 0.010629 / 0.012153 |
| RF evaluator.evaluate | 1 | 0.001192 / 0.001748 | 0.001101 / 0.001616 |
| evaluate_requirements | 1 | 0.001307 / 0.002108 | 0.001208 / 0.001949 |
| snapshot（raw_numbers含む） | 5 | 1.148108 / 1.312332 | 1.059486 / 1.211270 |
| atomic全体（各回JSON全量・書込・fsync・replace） | 2 | 0.135302 / 0.147124 | 0.102350 / 0.110268 |
| └ canonical JSON直列化 | 2 | 0.103032 / 0.112782 | 0.095093 / 0.104067 |
| └ fileとdirectoryのfsync | 4 | 0.027058 / 0.029250 | 0.001552 / 0.001707 |
| └ atomic replace | 2 | 0.000369 / 0.000419 | 0.000341 / 0.000387 |

未分類差分は各forward wall 0.0550〜0.1245秒、CPU 0.0507〜0.1103秒で、モデルevaluator準備、vector処理、budget確認、応答のlist化、呼出し・計測等を含む。行別中央値を足した値は全体中央値に必ずしも一致しない。source_identityで終了したGit子プロセスCPUは1回あたり中央値0.006317秒、最大0.006479秒。snapshot 25回を個別に見た中央値/最大はwall 0.229841/0.282517秒、CPU 0.212024/0.260785秒。atomic 10回の個別中央値/最大はwall 0.064021/0.087943秒、CPU 0.047386/0.066163秒。rawサイズは1,112,079 → 1,382,067 bytes。

## 別枠・合成I/O

実RF呼出しなし。診断で得た1行の繰返しから作った**合成JSON**であり、失われた原rawの復元でも393評価の再現でもない。各サイズ3回、同じ一時ファイルに原子的に保存。次は中央値 / 最大。直列化・fsyncはatomic内包。

| データ | bytes | atomic wall | atomic CPU | 直列化 wall | fsync wall（file + directory合計/保存） |
|---|---:|---:|---:|---:|---:|
| 小 | 67,555 | 0.010476 / 0.011141 | 0.004185 / 0.004947 | 0.003162 / 0.003687 | 0.006629 / 0.007197 |
| 大 | 27,538,427 | 1.601345 / 1.758202 | 1.364035 / 1.514136 | 1.418080 / 1.588903 | 0.116522 / 0.125036 |

fsyncの個別6回のwall中央値/最大は、小 `0.003175/0.004437` 秒、大 `0.019316/0.122740` 秒。大きいファイルでは直列化CPUが顕著だが、繰返し内容・cache・時点の異なる合成実測であり、元rawや保存回数増大時の実時間・全体コストには外挿しない。

## 提案順位・限界

1. **最優先の検討対象：snapshot/raw_numbersの重複処理。** 5回/forwardで現実測の最大部分。データの完全性・実際のunknown-before-forwardと完了後の両保存、課金および失敗時の意味を変えない実装案を別Issue/レビューで検討。単にsnapshotや保存を省くことは提案しない。
2. **次：全量JSON変換と原子書込みのサイズ依存。** 再利用や表現/保存設計を別途評価するが、監査可能な全応答、crash時の復旧・順序・fsync・readbackを維持する契約と回帰検査を先に定義。測定だけでdurabilityの緩和や並列化を承認しない。
3. preflight/source照合は測定上より小さく、RF本体とrequirementsはさらに小さい。科学条件、SPD、固定S2P、source/G1検査を省略しない。後続最適化・追加実行は別判断。
4. 長時間dev実行では、一時領域だけに原本を置かず、事前に永続領域・容量・アクセス権・保全責任・停止時手順を決め、初期/途中/終了時のraw・親記録・Plan・入力・ログを原子的に保持しbyte SHA・readback・遠隔照合する運用案を提案。元データを上書きせず、保存先の権限/容量/費用と整合性は別途承認・検証する。

[#361中断レビュー](issue361_pilot_review.md) の原本 `/tmp/issue361-dev-7RxpB4OQ/` は今回の存在確認でも見当たらない。既知SHAとの照合・原raw独立再集計は未実施。unknown費用や予約は解放していない。別保存先の網羅探索や完全履歴監査は行っていない。連続帯域、Q(f)、SRF、EM、公差、実測、物理実装性と大域最適性は未検証。

## ソフトウェア確認と実行範囲の注意

診断後、`test_issue315_fixed_stage.py` の9件はPASS。ただしこのテストには**実RFを使う小格子forwardが別途含まれる**。診断の5回/350 samplesには含まれず、テスト内の正確なforward数・requested/completedは計測していない。テスト実行時にこの追加RFを見落としたため、#367の「最大5回」を診断プロセス以外も含む全RF実行の上限として読む場合、遵守を主張できない。Pilot・同seedのretryではなく、さらにRFテストを繰り返していない。`test_phase2_current_status_review.py` は新規資料のgit未stage時、tracked fileベースのリンク検査で1件FAILし、資料stage後に再確認して3件PASSした。

## 計測資料・保全

[実際に使用したコードのbyte copy](issue367/executed-measurement.py.txt) は証拠用テキストであり再実行指示ではない。固定の一時パスを含み、再実行すると既存metadataを上書きし得るため**実行しない**。SHA `ecd6551aab13aefbec1a3acde30fe5006679e8e7122f049b5eebced2f4672a64`。[全イベント/metadata](issue367/timings.json) SHA `146dea92e2553e5b1b4f44aa1543e7a170e363451b8e70a26ae52d7024dfba85`。

診断の実raw SHA `2258477c8199e1ded8a11bc53183d2727beb5040f1e9535a78a919f8e9f6f65e` と合成JSONは `/tmp/issue367-timing-1794134932-9180/` に残存。これは永続保存保証ではなくPRにはrawを含まない。元Pilot rawの代替ではない。元checkoutの未追跡ファイルは未変更。worktree `/home/user/src/rf-lpf-issue367` はDraft PR用に保持。形式的G0〜G5、正式科学実験ではない。
