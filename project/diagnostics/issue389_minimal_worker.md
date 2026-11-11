# Issue #389：開発専用・最小Worker第1段階

## 境界

`_worker_next.MinimalWorker` は1 arm・1 step・1 seed・Hybridだけ。準備時にPlanを再freezeして定義・現行policy・bands/S2P・全格子・requirements・seed/vector SHAを照合し、モデル・検索格子・evaluatorを準備する。forwardは既存の6設定/部品/接続/全L行列SPD検査、RF evaluator、requirementsを使い、旧Workerと同じHybrid残差を渡す。数値のfloorや候補修復はない。solver `max_evaluations` は維持する。

これは実行制御の試作であり旧Workerを呼ばず、Core・Runnerを新設しない。checkpoint、費用予約・parent台帳・履歴、source再照合、selection/terminal/anytime/dense、復旧、EXPの機能はない。既存development/formal入口は未接続。準備後の入力変更を監視せず、正式運用・安全な費用解放を提供しない。ソルバの失敗/未収束を成功として扱わない。

#388は測定時未マージ、HEAD `928cf4c42a876ab5d71677b8f6fe0db063231365`。そのcheckpoint削減は旧Workerの別変更であり、本経路に取り込んでいない。#385は別HEAD・別process・計測器・cache・負荷であり、solver 2.313秒、job_worker 9.227秒、保存 6.297秒は参考のみ、速度比・直接比較を主張しない。#385の103 forwardにはselection 2とterminal 1を含む。

## 限定回帰

Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、OPENBLAS 1 thread。以下を実行：

- `PYTHONPATH=src .../python -m unittest discover -s tests -p 'test_issue389_minimal_worker.py' -v`：2件PASS。RF-T008 full_lpf、2 vectorで旧保存付き評価と複素S・全応答metrics・worst IL・mandatory_g・残差が厳密一致。3評価Hybridでbest vector/value、nfev、stop reason一致、上限到達。solver中のファイルopen禁止も確認。範囲外/非有限、policy/requirements/Plan不一致、SPD拒否（mock注入）、RF失敗、非有限ILの停止を確認。
- 同様に `test_issue317_fixed_worker.py`：26件PASS、`test_phase2_branch_mna.py`：6件PASS。MNA回帰はこのベンチ候補自体の独立検証ではない。

## 実RFベンチ（1回のみ）

main `dd08698ad48c144ac349387af76cf99311e7b555` 上の未追跡実装で実行。実行時ファイルSHA256：`_worker_next.py` `02f3e88c5e27419161e90afd4b83f6259c3f0b7b5ab57334e5f7784e04ee793a`、`benchmark_minimal_worker.py` `872469bfefa22cb87ef7291c4a8adb50c29b4268ac520059a58201c41ddbb944`。#388は非適用。原本vector SHA `6203467121a4e37baaa51c471aaecb3174f3374f9ab955d6fbf101f7b5ce935f` を実照合。RF-T008 rev3 trial effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、full_lpf、6設定/28独立区間・H2/H3・固定S2P。Plan SHA `8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e`、70点search grid SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`。bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、入力/出力S2P SHA `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945` / `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。

Linux WSL2 6.18.58.1、Python 3.12.15 / NumPy 2.5.4 / SciPy 1.18.1、BLAS/OMP/MKL各1 thread。setup **0.259334 s**、solver **0.270550 s**、total **0.529884 s**。solver nfev=100、nit=1、未収束 `evaluation_budget_exhausted`、best objective 27088.776754855604。計測後の別1 forwardでbestを確認：component policy PASS、L最小固有値 3.9306819299763447e-10 H、worst IL 1.8431100675890377 dB、最大違反 28.0198587146278 dB、strict finite-grid FAIL。この追加forwardはoptimizer nfevと計時に含まない。

```sh
cd /home/user/src/rf-lpf-issue389
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src \
 /home/user/src/reconfigurable-rf-lpf-research/.venv/bin/python scripts/benchmark_minimal_worker.py \
 --config project/diagnostics/issue377/baseline.yaml \
 --starts /home/user/issue377-rf-profile-20261110/inputs/starts-1002.json --arm hybrid --seed 1002
```

上記は実行記録であり追加反復の許可ではない。stdout一時コピー `/tmp/issue389-benchmark-summary.json` SHA256 `01dc71ad939f5fcfd2c163fa029033d97f1ea253199f64bbd1cbc9fa6510e0b3` はGit外・永続保全未確認。独立MNA・dense・連続帯域・Q(f)/SRF/EM・公差・実測・実装可能性はこの候補について未検証。大規模本番・3000評価・100 restart・EXPはnot_run。有限格子結果はRF認定ではない。
