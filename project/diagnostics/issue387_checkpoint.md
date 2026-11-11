# Issue #387：window100状態境界checkpoint

## 範囲と正本

対象はdevelopment-only `window100`、100-forward周期・科学評価・formal Campaign・既存rawは不変。実装基準main/実行HEAD `dd08698ad48c144ac349387af76cf99311e7b555`、実行時 `src` は本PR差分を含むdirty tree。非RFベンチのsource SHA `bb560a2dc486ec357528623bc08205722b0f1d36558f5e27abf72ab1d7fc054f`（HEADとdirty patchを含むsource identity）。RF-F003のfixtureを読み込み、RF応答はmockであり科学結果ではない。

#385の計測は別条件：RF-T008 rev3 **trial**、effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、source SHA `33f822e15b4a54900f54d0576b2c765e42c88920c61c6866aafacdcd71004587`。active formal RF-F003と混同しない。

## 保存経路と安全性

| 契機 | 保存直前 → 永続化される状態 → 続き | 判断 |
|---|---|---|
| 最初のactivate | 未開始 → 初回最悪窓予約 → forward | 維持 |
| 窓末尾 | 完了窓 → confirmedと次窓予約 → 次forward | 維持。残費用により末尾短縮 |
| 旧allocationでfinish | active → 確定とallocation解放 → inactive | 維持 |
| inactive後のactivate | inactiveで確定済 → 同じinactiveの再保存 → 新窓予約保存 | **再保存のみ削除**。新予約・入力照合は維持 |
| activeからactivate | 旧active → 旧窓確定 → 新grid・新窓予約 | 維持。anytime等の途中切替は異なる境界 |
| Worker step開始・結果確定 | input／solver結果・候補 → snapshot → 次処理 | 維持 |
| selection・terminal・anytime・独立spot | 候補や評価／検証の意味ある状態 → snapshot → 次処理 | 維持 |
| 最終／異常 | 最終状態を保存、または失敗時は直前予約のunknownを保全 | 維持。保存失敗後retryなし |

旧inactive中間保存ではforwardもallocationも変化しない。削除後、予約保存前にクラッシュしてもfinish等で確定した原本が残る。新予約前に新たなforwardはなく、新予約atomic fsync/byte・SHA readbackが成功して初めて次forward可能。予約書込み時のクラッシュやreadback不一致では親はJob全capをunknownとして保持、解放しない。新recordの`previous_confirmed`/`previous_uncertain_upper`は直前の実durable recordを指し、checkpoint番号は連番。source/Plan/RF照合は新予約保存内で実施。active切替・候補確定保存は一括削除しない。通常forwardにI/Oを追加していない。

## #385の20回：実測とmockを分離

#385は`window_checkpoint_save` 20回、包含6.297秒、内側`source_contract` 20回・2.199秒を実測したが、元JSONに個別理由はなく内訳は**未確認**。以下は同じ100 search＋2 selection＋1 terminal・anytimeなしの形を再現した**非RF fixture**であり、#385の内訳実測ではない。fixtureはF003・56点searchで、solver結果や評価も異なる。

| 発火と状態遷移 | 旧mock | 新mock | 続く処理 |
|---|---:|---:|---|
| 初回予約（confirmed 0→0、upper 100） | 1 | 1 | step開始 |
| activeのWorker明示checkpoint（step入力・solver結果） | 2 | 2 | solver／finish |
| 100 search窓末尾（confirmed 0→100、残枠なし） | 1 | 1 | solver結果確定 |
| 旧allocation finish（search、selection×2、terminal） | 4 | 4 | inactive |
| inactive→inactiveの再保存（selection×2、terminal直前） | 3 | **0** | 新allocation |
| 新allocation予約（selection×2、terminal） | 3 | 3 | 対応forward |
| 1-forward配分の窓末尾（selection×2、terminal） | 3 | 3 | 評価証拠確定 |
| inactiveのWorker明示checkpoint（選抜順位×2、Job最終） | 3 | 3 | 次候補／終了 |
| **合計** | **20** | **17** | |

best・solver・selection・terminalを含む最終payload、confirmed/uncertain upperと親台帳が旧新一致。mockは103 forwards・requested=completed 5,880 samples、親reserved=0、released=6,120、worker not_converged。これは#385の7,644 samplesやRF結果と比較しない。

