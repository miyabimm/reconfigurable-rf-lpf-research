# RF-LPFの保存結果と検証証拠

**本書は研究ナレッジベースの代表結果・失敗要因・検証限界の正本です。** [Issue #397](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/397)により、正式記録に不要な旧raw・checkpoint・補助数値は知見抽出後に削減します。古い結果の参照先が現行treeからGit固定履歴へ変わっても、当時の検証状態は変わりません。過去全試行の完全再現は保証しません。

数値原本は[実験索引](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/data/experiment_index.csv)と各EXPのmanifest・候補・検証記録です。有限格子のbest-foundを大域最適性、連続帯域保証、実装性能の保証とは扱いません。正式／試験／旧条件、`matching_only`／`full_lpf`、bare LPF／外部ポートを混ぜず、実効制約SHA・格子・検証深度が同じ候補だけを比較します。

| RF条件 | 保存証拠への入口 | 注意 |
|---|---|---|
| **RF-F003（正式）** | [EXP-047](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/main/experiments/chatgpt_topology_search/runs/EXP-047) | 正式2可変C、2026-10-17固定パレート4件は当時の記録 |
| **RF-T005（試験）** | [EXP-042](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/main/experiments/chatgpt_topology_search/runs/EXP-042)、同階層EXP-043/045 | 最大3可変C、固定パレート6件 |
| **RF-T006/T007（試験）** | [EXP-048](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/main/experiments/chatgpt_topology_search/runs/EXP-048)、同階層EXP-049/055 | 追加阻止帯・固定寄生モデルを区別 |
| **RF-T008 v3（試験）** | [EXP-058](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/main/experiments/chatgpt_topology_search/runs/EXP-058)、同階層EXP-062〜068 | IC固定C＋最大2可変C、各EXPの収束・独立MNAを個別確認 |

2026-10-17のRF-T005／旧RF-F003派生Paretoと24候補カタログは[以下の固定比較](#正式rf-f003旧版とrf-t005t007試験の固定比較2026-10)へ知見を統合し、旧派生原文は[マージ前の固定Git履歴](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/246444b93fb6e6b082af6ece3c5bfc7bcaff05c9/data)からのみ参照できます。最低必須30dB、公称35dB、IL目標0.30dBは別判定。Q(f)・SRF・EM・公差・実測は未保証。[ロードマップ](roadmap.md)／[手法・解釈](methods.md)。

## 正式RF-F003旧版とRF-T005〜T007試験の固定比較（2026-10）

**実行時条件を固定した歴史的な局所best-found。** 2026-10-17〜20の試験群はいずれも`full_lpf`、固定外部入出力S2P、50Ω源・60−j40Ω負荷、全6設定・28個別UL/DL/H2/H3区間、有限格子の必須H2/H3≥30dBを基礎とする。ただしRF-T006の**追加3〜6GHz・20dB**、RF-T007の**接地DTC 0.5pF/Q40固定寄生**、RF-T005の**可変C最大3枝**は同条件ではない。

**旧実効SHAと現在のschema2実効SHAは別物：** RF-F003 `f85710200ccda5b72ab32f943540fbfd7a8abb3137c5f4e6e5ba7a6d7b3da2ba`（現行`e12c42b11d12db7f20983c48cfa441ea96e362e533450d5862aa8a271c82af86`）、RF-T005 `59a451775ab4914cf9f0e51785ebfb62b36217af7735e7c93e9fe70f2323e67c`（現行`413c1f2979926dd8bc56fe6730603864f6c582e2a72ec3f7bb0ab1ba81a7becd`）、RF-T006 `54e86864b32bb158857750e6c81e41289d2f762fe1f12c52ec851b12a06f5137`（現行`1d22e01d6da243bed24970de90a496e8f2d38b11bd5a5fae78e001398f647e1c`）、RF-T007 `c6f0fc685464964fff2abedf8b99dda0064c99bbe133ec8fecd91c4f60d2b430`（現行`5452690de1c8590f1f7c306f76e41692e1885ac190da3cef050f1d926145c944`）。旧結果を現行RF-F003の新しい検証・最良値へ自動昇格しない。

| 旧条件・元EXP | chip面積 | worst IL [dB] | 数値の意味 |
|---|---:|---:|---|
| RF-F003旧・EXP-047 | 4⅔ / 5⅓ / 6 / 6⅔ | 0.882646928 / 0.843652332 / 0.836867952 / **0.833188234** | 最大2可変C、28区間×1,001点・選抜84点独立MNAの当時の観測非劣4点 |
| RF-T005・EXP-043/045 | 3 / 3⅔ / 4⅓ | 0.944268363 / 0.895180009 / 0.879244690 | 最大3可変Cの観測非劣点、28区間×1,001点 |
| RF-T005・EXP-042 | 4⅔ / 5⅓ / 6 | 0.819564515 / 0.811306586 / **0.805148668** | 面積6点はSLSQP**非収束**ながら28区間×7,001点の保存値で30dB適合、独立MNAは84点のみ |
| RF-T006・EXP-048 | 5⅓ | **2.920705899** | 追加3〜6GHzの20dBを有限格子で達成したが、元EXP-047 IL0.843652332から悪化。46,034点評価、別式MNA114点PASS |
| RF-T006・EXP-049 | 18 | **1.166797417** | Q33 LQW04モデル＋公表0.8nH下限にした代表例。追加阻止最小20.079968dB、IL≤1.1dB未達。別式MNA114点PASS |
| RF-T007・EXP-050 | 3 / 3⅔ / 4⅓ | 0.938309198 / 0.909728967 / 0.891827011 | 接地DTC付属寄生を含む固定履歴の3L観測非劣 |
| RF-T007・EXP-055 | 5⅓ | **0.817365590** | 4Lの配置探索後の保存値、EXP-053同面積0.875794664から改善0.058429074dB。28×1,001格子＋84点9×9独立MNA |

**探索の否定的成果：** 旧RF-F003の面積4/4L/0GJMでは30dB PASS点を当時発見できなかったが不可能性証明ではない。EXP-049でIL1.158264dBとなった面積19の旧試行はLQW04の一つが0.4nHで公表0.8nH下限未満であり、上表の下限考慮例とは別。RF-T007/EXP-055の最小H3は30.004810049dBと閾値近傍で製造余裕の証明ではない。すべての観測非劣群で公称H2/H3≥35dBとIL≤0.30dBは未達。旧RF-F003 4GJM/面積6の**元JSON面積誤記は正しくは6⅔**（元検証原本の値は変更しない）。旧RF-T005の非収束候補も数値適合とsolver収束を混同しない。

**旧W4資料から継承した出典上の注意：** EXP-042の当時のActions ZIP10個・19 member（うち未選別のcf2/both/pcb_cf2各数値＋独立報告の計6 member）は、既存Git選抜点と同一の採用checkpointであると検証されていない。旧資料のZIP SHA/CRC一致はRF独立計算を意味せず、6未選別点は当時の面積–IL非劣更新の根拠にならなかった。EXP-046の容量電力会計訂正とEXP-047のGJM Q-index誤りは**別問題**。EXP-047の誤index計5原本は正式順位から除外し、6検証候補と4 Pareto採録を区別する。EXP-046の実行元dirty・seed/環境欠落、EXP-047元optimizer commit/seed/環境unknownを埋めない。W4の46/131/225ファイル分類は重複する時点固定監査台帳であり、計算結果ではない。RF-T008旧#229の12 startは12/12収束でも厳密30dB適合0、dense1,001点・独立MNAは未実施（[元記録](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/246444b93fb6e6b082af6ece3c5bfc7bcaff05c9/data/repository_reviews/issue229_autonomous_search.json)）。

**証拠の保管と限界：** 選抜完全L/C/k・6設定Cv・ソースとMNA報告は[EXP-042](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/main/experiments/chatgpt_topology_search/runs/EXP-042)、[EXP-047](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/main/experiments/chatgpt_topology_search/runs/EXP-047)、EXP-043/045/048/049/050〜055各runに残す。旧24候補カタログ、RF-T005/F003・RF-T007の派生ParetoとW4棚卸し/ZIPは知見を統合した後に退役し、[整理前の固定Git原文](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/246444b93fb6e6b082af6ece3c5bfc7bcaff05c9/data)で確認する。元EXP manifestや現行RF loader/registryは不変更。数値条件の差、内部guard、元の選別証拠深度・非収束状態を失わせない。連続周波数極値、Q(f)、SRF、EM、磁気結合符号の物理的同時実現、温度・公差・実測は未検証。Gitの歴史的原文へのアクセスを**今回新しいMNAや最適化を実行したこと**とは呼ばない。

## RF-T008 v3の横断比較（2026-10-20の固定履歴）

**条件：** RF-T008 rev3 **試験**、当時の実効SHA `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`、`full_lpf`、固定外部S2P、50Ω源／60−j40Ω負荷、全6設定・28個別区間×1,001点の有限評価。後続schema2の実効SHAや正式RF-F003の成果に読み替えない。EXP-062〜065は合計264 start（249収束・15非収束）、選別10 checkpointの保存済み84点独立枝電流MNA証拠をレビューした。

| chip面積 | L / GJM | 有限格子worst IL [dB] | 観測ベストの出典 |
|---:|---|---:|---|
| 3 | 3L / 0GJM | 1.010350255 | EXP-058、EXP-063で再確認 |
| 3⅔ | 3L / 1GJM | 0.934027580 | EXP-058、EXP-063で再確認 |
| 4 | 4L / 0GJM | 0.929126781 | EXP-064、PCB-C配置探索で更新 |
| 4⅓ | 3L / 2GJM | 0.928118761 | EXP-058、EXP-063で再確認 |
| 4⅔ | 4L / 1GJM | 0.837133749 | EXP-059、接地PCB-C配置で更新 |
| 5⅓ | 4L / 2GJM | 0.829711540 | EXP-065、EXP-062時点0.833505430から更新 |
| 6 | 4L / 3GJM | 0.827841148 | EXP-062 |

これは**探索した構成集合内の観測非劣解**であり、大域Paretoではない。面積6⅔（4L/4GJM）の局所ベストIL=0.837795449dBは、より小さい面積6の0.827841148dBに**支配**され、上表には加えない。

**トポロジーと失敗の教訓：**
- 面積4の4L/0GJMはEXP-058時点の局所best 0.948650159dBでは面積3⅔に支配されていたが、EXP-064の12配置×2初期値（24/24収束）で0.929126781dBに改善し、新しい観測非劣点となった。最初の配置で不利でも4L構成一般が不可能という証拠ではない。
- EXP-059の4L/1GJMは**23 PCB配置×2 DTC配置＝46回路、92 start（81収束・11非収束）**を実施し、41回路で収束済み30dB候補を得た。面積4⅔の保存元0.854367459dBから**0.837133749dB**へ改善。最良はN4–GNDとN3–GNDの接地PCB-C **2枝**（未装着の3枝目のゼロ埋め座標は部品ではない）。PCB-Cを単純に増設するより、接地点・Q・DTC配置を含めて共同最適化する価値を示す限定観測であり、部品の取り外し**だけ**の因果効果ではない。
- EXP-063の3L検証は24/24収束しても、対象3面積で既存EXP-058のPareto値を実質更新しなかった。EXP-065は8固定C配置×4 DTC配置×3 Lグラフ＝**96回路／192 start（178収束・14非収束）**で面積5⅓を0.833505430→0.829711540dBへ改善。ただし狭い試行範囲での非改善も、当該構成一般の限界証明ではない。

選別点のH2/H3は有限格子でほぼ30.005dBの内部guard近傍。**公称35dBとIL≤0.30dBは未達**。保存済み独立MNA報告・部品/SPD・電力残差を第三者が照合したが、レビュー自体は全28区間の独立RFネットワーク再計算ではない。連続帯域極値、Q(f)、SRF、物理的同時signed k、EM、温度／公差、IC/PCB実面積、実測は未確認。**EXP-058のmanifest/storage_recordは依然`running`であり、数値選別点の存在を保存完了へ遡及修正しない。**

出典：現行の[EXP-058選抜ベクトル](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/main/experiments/chatgpt_topology_search/runs/EXP-058/pareto)・[EXP-059配置比較](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/main/experiments/chatgpt_topology_search/runs/EXP-059/pareto)・EXP-062〜065の各checkpoint/MNA、[レビュー原文](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/3370ea4/docs/results/rf_t008_pr148_151_independent_review_20261020.md)。PR間の暫定・統合集計を含む**派生7スナップショット**および旧専用レビュー・curationコードは研究知見統合後に削減し、原文は[削減前の固定Git履歴](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/762b58d8de97717e3ab651da8ec47ee6daa868c7/data/pareto_snapshots)と[旧専用コード](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/762b58d8de97717e3ab651da8ec47ee6daa868c7/scripts)でのみ参照できる。選別10件の独立MNA履歴は各EXPの保存証拠であり、この編集では新しいRF計算・EXP・独立MNAを実施していない。

## RF-T008旧条件の多初期値と座標A/B比較

[#233の固定3構成×3-start](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/6ac982306cd5899dee99b40dee660d3a6986db89/data/validation/issue233_multistart_pilot/README.md)と[#237の同一初期値9ペア対照](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/6ac982306cd5899dee99b40dee660d3a6986db89/data/validation/issue237_coordinate_ab/README.md)から、**探索の数値収束とRFの厳密適合を分ける必要性**が確認された。いずれもRF-T008 rev3 **trial**、`full_lpf`、当時の実効SHA `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`、外部固定S2P・6設定／28個別区間の結果。現在のschema 2 RF-T008の実効SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、正式RF-F003とは混合しない。

| 実行済み比較 | start／数値収束／非収束 | 17点/区間の厳密H2/H3≥30dB | 観測と限界 |
|---|---|---|---|
| #233：3構成×nominal/Sobol index 0/1 | 9／7／2 | **0/9** | 全件component・box・接続role・全L行列SPDはPASS。nominal 3本は先行1-startのILを再現。多初期値のRF適合改善は未観測 |
| #237 A：物理座標、同9初期値 | 9／7／2 | **0/9** | #233のstatus・nfev・17点forward ILを再現した新EXP-096等 |
| #237 B：正規化座標、同9初期値 | 9／8／1 | **0/9** | 1件の収束増加はRF適合増加を意味せず、有限差分の物理stepも変化 |

#233は18 stage／12,206 nfev、#237はA: 18 stage／12,206 nfev、B: 20 stage／10,312 nfev。#237 BのEXP-100は既存v2の回復操作を1回含む。同じ初期値と予算**規則**でも実際のstage・評価回数は異なる。短時間の単回・非ランダム順の計時から速度優位を一般化しない。

**境界の実例：** #233 EXP-091は精3点ではH2=`30.00000000002153`dB、H3=`35.20079203442586`dBだが、passband epigraph残差`−1.26e−11`dBでchecked選別対象外。17点ではB28・1422.875MHzのH2が`29.713319322336265`dBへ低下した。#237のA EXP-108は非収束、対応B EXP-109は数値収束したものの、17点最小H3=`29.996923233368015`dBでstrict FAIL。B EXP-100も回復後のH2=`29.999999999956906`dBでFAIL。**丸め・許容差によるPASS昇格は行わない。** 非収束時の巨大な負のepigraph `t` は物理挿入損失ではなく、worst ILは保存された回路ベクトルのforward値とする。

両比較は粗2点／精3点の探索から17点/区間の有限forward評価まで。厳密30dB適合候補が0件のため、**密格子1,001点／区間、独立枝電流MNA84点、passivity／power balanceは全件 `not_run`**。部品／SPD検査PASSも、実際のレイアウト・Q(f)・SRF・EM・公差・実測・物理的signed kの実現保証ではない。旧Paretoとの異格子・guard・回路接続差を無視してIL順位を統合しない。

詳しい解釈は[手法ノート](methods.md#多初期値座標正規化有限格子での探索上の教訓rf-t008旧条件)。数値根拠は[#233集計](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/6ac982306cd5899dee99b40dee660d3a6986db89/data/validation/issue233_multistart_pilot/report.json)と[#237集計](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/6ac982306cd5899dee99b40dee660d3a6986db89/data/validation/issue237_coordinate_ab/report.json)。参照したREADME・集計JSON・対照の補助コードは[固定Git履歴](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/6ac982306cd5899dee99b40dee660d3a6986db89/data/validation)で確認できる。EXP-086〜112の27件の17点検証overlayは、各EXPの`validation/17pt.json`へ**バイト同一で移動**し、正式manifest／storage_recordの証拠パスだけを移行した（SHA-256・数値・収束／RF検証状態は不変）。旧manifestの元バイトは[移動前の固定コミット](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/6ac982306cd5899dee99b40dee660d3a6986db89/experiments/chatgpt_topology_search/runs)に残る。この記述は**既存の実行済み結果の抽出**であり、再最適化・追加RF検証・現行正式RFへの再判定を実施していない。

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

## 旧data/validationの整理とRF-F002の教訓（Issue #397）

2026年10月のRF-F001/F002、RF-T003/T004、旧Phase 2 manager/solverの補助記録を分類した。削減前の`data/validation/`は**182件・4,351,659 bytes**。**旧補助182件・4,351,659 bytesを削除**する。EXP-047の非標準manifestと選抜証拠はEXP配下に維持し、元manifestの固定Git blob SHAと必要な現存証拠の検査によって従来の実験索引行を照合する。旧原文は[変更前の固定Git履歴](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/246444b93fb6e6b082af6ece3c5bfc7bcaff05c9/data/validation)から確認できるが、現行treeだけでの再実行は不可。

**RF-F002旧実効SHA `f20d27e93451dcec2f823e6f7c3731c06d843050c4d2ace8b0b46ded605542e2`での観測**（現行正式RF-F003と比較しない）：

| 旧EXP | 実行済み成果と限界 |
|---|---|
| **032** | 4 start、maxiter各5のfull-LPF worker数比較で2-workerが約**1.853倍**。全点非収束／H2/H3必須30dB未達、長時間本番Campaignの高速化保証ではない |
| **033** | 座標正規化・有限差分刻みの違いを調査、maxiter120でIL≤0.30dB候補未達。異なるソースSHAやdirty worktreeを同一実験条件とみなさない |
| **034〜037** | SIGINT/SIGTERM・PID/lock・resumeのライフサイクル挙動を確認。EXP-035の1-worker **347.126秒**／2-worker **201.347秒**は限定ベンチ。元checkpointのoutput node 3をmanager node 2へ**remapせず**投入したため、そのoptimizer値は元EXP-017/023候補のRF再評価ではない |
| **038** | remap訂正後の2 topology×2 startが30/35dB stageで収束し、21点/区間で35dBを許容差内達成。ILは代表**0.378349/0.459808dB**、0.30dB未達。初期値近傍の同じ局所解は大域最適性ではない |
| **039** | 9点から17点/区間への最適化格子変更で2局所点のIL差**1e−11dB未満**、21点で再評価。連続帯域の極値保証ではない |
| **040** | scaled FTOL=1e−8/1e−6の2初期値は類似解。unscaledはともにmaxiter=60に達し非収束。EXP-017由来のunscaled IL約**0.318693dB**は30dB tolerance内であって35dB適合ではない |
| **041** | 30dB点IL約**0.318693dB**、35dB点約**0.378349dB**。収束・許容差・strict適合とIL目標を分離する |
| **016/017・旧T003/T004** | [旧試験結果](#旧rf-f001t003r2の成果と限界)と[回収・訂正](#訂正回収再現性元記録を上書きしない)へ代表値を抽出済み。EXP-017の完全回収ベクトルは各EXP側にあり、旧trialを現行正式値に転用しない |

**科学的境界：** 現行のEXP-016/017/023/034〜041の原manifest・選抜checkpoint・実験索引を改竄しない。EXP-034〜041の旧manifestに登録された`data/validation/`補助原本は欠損するが、**元manifest自体のSHAで固定した17件（EXP-025〜041）の履歴索引監査のみ**、欠損した旧データを除外する。現存する登録証拠のSHA照合は継続し、直接`validate_manifest`、新規EXPのG0〜G5、正式RF/独立MNAの科学回帰には例外を設けない。EXP-047用overlayは退役し、元の非標準manifestおよび既存の索引行は改変しない。旧RF-T003専用リプレイスクリプト／専用テストは原入力と一体で削除し、現役のSPD・受動性・電力保存・独立枝電流MNA検査を残す。

**未実施：** 旧全候補の再最適化、1,001点全帯域と84点MNAの再計算、連続周波数極値・EM/Q(f)/SRF/公差・実測。旧記録中の有限結果と今回の整理作業を混同しない。

## 旧RF-F001/T003・R2の成果と限界

以下は旧一定Q・旧可変C範囲・強結合モデルの履歴で、現行RF制約へ持ち越しません。各候補の全L/C/kと6設定Cvは[削減前の固定validation Git履歴](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/246444b93fb6e6b082af6ece3c5bfc7bcaff05c9/data/validation)、探索の試行数・中断・未実行範囲は[整理前の逐語文書](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/3370ea4/docs)にあります。新たなRF再計算は行っていません。

- **EXP-015/R2**：[固定監査JSON](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/r2/EXP015_COMMON_MODEL_AUDIT.json)は4候補を7,001点/区間で再現（保存メトリック差0）、各72点の3方式照合で最大利得差3.17e−15、電力残差3.36e−17W。旧3CのHV/HQ候補はRF-T002接続条件に適合、2C候補はF001/T001/T002いずれも不適合。全4件30dBを満たすが35dB・IL0.30dBは未達。API移管計画と実装済みを混同しない。
- **EXP-016旧F001探索**：GJM Q80とPCB-C Q40は別部品。元217探索・追補の実行環境と完全ログは不明。初期報告を後のRF-T004正式検証と読み替えない（下記の事後追試を区別）。
- **EXP-017旧2C統合比較**：共通シャントノード、片側シャント固定化、固定Cでの共振枝結合は別グラフ。35.005dB探索を後日承認された30dBのRF-T003成果へ再分類しない。非GND橋絡Cvは固定L並列であり主経路直列ではない。

RF-T003は旧F001基準（effective SHA256 `e0c45f7094ced1ed2ccb91cae474c7c3c1a6af73a495a2a9cf8f512ccb45ab08`）、1対GND＋1非GND橋絡Cv、各0〜4pF/Q80、隣接|k|≤0.4の**試験**です。下表の主要選抜解は28個別区間×7,001点＋84代表点独立枝電流MNA、SPD・電力の元検証記録を持ちます。全探索試行がこの深度で検証済みという意味ではありません。

| 系列／チップ費 | 保存時の最悪IL dB・最小減衰 | 旧JSON（削減前data/validation/）の出典と解釈 |
|---|---|---|
| 4L/2GJM、5⅓ | 0.376495319 / 30.000828dB | `rft003_20261012/target30_results.json`。IL未達。比較35dB版0.491136506との差は異なる共同最適化解 |
| 5L/2GJM、6⅓・初期拡張 | 0.361230713 / 約30dB | `rft003_20261013/phase2_5l_results.json`。配列変更後0.348361188は`continued_5l_coupling_row.json`。IL未達 |
| 7L/2GJM/3PCB、8⅓ | 0.299845269 / 30.006584dB | `rft003_20261013/seven_L_3PCB_best.json`。公称微差、実装保証なし |
| 7Lからの6L縮約、7⅓ | 0.301780900 / 30.004702dB | `rft003_20261013/cost_reduction_screening.json`。IL未達、並列Lの単純合成不可 |
| 6L/3GJM/3PCB、8 | 0.299744774 / 30.011dB | `rft003_20261013/cost_down_continuation_new_best.json`。GJM追加のモード結合、余裕30.03dB版はIL未達 |
| 6L/1GJM/3PCB、6⅔ | 0.297613445 / 30.003dB | `rft003_20261013/six_L_one_GJM_cost_6p67.json`。GJM削除だけでなく共同再最適化。30.1dB版0.299151 |
| 全L≤25nH・新物理列、6⅔ | 0.295452340 / 30.101dB | `rft003_20261013/new_25nH_row30p101_best.json`。物理列L2–L1–L3–L5–L0–L4。25nHは感度条件でSRF改善実測ではない |
| 同25nH列の減衰余裕 | 0.298684250 / 30.30dB、0.299505228 / 30.35dB | `rft003_20261013/row25_rejection_margin_variants.json`。30.40dB版0.300330でIL未達 |
| 5L/2GJM/3PCB、6⅓ | 0.295989814 / 30.01dB | `rft003_20261013/five_L_cost6p33_candidates.json`。PCB3枝は異なる端点。30.1/30.2/30.3dB版IL0.297214/0.298585/0.299968、最後は余裕約0.000032dB |

低コスト探索の**未達**を成功へ昇格しません。5L/1GJM/3PCB（費5⅔）は別系列最良約0.308893dB、後の試験（`rft003_20261013/five_L_below6p33_cost_search.json`）は7,001点＋84点MNAで0.3083370097623731dB、最小H2 30.003840286/H3 30.004000000dBまで改善してもIL未達。GJM0や4L化、Q15置換の失敗は有限局所探索であって不可能性証明ではありません。LQP01HVの公表値域0.3〜16nHに対して仮想27nH/Q15案は実製品候補でなく、値域内の最良0.325156dBもIL未達。多数の|k|=0.4、27nH端点、微小PCB容量、符号の同時実現・Q(f)/SRF/EM/公差は未確認。原SLSQP全開始点のコード／ZIPはGitコミット完全固定ではなく、再計算器の存在は探索全履歴の再現を意味しません。

## 訂正・回収・再現性（元記録を上書きしない）

### EXP-016/017と旧RF-F002 runner

- **EXP-017 0.301248245dBは30dB点、35dB点ではない。** 当初RG-001 openだった完全ベクトルは後日回収済み。旧「未回収」を現在の結論にしない。[回収追試の固定Git履歴](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/246444b93fb6e6b082af6ece3c5bfc7bcaff05c9/data/validation/exp017_rf_f002_recovered_20261015/summary.json)はIL0.3012482451489075、H2 30.004999999986865、H3 30.004641701571376dB、電力残差1.8214596497756474e−17W。IL目標は未達。
- 原ZIPの26member目録は[整理前の固定履歴](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/c2143b0f9322f0a16f2eb39073ed243a8d0e4b51/data/exp017_rf_f002_source_zip_index_20261015.json)。元2,959B候補は`EXP-017/EXP017-LQW4-H30-NEAR.original.json`、SHA256 `fa997fb131a1237c41ec8a42ead80e40fe2436275a7e944837afecea9c387896`。`.recovered.json`は正規化表現でバイト原本ではない。ZIP本体と残り25memberはGit未収録、453局所試行の再最適化はしていない。
- 別の`RF-T004-EXP017-bundle.zip`（118,646B、SHA256 `48175d3579d3814e5d3740858ee3959b88e9731b835cb2cd306ce6b0093ae640`）は**RF-T004試験**の証拠。14,001点のIL `0.2999624819232782` をRF-F002欠落ベクトルと取り違えない。元ZIPはGit未収録。
- **EXP-016 READMEの完了主張とmanifestのunknown/not_runは時点が違う**。後日の4保存候補の7,001点/区間＋84点独立MNA追試は`data/validation/exp016_ci_replay_20261014.json`と`data/validation/exp016_rf_t004_numpy2_replay_20261014/summary.json`に別保存。CI 38587242196、commit `90c87551c4720441ba7120f1457ea318c752dc34`、RF-T004 effective SHA `c66302a281a1fdb88da355fc44dac1ef3b1c4e18e8ff297db9e842b219b5b0c4`。保存ベクトルの数値再現であって、初回探索・環境・事前登録の遡及証明ではない。
- **EXP-034〜037のwarm-start端子remap誤り**：manager停止・lock/resume・改変拒否の元ライフサイクル試験とその保存summaryは、誤remapのoptimizer値が保存候補の再評価であることを意味しない。EXP-034はSIGINT後max_attempts=1でpartial、SIGTERM後は実行中workerが終了するまでresumeを拒否してから結果を採用。EXP-036はmax_attempts=2で再開後completed。いずれも2 startの限定検査でRF性能の結論ではない。EXP-035の旧benchmarkは1 worker 347.126秒、2 worker 201.347秒だが全出力非収束・端子remap誤りのため候補品質比較ではない。訂正済みEXP-038/039の35dBは1e−5dB tolerance内、strictと同一でない。EXP-040 unscaledは非収束でも30dB residualがtolerance内で、収束とは別判定。旧runnerの一時ログ・lockは#359で削減し、元manifestは不変。過去のライフサイクル結果を今回再実行したわけではない。
- EXP-041の30dB点IL0.3186931893、35dB点0.3783490996は共にtoleranceのみ、IL未達。matching-only速度からfull-LPFの予算／大域限界を推定しない。旧100 graph S1/S2/S3は報告時未開始。旧F002の小規模5 startや4task runner smokeを完全トポロジー網羅と扱わない。

### EXP-042、046/047の原本と訂正

- EXP-042の[元10 ZIP（整理前固定Git履歴）](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/246444b93fb6e6b082af6ece3c5bfc7bcaff05c9/data/repository_reviews/w4_exp042_actions_original_zip_b64_20261018.json)は26,953B・19memberをSHA/CRC付きで当時保存。既存Gitとのバイト一致は空stderr 1件だけ。ZIPハッシュ確認は数値独立再計算ではない。`target_35.json`の元run38999677194と選別run38774357292、`area_cf1.json`の38999677183と38775558755は**別Actions run**。単なる同run内stage差と断定しない。
- 未選別`cf2/both/pcb_cf2`の6元JSON（23,460B）は[整理前の固定Git履歴](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/246444b93fb6e6b082af6ece3c5bfc7bcaff05c9/data/repository_reviews/w4_exp042_recovered_original_members_20261018)に当時バイト同一で保存。存在しない3つの選別checkpointを生成しない。元報告は1,001点＋84点MNA、暫定IL0.8dB未達、既存同面積よりILが悪くIL/面積の新パレート根拠なし。調波余裕等も含む全面的劣位や独立再検証済みを意味しない。
- EXP-046の初期「全て30dB未達」と後続別4Lの一部達成は別時点。容量損失会計の訂正版は`independent_verified_1001_corrected.json`。旧容量診断を引用せず、訂正前後を保持する（保存説明ではIL/H2/H3非影響）。dirty実行・seed/environment欠損を捏造しない。
- EXP-047のQインデックス誤りは`Q[5]=80`ではなく正しいGJMの`Q[1]=80`。元manifestの`q_bug_excluded_files`の5原本は正式性能順位から除外。manifest上6検証候補とパレート採録4候補を区別。optimizer commit/seed/environmentはunknown、Actionsでの元探索再実行証明はない。

## 文書統合と固定監査の読み方（Issue #352）

研究解釈は本ページと[methods](methods.md)、現役実装とゲートは[roadmap](roadmap.md)、運用は変更しない[instructions](../project/instructions.md)へ集約しました。W3/W4/W5の当時の監査完了・CI成功は、原研究の数値再実行、重要証拠の削除許可、研究Phase移行ではありません。225件、131件、46件の台帳は重複し得る別集合で、単純合算しません。旧39/31/3 workflow数や「未merge」は各報告時点の意味で、現役状態ではありません。

[W3統合文書](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/archive/w3_consolidated_documents_20261017.md)は当時のD-001〜004の出典・承認を記録する。正式EXPの残存するmanifest・選抜point・独立MNAが現在の証拠であり、退役した旧W4/W5の[原レビュー資料](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/246444b93fb6e6b082af6ece3c5bfc7bcaff05c9/data/repository_reviews)は当時の原blob分類・終了状態・訂正の参照に限ります。時点固定のW4/W5保全一覧は[整理前tree](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/c2143b0f9322f0a16f2eb39073ed243a8d0e4b51/data/repository_reviews)にあり、数値再検証ではありません。削除した日付別文書の逐語内容と試行内訳は[整理前tree](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/3370ea4/docs)、元pathごとの処置・残置callerは[PR #353](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/353)に記録します。復元専用機能・新アーカイブは追加しません。

Phase 2継続、Phase 3未承認。この整理で新しい科学的結論、RF条件、原EXPの実行／検証状態を変更しません。
