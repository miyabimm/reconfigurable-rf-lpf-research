# Issue #369：開発用100-forward予約と限定計測

## 範囲・実行

`develop` の既定値は旧方式のまま。`--storage-mode window100` は**単一プロセス・開発専用**であり、formal Campaign/G0–G5、`campaign_formal_raw_v1`、過去rawを変更・変換しない。新形式は `development_forward_window_v1` envelope と `development_window_raw_v1` payload、独立した厳格readbackを使用する。Phase 3、正式EXP、Pilot/Main/Extensionの実行許可ではない。

```sh
uv run --frozen python scripts/run_rf_search.py develop \
  --config <schema2-plan.yaml> --starts <starts.json> \
  --storage-mode window100 --output <既存の永続親ディレクトリ内の未存在パス>
```

出力先はcheckoutとGit管理ディレクトリの外、system temp・`/tmp`・`/dev/shm` の外を要求する。実際の永続性・バックアップは利用者が管理する。既存ディレクトリ／rawは拒否し、自動retry/resumeはしない。旧 `legacy` のsystem tmp契約は変わらない。

## 記録と安全側の費用

JobSpecにはPlan・定義・RF/bands/外部S2P・格子・source/environment・seed・完全初期vector/SHA・solver/予算・modeを凍結。Job開始・step切替・100 forward到達・意味ある状態境界・終了で実入力とsourceを再照合する。評価前に、最大100回の**RF response評価**と残予算に応じた末尾枠をatomic保存・fsync・byte/SHA読戻しする。各forwardの完全vector合法性・全L SPD・全格子評価・requirements・費用上限は維持し、通常forwardで保存・入力再読込はしない。固定S2Pの評価用配列はstep開始時に構築する。

checkpointの `confirmed` は保存確定済みのforward/requested/completed、`uncertain_upper` と `window` はその後の実行可能枠の上限であり、optimizer iteration数ではない。枠内の未保存結果はcrashで失われ得る。異常時に状態保存できても上限は解放しない。保存・readback・入力照合失敗時も停止し、親はJob cap全体をunknown予約に残す。前回確定以降の実使用を0とはみなさない。元#361のunknownやrawは触らない。

検索中は軽量assessment・物理検査要約・各完全vectorとSHAを保存し、全複素波形は保存しない。stepごとの `best_observed_by_stage` は観測上の最良で、solver採用解・selection・terminal・独立検証済み候補とは別。selection/terminal/anytimeおよび指定独立spotに必要なresponseは保持する。これは過去の科学的選抜ルールや独立検証の範囲を変えるものではない。連続周波数、全帯域MNA、EM、SRF、Q(f)、公差、実測は未保証。

`summary.json` の `io` は親raw・worker raw・summaryについての**論理atomic JSON payload書込みと直後の読戻しの回数・bytes**。それ以外の入力読込・metadata・OS内部syscall、未読戻しunknown workerの全量は含まず、`complete_worker_accounting` で明示する。各atomic更新はファイルfsync・replace・ディレクトリfsync後に実bytesを読戻す。

## Mock比較（実RF 0回）

2026-11-08、Linux WSL2 x86_64 / ext4 `/tmp`、Python 3.12.15、NumPy 2.5.4、BLAS/OMP/MKL各1 thread。比較は **RF-F003 fixture・6設定28区間×56 search samples**、同一完全vector、同一固定step・selection・terminal・fixture solver。RF responseもrequirementsも固定mockであり、性能やRF適合を意味しない。system tmp出力の場所制限だけをテスト時にpatchし、原本保存経路の永続性は計測していない。

測定時HEAD `e84ae4826ae4af4a9ae01a3daf3eb32406605bdf`、source identity SHA `c65eded33d87b2792941210bbdd529111bd0146aa84c6f951e696591a66c0888`、source dirty patch SHA `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`（空diff）。測定後に完成Jobの選抜漏れを拒否するreadback検査を追加しており、その差分の時間影響は未測定。数値はそれぞれ1回の実測で、mock計測器自体の影響を含む。

| search mock forwards | 方式 | wall s | CPU s | contract | source identity | snapshot | atomic回数 | payload bytes |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 5 | legacy | 2.952 | 1.889 | 8 | 10 | 48 | 30 | 2,919,896 |
| 5 | window100 | 1.865 | 1.037 | 15 | 17 | 14 | 18 | 2,327,394 |
| 100 | legacy | 159.902 | 136.812 | 103 | 105 | 523 | 220 | 81,626,005 |
| 100 | window100 | 2.854 | 2.061 | 16 | 18 | 15 | 19 | 3,890,538 |

開始前凍結、親とsummaryを含むJob全体の計測。各行にselection/terminalのmock 2 forwardを含む。5件では両方式ともrequested/completed=476、100件では5796、選抜vector SHA・terminal completed・solver not_convergedは一致。独立spotはこの計測では未実施。測定時の少数forwardでは境界の再照合により新方式のcontract回数がむしろ多い。

別の**実requirements・mock RF**比較は上記とは異なる実装途中のsource identity SHA `58ce3347a215e032b1c9ba6bbbd4af0696d5cd986f9c326dc9fb1c54697754ed` で行った。100件旧方式は240秒timeout、保存済み70 mock forwardの時点で中断した。100件完走やCPU時間を推定しない。同条件の新方式は100 search + selection/terminal 2 mock forwardを3.738秒wall、2.773秒CPU、atomic 19回・4,623,500 bytesで完走したが、旧方式との完走比較ではない。この途中版のdirty source差分は保存しておらず、精密再生可能とは主張しない。いずれも実RF呼出し0。別途、固定evaluatorのI/O不在テストではRF-T008・1 forward・56 samplesのみ実計算した。

再現用（**mockのみ**、旧100件は数分かかり得る。強制終了時はテスト用一時ディレクトリが残り得る）：

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --frozen python scripts/benchmark_issue369_mock.py --forwards 5 100
```

#368はRF-T008・70 samples・実RF 5 forward・異なる計測器／Job／ファイルサイズであり、この表と直接比較できない。#361の約18.9秒/forwardの原因もここでは確定しない。
