# RF-F003旧版とRF-T005〜T008の代表結果

**対象：** 条件実効SHA別のPareto、面積・IL・減衰、独立MNA深度、trial条件差。旧研究条件の数値・仮説を現行RF-F003適合と混同しない。
**出典：** [旧results原文](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/d536a3f1a1b79b8e9be3db4752f1a8b05fa60e65/project/results.md)（PR #411以前のmain固定版）。内容は既存研究の移設であり、新規RF/MNA実行ではない。

**本書は研究ナレッジベースの代表結果・失敗要因・検証限界の正本です。** [Issue #397](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/397)により、正式記録に不要な旧raw・checkpoint・補助数値は知見抽出後に削減します。古い結果の参照先が現行treeからGit固定履歴へ変わっても、当時の検証状態は変わりません。過去全試行の完全再現は保証しません。

数値原本は[実験索引](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/data/experiment_index.csv)と各EXPのmanifest・候補・検証記録です。有限格子のbest-foundを大域最適性、連続帯域保証、実装性能の保証とは扱いません。正式／試験／旧条件、`matching_only`／`full_lpf`、bare LPF／外部ポートを混ぜず、実効制約SHA・格子・検証深度が同じ候補だけを比較します。

| RF条件 | 保存証拠への入口 | 注意 |
|---|---|---|
| **RF-F003（正式）** | [EXP-047](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/main/experiments/chatgpt_topology_search/runs/EXP-047) | 正式2可変C、2026-10-17固定パレート4件は当時の記録 |
| **RF-T005（試験）** | [EXP-042](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/main/experiments/chatgpt_topology_search/runs/EXP-042)、同階層EXP-043/045 | 最大3可変C、固定パレート6件 |
| **RF-T006/T007（試験）** | [EXP-048](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/main/experiments/chatgpt_topology_search/runs/EXP-048)、同階層EXP-049/055 | 追加阻止帯・固定寄生モデルを区別 |
| **RF-T008 v3（試験）** | [EXP-058](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/main/experiments/chatgpt_topology_search/runs/EXP-058)、同階層EXP-062〜068 | IC固定C＋最大2可変C、各EXPの収束・独立MNAを個別確認 |

2026-10-17のRF-T005／旧RF-F003派生Paretoと24候補カタログは[以下の固定比較](../results.md#正式rf-f003旧版とrf-t005t007試験の固定比較2026-10)へ知見を統合し、旧派生原文は[マージ前の固定Git履歴](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/246444b93fb6e6b082af6ece3c5bfc7bcaff05c9/data)からのみ参照できます。最低必須30dB、公称35dB、IL目標0.30dBは別判定。Q(f)・SRF・EM・公差・実測は未保証。[ロードマップ](../roadmap.md)／[手法・解釈](../methods.md)。

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
