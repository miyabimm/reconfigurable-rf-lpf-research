# 探索手法・Pareto・数値判定の教訓

**対象：** RF-F003対trialの比較境界、多初期値・座標・格子、Paretoと旧RF-F002の失敗、実行済みA/B数値。旧研究条件の数値・仮説を現行RF-F003適合と混同しない。
**出典：** [旧methods原文](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/d536a3f1a1b79b8e9be3db4752f1a8b05fa60e65/project/methods.md) / [旧results原文](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/d536a3f1a1b79b8e9be3db4752f1a8b05fa60e65/project/results.md)（PR #411以前のmain固定版）。内容は既存研究の移設であり、新規RF/MNA実行ではない。

## 過去RF-F003と試験トポロジーの比較境界

**2026年10月の旧条件のみに適用する教訓：** [実行済みの正式/試験別結果](../results.md#正式rf-f003旧版とrf-t005t007試験の固定比較2026-10)を参照。制約IDだけでなく実効SHA・可変C個数・接地DTC付属寄生・追加阻止帯・固定外部S2P・測定格子・検証深度を一致させて比較する。旧RF-F003 `f8571020...`や旧RF-T005/T006/T007の局所値を現行schema2の正式RF-F003 `e12c42b1...`の達成値に転用しない。

- **構造変更は目的ごとに再最適化する。** RF-T005で3枝のCvが使える場合と正式RF-F003の2枝、RF-T007で接地DTCごとに0.5pF/Q40を強制する場合は同じ回路でも別条件。#EXP-055でCv接続を変更して4LのILを0.875795→0.817366dBに改善したが、内部30dB guardは約0.005dBであり製造余裕の証明ではない。
- **追加阻止帯は通過損失を増やしうる。** RF-T006の全設定3〜6GHz≥20dB追加によりEXP-048は面積5⅓でIL2.920706dB。EXP-049のQ33モデル・面積18でもIL1.166797dBで目標1.1dB未達。Lの公表値域（0.8nH下限）と定数Q/SRF実現性を区別し、20dB達成の狭い0.080dB余裕を物理保証としない。
- **磁気結合は図式・signed k・全行列SPD・実現性を分ける。** 歴史的24候補の構造CSVは旧14候補の電気接続を`unknown`とし、EXP-042の一部接続も関連EXP-047資料からの推定だった。signed kのベクトル一致は巻線極性、PCB配置、Q(f)、受動性の製作後保証ではない。旧棚卸しで照合できたGit blob SHAやZIP CRCもネットワークの独立MNA再計算とは異なる。

今回の整理は既存保存結果の要約のみで、新しい可変C上限・評価指標・RF topology判定やBSF合成式を変更しない。正式制約は[active registry](../../rf/constraints/registry.json)で判断する。

## 多初期値・座標正規化・有限格子での探索上の教訓（RF-T008旧条件）

**適用範囲：** [#233多初期値](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/6ac982306cd5899dee99b40dee660d3a6986db89/data/validation/issue233_multistart_pilot/README.md)と[#237座標A/B](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/6ac982306cd5899dee99b40dee660d3a6986db89/data/validation/issue237_coordinate_ab/README.md)の**実行済み**有限探索。どちらも `full_lpf`、RF-T008 rev3 **trial**、当時の実効制約SHA `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`、固定外部S2P・全6設定／28不連続区間を使用。現在のschema 2 RF-T008の実効SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`とは別条件であり、現行RF-F003の実績へ転用しない。

- **開始点は収束とRF適合を分けて評価する。** #233は固定3構成×nominal/Sobol 2点の計9 startで数値収束7件、17点/区間の厳密H2/H3≥30dB適合0件。nominal 3本は既存1-startの損失値を再現し、3L0GJMのSobol index 1もnominalに近い損失へ到達したが、適合率や最悪ILの改善は観測されなかった。少数startで多初期値一般の無効性や最適解不在は結論できない。
- **正規化は単独の解決策ではない。** #237は保存済み9初期値を物理座標A／正規化座標Bで各1回比較し、収束A=7/9、B=8/9、17点strict適合は両方0/9だった。両方式ともSciPy 1.18.1の既定絶対有限差分 `eps≈1.49e-8` を各座標単位に適用するため、Bでは物理有限差分幅もbox幅倍に変わる。座標変換だけの因果効果、安定した速度優位、正規化の標準採用は示されていない（実消費stage・nfevも異なる）。
- **格子と制約残差は段階別に厳密判定する。** 粗2点／精3点のsolver `status=0` は密格子でのRF適合を意味しない。#233のEXP-091は精3点のH2/H3自体が30dBを上回っても、passband epigraph残差が微小負でchecked対象外となり、17点再評価ではB28のH2が29.713319dBへ低下した。30dB直下を丸め・許容差でPASSにせず、H2/H3・passband残差と測定格子を別々に報告する。
- **epigraph変数 `t` を物理ILと取り違えない。** #233の非収束EXP-086/093では最終`t`が巨大な負値へ破綻した。報告するworst ILは**最終完全回路ベクトルをforward評価した値**であり、`t`でもsolver successでもない。破綻を含む開始点をRF適合Paretoへ昇格しない。
- **次回の探索設計への示唆（未実行提案）：** まず失敗を「非収束／epigraph破綻」「厳密閾値直下」「周波数格子内部の見落とし」に分ける。回復法・座標系を比べるなら、初期値・有限差分の**物理**摂動量・制約閾値/guard・評価格子・予算を固定し、収束、strict適合、IL、費用を別指標で比較する。17点も連続帯域保証ではなく、今回strict候補0のため1,001点/区間・84点独立MNA・電力／受動性の後段検証は**未実施**。方法の採用や追加実験を承認したものではない。

代表値・9ペアの全記録と限界は[結果の整理](../results.md#rf-t008旧条件の多初期値と座標ab比較)および各[元集計](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/6ac982306cd5899dee99b40dee660d3a6986db89/data/validation/issue233_multistart_pilot/report.json)・[対照集計](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/6ac982306cd5899dee99b40dee660d3a6986db89/data/validation/issue237_coordinate_ab/report.json)を参照する。集計README/JSONへのリンクは削減前の固定Gitコミットを指す。27件の17点検証overlayはEXP-086〜112の各`validation/17pt.json`へ元JSONのGit blob/SHA-256を変えずに移動し、保存manifest／storage_recordの**参照パスだけ**を更新した。旧metadataの原文は移動前の固定Git履歴に残る。この統合は既存結果の読取りであり、新しいRF計算・EXP・独立検証を実施していない。

## Pareto支配と配置選択の教訓（RF-T008 rev3の歴史的局所探索）

**出典・有効範囲：** [EXP-058/059・062〜065の整理結果](../results.md#rf-t008-v3の横断比較2026-10-20の固定履歴)。固定外部S2Pと6設定・28区間×1,001点、必須H2/H3≥30dB、当時のRF-T008 rev3 trial実効SHA `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`の探索済み部分集合に限る。

- **非劣性は再最適化後の同条件比較で判定する。** 面積4の旧4L/0GJM候補は低面積3⅔に支配されていたが、EXP-064のPCB-C配置探索で非劣点に変わった。局所探索で見つからないことを構成不可能の証明にせず、固定した面積クラスの異接続・異開始点を比較する。
- **PCB-Cの配置・損失・枝数を独立に考える。** EXP-059ではhot-hot Q40のPCB-C橋絡の代わりにN3–GND/N4–GND（接地Q60）を使う4L/1GJM配置が有利だった。最良に3枝目のPCB-Cは装着されない。配線・Q・値とDTC接続を含む共同再最適化の観測なので、単一枝削除や接地化だけの因果効果と断言しない。
- **部品費増加は性能改善を保証しない。** 面積6⅔/4GJMのbestは面積6/3GJMに支配された。他方、面積5⅓の96回路同時組合せではEXP-062基準から小幅改善した。L/GJM/PCB-C個数だけで候補を並べず、接続役割・物理列・結合SPD・選抜ベクトルと全設定の性能を同時に検証する。
- **探索停止・検証深度をParetoから分離する。** 数値収束、有限格子30dB、84点独立MNA報告、電力保存、35dB公称目標、IL≤0.30dB、連続帯域と製作可能性は異なるゲート。小さな内部guard（約0.005dB）を製造余裕と解釈せず、保存済みMNA結果の監査を新たな独立解法実行と呼ばない。

これらは次の探索で配置と初期値の多様性を確保する**設計上の示唆**であり、新たなRF最適化やPhase移行の承認・実施記録ではない。

## 旧RF-F002のsolver・manager設計の教訓（Issue #397）

[旧RF-F002の実測・非収束記録](../results.md#旧datavalidationの整理とrf-f002の教訓issue-397)は、現在の正式RF-F003で再実行していない。学ぶべき点は次の四つである。

- **checkpoint端子の写像を保存前に検証する。** 旧EXP-034〜037では元output node 3とmanager node 2のremapを欠き、ベンチ・復旧の検査結果が候補RF再評価結果でない。端子・接地・接続roleと全設定のforward一致を新規実験のG1で明示する。
- **solver成功と厳密RF/ILを分離する。** 旧EXP-038の35dBは`1e−5dB`許容差内で、最悪ILは0.30dB未達。EXP-040のunscaledは非収束で、30dBと35dBの達成度も異なる。9/17点の局所安定性は28×1,001点・独立MNAや連続帯域の保証ではない。
- **並列高速化を小さい旧負荷から外挿しない。** 旧4 start短時間の1.85倍と別の旧4taskの1.72倍は異なる条件。新規負荷では同一worker/seed/grid/sourceで反復・費用・停止状態を測る。
- **旧証拠の退役と現役保存契約は別。** SHA固定のEXP-025〜041原manifestはそのまま保管。履歴索引に限って欠損した旧`data/validation/`補助証拠を除く。現存証拠・直接manifest検証・新規EXPのG0〜G5は厳格なSHA比較を維持する。

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

詳しい解釈は[手法ノート](../methods.md#多初期値座標正規化有限格子での探索上の教訓rf-t008旧条件)。数値根拠は[#233集計](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/6ac982306cd5899dee99b40dee660d3a6986db89/data/validation/issue233_multistart_pilot/report.json)と[#237集計](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/6ac982306cd5899dee99b40dee660d3a6986db89/data/validation/issue237_coordinate_ab/report.json)。参照したREADME・集計JSON・対照の補助コードは[固定Git履歴](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/6ac982306cd5899dee99b40dee660d3a6986db89/data/validation)で確認できる。EXP-086〜112の27件の17点検証overlayは、各EXPの`validation/17pt.json`へ**バイト同一で移動**し、正式manifest／storage_recordの証拠パスだけを移行した（SHA-256・数値・収束／RF検証状態は不変）。旧manifestの元バイトは[移動前の固定コミット](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/6ac982306cd5899dee99b40dee660d3a6986db89/experiments/chatgpt_topology_search/runs)に残る。この記述は**既存の実行済み結果の抽出**であり、再最適化・追加RF検証・現行正式RFへの再判定を実施していない。