## 非RF Worker固定負荷の比較

`scripts/benchmark_issue387_mock.py` は同一現行コード・sourceで、削除行のみを旧挙動として追加する。親Runner→Worker→原子的保存→親readback、合成RF応答、実requirements評価、同じ候補・予算。出力先の制限はfixture内でのみpatchしdisposable temporary directoryを使用。旧新各1回、常に旧→新の順序、同一process、共有負荷・cache非制御。ログ用spy・時計のオーバーヘッドは未測定。通常実行へのイベントI/O追加なし。

| search forward | 旧→新 保存/read | 書込bytes 旧→新 | 親Worker wall秒 旧→新 |
|---:|---:|---:|---:|
| 0 | 14→12 | 2,698,832→2,336,741 | 1.577→1.304 |
| 1 | 21→18 | 5,305,420→4,530,179 | 2.758→2.365 |
| 99 | 21→18 | 5,305,728→4,530,437 | 2.978→2.623 |
| 100 | 21→18 | 5,305,740→4,530,447 | 2.857→2.590 |
| 101 | 22→19 | 5,532,780→4,757,487 | 2.660→3.091 |
| #385形状100 | 20→17 | 5,418,946→4,604,287 | 2.791→2.450 |
| 2 step/grid、各1 search | 26→22 | 7,267,645→6,131,280 | 3.280→2.873 |

前5行はanytimeを含む。1 search直後にanytimeへ切替えてsearch窓を再予約するため、次の100件境界はsearch 101件時であり、単一窓99/100/101と別である。旧新は全ケースで最終payload全体、候補・best・solver・selection・terminal・anytime、親台帳とconfirmed/uncertain上限が一致。`--two-steps`は粗/細grid切替も比較した。予算停止は別テストで旧新一致。短い末尾窓と0/99/100/101、source変更、保存失敗、中断は既存Journal/Worker回帰でも検証。

#385形状の`_save`包含wallは2.077→1.760秒、snapshot包含wall 0.571→0.519秒、source contract計時0.825→0.715秒（constructor呼出しも含む）。snapshotとsourceはsave内を主に含み、領域は重複するため足し算不可。atomic fsync/readbackの自己時間は未分離。固定順序・spy・キャッシュ・ファイルサイズ・共有負荷により実Jobの速度改善率は主張できない。表の101ケースは新のwallが遅い例であり、速度改善は保証されない。#385の6.297秒と2.199秒も包含関係で加算不可。

## 再現・検証

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --frozen python scripts/benchmark_issue387_mock.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --frozen python scripts/benchmark_issue387_mock.py --shape385
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --frozen python scripts/benchmark_issue387_mock.py --two-steps --forwards 1
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --frozen python -m unittest discover -s tests -p 'test_issue387_boundaries.py' -v
uv run --frozen python -m unittest discover -s tests -p 'test_issue317_fixed_worker.py' -v
uv run --frozen python -m unittest discover -s tests -p 'test_issue319_parent_runner.py' -v
uv run --frozen python -m unittest discover -s tests -p 'test_issue369_forward_window.py' -v
uv run --frozen python -m unittest discover -s tests -p 'test_issue383_integration.py' -v
uv run --frozen python -m unittest discover -s tests -p 'test_phase2_branch_mna.py' -v
```

各benchmark比較PASS。順にテスト2件（旧新×5異常位置と予算停止を含む）、27、18、9、6、6件PASS。旧finish保存失敗、新source変更、新予約atomic失敗、readback不一致、新forward中断を旧新双方で注入し、親capを全保持、不要な追加forwardなし・再試行なしを確認。readback不一致はreplace後の新予約原本が存在し得るが親は安全側の全capを保持。既存回帰には小規模実RF fixtureと指定独立spot、MNAが含まれるが、全RF性能や連続周波数の認定ではない。

新規3,000評価、100 restart、正式EXP、本番探索、追加実RF Job、dense/EM/実測はnot_run。旧raw・研究証拠の変更なし。finite grid、Q(f)/SRF/EM・公差・測定と実装可能性は未検証。
