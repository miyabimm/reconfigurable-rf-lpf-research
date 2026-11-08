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

checkpointの `confirmed` は保存確定済みのforward/requested/completed、`uncertain_upper` と `window` はその後の実行可能枠の上限であり、optimizer iteration数ではない。枠内の未保存結果はcrashで失われ得る。異常時は最後に確定したpayloadをそのまま保持し、可能ならtermination理由を追記する。未確定のメモリ内結果を確定payloadへ入れず、上限を解放しない。保存・readback・入力照合失敗時も停止し、親はJob cap全体をunknown予約に残す。前回確定以降の実使用を0とはみなさない。元#361のunknownやrawは触らない。

検索中は軽量assessment・物理検査要約・各完全vectorとSHAを保存し、全複素波形は保存しない。Hybridでは各forwardの同じassessmentから、solverと同じ平方残差の `sum` または `max` 目的値scalarと検算用成分を保存する（非有限・無効な場合は `invalid`）。全 `mandatory_g` 配列は保存しないため、readbackの成分整合検査は元配列からの独立再計算ではない。`best_observed_by_stage` は厳密可行性・違反・ILの科学選抜順位、`best_hybrid_observed_by_stage` はHybrid目的値最小（同値は先着）で、いずれもsolver採用解・selection・terminal・独立検証済み候補とは別。selection/terminal/anytimeおよび指定独立spotに必要なresponseは保持する。これは過去の科学的選抜ルールや独立検証の範囲を変えるものではない。連続周波数、全帯域MNA、EM、SRF、Q(f)、公差、実測は未保証。

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

## PR #370レビュー後の修正・限定実RF比較

2026-11-08のblocking指摘に対し、Hybridの目的値を同じassessmentからsolverと同じ平方残差・集約順序で各観測へ保存し、科学順位のbestとは別の `best_hybrid_observed_by_stage` とreadbackの整合検査を追加した。異常終了時は**最後に確定したpayload**と予約上限を維持しtermination理由のみ追記する。3成功後の4回目失敗、checkpoint 100件、sum/max、同じ違反最大・違反和でも目的値が異なる例、改ざん、親unknownをmockで確認した。

別枠の実RF技術比較は事前上限 **2 forward × 70 samples＝140 requested/completed**。旧・新それぞれ同じベクトルで1回ずつ、solverを呼ばず、評価結果の複素S・IL/APL/入出力RLの全配列とassessmentは完全一致した。`max_violation_db=25.224754407591835`、`sum_violation_db=323.4272113345574`、`worst_il_db=24.999944738674145`、Hybrid sum目的値 `22511.121105913582`、strict feasible=false。新方式の保存用scalarと既存solverの残差集約値も一致。これは科学的選抜・収束やRF性能の承認ではない。

- RF-T008 trial effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、6設定28区間・格子SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`。
- seed1001の凍結vector SHA `49f9f53b0220f4e81332fbe94cebe2482e436b1a313aaabbae696a6b015761e5`、definition SHA `bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068`、definition byte SHA `e8ac857c063e0b9d2eb8eaf629c2e4b700a694e9241f3bbc596d99f6374487f6`。#361のunknown Jobの再試行・継続ではない。
- source HEAD `0321a983afba63fcdc7c2ed69cee6aa6328b34d7`、source identity SHA `4b18414b262e3de6bfa76e956ffc217c81ce56539836dc332690487c3cd3c86a`。Plan SHA `0abfb03063e41d7cc428a054663d1d0f7a1aa34801c45b7a9ac796e0055f4f2f` はdefinition pathをGit追跡済み `project/diagnostics/issue361/definition.json` に置き換えたため元Pilot Plan SHAとは異なる。実行出力の `definition_sha256=8743ebc4285c4b71996df8e5a338d37dc07ef01d8c4c1eadb6e2c806c1e762eb` はdefinition **参照オブジェクト**のSHAであり、上記のdefinition内容SHAではない。
- bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、入力S2P `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、出力S2P `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。response SHA `81b07e412e4bac01a11db2e0fc9adb26582a60923fe78a9e3db240999169b7c6`、assessment SHA `f8f112b836479d17f2d35bba9cf445681edeb0c091fc50d11332b0085de803ae`。
- 永続原本を伴う開発Jobではなく、保存処理をtest doubleに置換した一時的な数値比較で、rawは保存していない。保存耐久性や実運用速度は検証対象外。独立MNA・受動性/電力の独立検証はnot_run。

手動テスト実行時、`-k hybrid` が意図せず既存のRF-F003回帰 `test_hybrid_slp_adapters_invalid_endpoint_and_top_k` にも一致し、上記の限定比較とは別に**9 forward・728 samples**の実RFが実行された（fixture solver、科学EXPではない）。今後の限定確認では個別テスト名を指定する。CIの既存回帰によるRF呼出し数は別途未集計。
