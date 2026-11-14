# 非EXP PilotとMinimalWorkerの性能計測

**対象：** 未収束Pilot、測定契約・inclusiveタイマー、#401の実測・限界（正式EXPではない）。旧研究条件の数値・仮説を現行RF-F003適合と混同しない。
**出典：** [旧methods原文](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/d536a3f1a1b79b8e9be3db4752f1a8b05fa60e65/project/methods.md) / [旧results原文](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/d536a3f1a1b79b8e9be3db4752f1a8b05fa60e65/project/results.md)（PR #411以前のmain固定版）。内容は既存研究の移設であり、新規RF/MNA実行ではない。

## 開発Pilotの未収束と性能計測の教訓（RF-T008 schema2、Issue #372/#375/#389/#391/#393）

**条件と出典：** 非EXP・Phase 2の開発専用診断。RF-T008 rev3 **trial opt-in**、実効SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、`full_lpf`、固定入力/出力S2P・全6設定/28不連続区間。#372/#375の同じ4L・2複合Cv入力の初期seedと、#389/#391/#393の最小Worker比較は**別の測定目的とコードHEAD**。正式RF-F003、旧RF-T008実効SHA `7de08611...`、10月の密格子Paretoの証拠とは混同しない。[代表結果・履歴固定リンク](../results.md#開発pilotの未収束と限定性能診断2026-11)を参照。

- **予算増加・solver収束・strict RF適合は独立。** #372は2 seedとも3,000評価で予算切れ、#375ではseed1002を6,500まで延長しても予算切れ／RF不適合、seed1001は6,006評価でsolver収束したがRF不適合。局所反復の増量は必須減衰30dBもILも保証しない。科学順位のbest-observed vectorとsolver terminalも別に判定する。
- **目的値の単一指標化は危険。** #375 seed1002は84点格子で最大違反28.516→0.710dB、合計違反388.449→0.957dBへ低下しても、worst ILは途中の0.988dB（1,000評価）から9.279dB（6,500評価）へ悪化。各forward時点の値であり過去bestではない。70点search、84点anytime、476点terminalでは格子と選抜対象を明示し、失敗を低ILのParetoに昇格しない。
- **データ完全性の停止を科学的不適合にすり替えない。** #372の初回診断はlegacy summaryにない`io`キーを参照する集計コードの`KeyError`で停止しただけで、RF計算やwindow100が失敗したという証拠ではない。後続の固定vector実RF/IO readback照合は当時成功したが、全最適化と全帯域保証は別。window100の予約／確定／unknown、readbackと終端状態は分ける。
- **性能のボトルネックは計測契約に依存する。** #391の100-forward測定ではrequirements `0.105035s`、RF `0.080692s`、physical `0.050532s`（1回の詳細計時）。包含区間の`evaluate/residual`と二重加算しない。固定grid fingerprintや詳細出力の事前計算は**未実装の高速化候補**であり、候補依存の全6設定/28区間、H2/H3、SPD、NaN/STOP、S2P、残差の科学的契約を省略しない。
- **同等性と速度優位を分ける。** #389の限定最小Worker回帰、#393の旧詳細/新prepared各100-forwardのvector・RF・solver一致はその条件での数値同等性。#393のwall時間差は旧→新の単一順序で測定負荷・cacheを固定しておらず、再現した速度比や現行Worker全体の加速率ではない。plain/timed/profileで計測器の負荷が変わる（#391のcProfile solverはplain中央値より約35%長い）。比較には同じ入力・source SHA・seed・solver・grid/参照面での複数回、順序入替、無計時plain基準と分布の評価が必要。

以上は当時の診断から再利用する**判断基準**であり、新しいPilot、RF/EXP、ベンチマーク、最適化を今回実行・承認したものではない。旧raw・一回限りの診断コードを削除しても、現役の`MinimalWorker`・科学的回帰、後続#394でも使用した共通`issue391_benchmark.py`は残す。

## MinimalWorker性能診断の運用（#401/#408）

開発専用の[単一ベンチ](../../scripts/benchmark_minimal_worker.py)は同一Plan・grid・初期vector・source・環境で `plain`（無計時）、`timed`（L1/L2）、`deep`（L3）を区別する。`worker.solve()`の壁時計には前後の物理検査が含まれ、Hybrid単独ではない。後段のbest_x観察は別時間・追加1 forwardとして記録する。タイマー領域はinclusiveで、特に RF ⊃ port ⊃ node ⊃ matrices を加算しない。計器は実solver callbackを包み、失敗を再送出する。

高速化は一仮説ずつ科学回帰後に旧新plainを別process・warmup除外・交互順（例：旧新新旧、各10回以上）で比較する。source/条件/環境と全run・未収束・外れ値を記録し、揺れたら除外せず再測定する。deep値や合成noopの校正を実RFの速度比としない。6設定・28区間、S2P、SPD、受動性・電力保存、独立MNAを既存検証で確認し、ノイズ未満の変更は退役する。[#401原記録と報告](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/26427c9ce08fe166d5dec31640f417c8dfe2ec79/project/diagnostics)、[結果と限界](../results.md#minimalworker性能診断issue-401)。正式EXP・RF合格の代用ではない。

現役の数値正本は[RF registry](../../rf/constraints/registry.json)、結果・訂正・保全境界は[results](../results.md)。この統合による新規RF計算・EXP・Phase移行はありません。

## 開発Pilotの未収束と限定性能診断（2026-11）

**適用条件：** RF-T008 rev3 **trial**（schema2実効SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`）、`full_lpf`、6設定・28不連続区間、固定外部S2P。以下は**非EXPの開発診断**であり、10月の旧SHA `7de08611...`のPareto、正式RF-F003、正式EXP実行に追加して数えない。#372/#375は探索を伴う有限Pilot、#389/#391/#393はWorker性能・同等性の限定測定。

| 診断 | 実行済み観測 | 結果／厳密な限界 |
|---|---|---|
| **#372** | 最初の固定vector診断は集計`KeyError: 'io'`で停止（旧方式630 samplesのみ。window100未実行）。修正版は20固定callback、search等1,960 samplesで全S/requirements/Hybrid一致。別のPilotはseed1001/1002とも各**3,000 nfev**で予算切れ。合計421,792 samples、raw readback整合 | terminal17点/区間：1001 IL **8.404197**、H2/H3 **22.459800/18.576963**dB；1002 IL **7.649546**、**21.873509/19.555110**dB。ともに未収束・strict FAIL。window100の検証成功はPilot RF適合でない |
| **#375 seed1002** | 6,500 nfev、2 local run、予算切れ（exit4）。84点current-pointで最大違反 **28.515552→0.710063**dB、和 **388.448630→0.957136**dB | 17点terminal worst IL **9.279059**dB、最小H2/H3 **29.983915/29.289937**dB、strict FAIL。違反減少の過程でILは増加 |
| **#375 seed1001** | 6,006 nfev、2 local runのsolver収束（exit0）、6,500閾値は**未実施**。#372と共通の1,000/2,000/3,000現在点を同84点格子で再現 | 17点terminal IL **8.587453**dB、最小H2/H3 **22.494641/18.646104**dB、strict FAIL。solver success≠RF pass |
| **#389** | 最小Worker旧経路との限定数値パリティと100-forward実RFベンチ1回。setup/solver **0.259334/0.270550s**、nfev100で予算切れ | bestの別forward IL **1.843110**dB・最大違反**28.019859**dB、strict FAIL。修正後の実RF再ベンチ、正式保存・Campaign、独立MNAは未実施 |
| **#391** | 同一seedの100-forward `plain`3回でsolver wall中央値 **0.257408s**（範囲0.256984–0.270284）。`timed`1回0.251084s、`cProfile`1回0.346371s | 1回の詳細内訳ではrequirements 0.105035s > RF 0.080692s > physical 0.050532s。instrumentationと負荷未制御、実装改善A/B**未実施**。全実測は同一solver経路 |
| **#393** | 旧詳細評価→新prepared評価の順で各100-forwardを1回ずつ、14,000 samples。全vector・worst IL・mandatory g・solver結果一致（nfev100、未収束） | solver wall旧 **0.384701s**／新 **0.150141s**（total 0.717479/0.392852s）。単一順序・各1回の計時であり、再現性ある高速化率、全Workerの改善やRF passを証明しない |

#375の2 Jobは別枠read-only1,120 samples込みで**879,088 samples**、各raw requested=completed／unknown=0。84点の`current-point`、70点search上のbest-observed、17点terminalは異なる概念で、#372との先頭3,000一致は**新規runの再現**であってresumeではない。各非EXP候補のdense1,001点/区間、独立MNA84点・受動性/電力の独立再計算、連続周波数極値、Q(f)、SRF、EM、公差・実測は**未実施**。関連の正式EXP／Main・Extension・Phase3は今回の結果では開始・成立していない。

**再現性／削減境界：** 実行時のPlan・source・grid・seed/vector・環境・raw SHAの逐語原文は[整理前の固定Git tree](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/504058c52b360e02e37649f509d257dea139ad64/project/diagnostics)で確認できる。#372/#375の全rawは**Git外のローカル原本**を前提とし、その将来可用性は未確認。#391の生計時rawもGit外、#393の生JSONは削減対象。原文・再実行可能性の削減は**科学的結果の変更ではない**。現在の性能計測用`issue391_benchmark.py`は後続[#394比較](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/main/project/diagnostics/issue394_ab)でも利用しており保持するが、当時の実測値を最新の性能と呼ばない。新しいRF評価・Pilot/EXP・本番ベンチはこの整理で実行していない。

## 完全RFResponse維持のC組立て診断（Issue #410）

[報告・原記録・再現方法](../diagnostics/issue410_report.md)。RF-T008 rev3 trial／full_lpf、effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、6設定・28別区間・70点、seed1002、100 nfev/restarts0、測定HEAD `9e9c3f13ef0fe0dca218ef0d7b3bdd1bc9c42415`。

固定C共通D＋可変C設定別Dの分離は、2回の小einsum・抽出・加算費用が勝り、交互plain各10回のsolve中央値旧73.254→新80.615ms、対応差中央値+8.244msで**不採用**。全6設定D先行は旧73.381→新71.281msだが再測定で対応差中央値−2.040→+0.865msと符号が反転し、**効果未確定・本番不採用**。局所node microの改善を全体速度としない。現行も70点を一括einsumで処理しており、単純な70→6 Pythonループ削減ではない。

同じ100候補を再評価するとS全4要素最大差1.870e−14、IL/APL/両RL/全mandatory_g順序込みは許容差内だが**ビット非一致**。有限差分Solverの最終vectorは変わるため、同じstart/seed/nfevでも同じ候補軌道と呼ばない。固定2候補と0可変枝は独立branch-current MNA・受動性／電力を検証。全77runは未収束。100候補全点の独立MNA、連続帯域・EM・SRF・Q(f)・公差・実測は未検証。試作は診断専用で、公開RFResponse・SPD・S2P・異常STOP・保存／Solver契約は本番コードで変更していない。

## 枝Qスタンプ前計算と小行列縮約（Issue #413）

[報告・全run・再現コマンド](../diagnostics/issue413_report.md)。RF-T008 rev3 **trial opt-in** / full_lpf、実効SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、seed1002、25変数・6設定・28別区間・固定S2P・70点、計測HEAD `fd0f420c7c0323f3745f1411bd59399b202f7386`。

#410の固定／可変分離ではなく、トポロジー/Qだけで決まる枝stamp外積をsetupで準備し、候補Cを毎forwardで掛ける3案を比較。**six-matmulを独立レビュー第一候補**、direct-matmulも同等候補とし、**本番未採用**。固定100 vectorの実RF forwardでは、旧新各10子process×2batchの対応差中央値がA −6.910/−8.547ms、B −9.347/−7.868ms、six-einsum-no-opt −7.451/−8.078ms。上位A/Bのplain `worker.solve()`も対応差A −8.605/−8.899ms、B −9.014/−10.719msで改善方向を再観測した。共有hostの外れ値を全保持し、A/Bの微小順位差・汎用加速率は認定しない。小行列ではpath探索・枝係数／incidence再構築の負荷削減が、演算数削減だけより重要になり得る。

固定候補比較は全S／IL/APL／両RL／mandatory_g全42点順序込みでatol1e−9/rtol1e−11内だが**ビット非一致**。代表3 vector×全70点×3案で独立MNA・受動性／電力を検証。正式モデル群・0可変枝・異Q並列・非SPD/非有限・Schur/Y→S/power異常STOPも回帰。Solver 88runは全て100 nfevで**未収束**、旧新で最終vectorが変わるため、Solver比較を固定候補列比較へ読み替えない。正式RF-F003の速度・全候補独立MNA・極端値すべてのSTOP発生位置・連続帯域・EM/SRF/Q(f)/公差/実測は未検証。診断opt-in以外の`src/`変更はなく、本番採用はDraft PR独立レビュー後の別判断。

## six-matmul採用後mainのRF forward内訳（Issue #417）

[詳細報告と再現条件](../diagnostics/issue417_report.md)／[全24runのraw集計](../diagnostics/issue417_forward_timing.json)。PR #416反映後HEAD `523f3ab8d0d89323fd521c9b6738728f8babc54b`、RF-T008 rev3 **trial opt-in**／`full_lpf`／effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、#410から再照合した固定100 vector、6設定・28別区間・70 samples/forward・固定S2P。plain 12子processの中央値49.140ms/100 forward（48.167–51.819）。

同HEADのdeep inclusive中央値ms/100 forward：power_response 12.705、port 21.084/node 12.566（port−nodeのrun別差中央値8.590）、decode 7.186、matrices 6.338、node−matrices 6.228、cascade2回合計5.130、Y→S solve 2.523、encode 0.799。包含区間は合算不可。inclusive関数計時・response digest／mandatory g照合はplain timingより外れ値と負荷の影響が大きく、plainとの差中央値は+5.955ms/100（範囲+1.474～+20.298）。deep値をplain性能と呼ばない。

次候補は**power_responseを第一候補**（最大の独立inclusive領域）、Schur/port側とdecodeを次の調査候補とするが、2/3位は範囲が重なるため未確定。matrices/node残余も近い。全応答・mandatory gのdigestはplain/deepで完全一致し、24 runともforward STOPなし。既存RF Core／branch-current MNA／#415 production-stamp回帰を実行。速度改善実装・Solver測定・正式RF性能一般化・全100vector独立MNAは行っていない。

## MinimalWorker性能診断（Issue #401）

[PR #402](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/402)・[原報告とrawの固定履歴](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/26427c9ce08fe166d5dec31640f417c8dfe2ec79/project/diagnostics)。RF-T008 rev3 **trial** / full_lpf、effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、6設定・28別区間・70 samples/forward、seed1002・100 nfev、Plan `8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e`、grid `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`。計測前HEAD `f5bd7dbb0d5ccc580999633b76116eb7356b80db`、port変更後詳細HEAD `6908e52149de9f59c51c859f291ba6f4cd8de72c` と `124a55c5b1cda68b17a41daeeede7447d70b0437`。単一thread・共有host、外部固定S2Pを含む有限格子。

- 旧new交互plain（warmup各1＋各10、2 batch）で固定source/load事前準備のsolve中央値は旧97.285/105.981、新83.234/86.339 ms。対応差中央値−14.248/−14.863 msだが範囲はそれぞれ−41.030〜+11.622、−33.671〜+32.507 ms。3 vectorの複素S・IL/APL/RL・mandatory g配列digestは旧新完全一致（6 forward・420 samples）、全solver軌道の配列一致ではない。
- Deepの100 forward中央値は変更前→後の再測定で RF 83.817→79.016、port 35.860→38.631、node 25.979→28.241、power 15.388→15.251、decode 7.911→8.153 ms。包含区間は加算不可、非交互のため差を変更の因果効果やplain速度比としない。後初回plain最大239.046ms、再測定deep最大162.408msの外れ値は除外していない。
- C incidence先行準備は旧HEAD `f5bd7dbb0d5ccc580999633b76116eb7356b80db`／候補 `411110f8838d2a4889f64fc4e3393cc5beb919db`、22 run・2,200 forwardで対応差中央値−0.526ms、範囲−22.797〜+13.282ms。ノイズと区別できずrevert。初期26 run 2,600 forward、詳細33 run 3,300、port A/B 44 run 4,400、後詳細66 run 6,600は別実施分であり、各70 samples。全solver runは100 nfev予算切れ・**未収束**。

計器の実RF負荷や汎用速度比は未確定。測定時のsolver一致はRF合格を意味しない。連続帯域、全軌道の独立MNA、EM・SRF・Q(f)・公差・実測・物理実現性は未検証。これは正式EXPや正式RF PASSではない。
