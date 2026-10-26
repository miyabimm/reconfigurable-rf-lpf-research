## 2026-10-20：RF-T008改訂v3（2可変C上限、Phase 2・研究試験）

所有者の明示指示により、試験RF-T008で**IC可変C最大3枝→最大2枝**とする（設置数0～2）。各枝に1対1で付随する高Q IC内固定Cも最大2個。各枝Hot-Hot固定0.2～3pF/Q60、Hot-GND固定0.5～3pF/Q60、可変0～3pF/Q35、固定C全バンド共通のv2モデルは不変。通常PCB-Cは対GND 0.02～1pF/Q60、Hot-Hot 0.02～0.2pF/Q40、計最大3個を維持。RF-T007の旧対GND DTC寄生0.5pF/Q40はRF-T008では重複させない。RF-F003とRF-T005/T006/T007は不変更。実効policyの枝数、結合可変・IC固定Cとレジストリを同時更新し、CIで3枝を拒否する。**2-Cvのパレート探索はまだ実行していない**。新EXPのmain予約・正規S2Pに基づく6バンド最適化・独立MNA・パレート非支配判定は別作業。v2履歴：コミット`2a6374cd6bc871873eac5cfa43eed4a8a0c68719`。Phase 2継続、Phase 3未承認。

## 2026-10-20：RF-T008改訂v2（履歴：当時は最大3可変C枝）

ユーザー承認により、ICのOFF残留寄生という見方を**設計時に選定するIC内固定C**へ拡張。可変C最大3枝／枝0～3pF/Q35は不変。**IC固定Cは各設置DTCと同一端子間に1枝、Hot-Hot 0.2～3pF/Q60、Hot-GND 0.5～3pF/Q60**、全6バンド共通、OFF時も存続。枝合計上限は6pF、損失付きYをCfix/Q60とCvar/Q35で別々に計算。RF-T008初版のシャント0.5pF/Q40枝は**置換済み、二重stamp禁止**。RF-T007従来Q40モデルは不変更。**通常PCB-Cは対GND 0.02～1pF/Q60（既にQ60であり継続）、Hot-Hot 0.02～0.2pF/Q40、最大3個で不変更。** 固定IC-CはPCB-C個数へ算入しない。IC物理面積/Q(f)/SRF未評価。新制約、レジストリ、`src/lpf/constraint_versions.py`および専用検査`src/lpf/trial_ic_fixed_c.py`、回帰テストを改訂。正式RF-F003と他のtrialは不変更。**v2仕様での新EXP探索・28区間評価・独立MNAは未実施**。旧IL0.831046dBなどは旧条件下の予備結果でありv2の実績ではない。新EXPのmain事前予約・公式外部S2P使用・再最適化必須。Phase2継続、Phase3未承認。

## 2026-10-20：RF-T008初版・履歴（改訂v2でICモデル置換）

**ユーザー承認済みのPhase 2試験条件登録。** RF-F003を固定基準とし、RF-T007の最大3DTC（各0～3pF/Q35）およびシャントDTC各枝の常設寄生0.5pF/Q40を保持したうえで、通常の固定PCB-Cを**対GNDなら0.02～1.0pF/Q60、hot-hotなら0.02～0.2pF/Q40**として明示的に区別する。固定PCB-Cは両配置合計最大3個。追加0.5pFのDTC寄生は別枠・Q40固定。条件正本：`data/constraints/trial/RF-T008.json`、台帳、接続別検査器`src/lpf/trial_pcb_pattern_c.py`、回帰テスト`tests/test_trial_pcb_pattern_c_t008.py`。正式RF-F003と既存trial不変更。ユーザーのPCB実現性・Q60見込みは仮定であって物理検証完了ではない。**RF-T008での新最適化、1MHz格子に基づく確証、独立MNA、実部品・SRF/EM・公差評価は未実施**。前回の0.831046dB（接地PCB-C Q40）はRF-T008成果に流用禁止。新EXP番号のmain事前予約後に実験を開始する。Phase2継続、Phase3停止。

## 2026-10-20：EXP-057（EXP-055最優4Lの周辺インダクタ接続探索）

**Phase2／RF-T007、実行済み。** EXP-055の独立検証済み4L／面積5⅓／3DTC／IL0.8173655897607699dBを出発点とし、固定GJM01 Q80×2、PCB-C Q40×2、Cv0(3,GND)／Cv1(0,3)／Cv2(1,2) 0–3pF/Q35、**接地Cv0のみにOFFでも常在する別0.5pF/Q40**、物理L列 L0-L1-L3-L2と|k|≤0.10、固定外部S2P、6設定H2/H3≥30dBを保持。L電気接続のみ変更した**新規9種類＋元構成1種類の計10種類**の接続グラフを比較した。EXP-057は実行前にmainの中央台帳で予約済み。

**GitHub Actions [39371574312](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39371574312) SUCCESS。** 10接続×2初期値＝20試行、標準`slsqp-staged-v1`通常240/120反復、反復限界時だけ救済500/280。**19試行が正常収束、1試行は方向微分に起因する線探索停止（非収束；反復限界到達ではない）、実行例外0、救済再試行0**。選択した10構成は全6設定・28区間×1001点の必須30dB H2/H3を満たし、各84点独立9×9結合L枝電流MNA／受動電力収支PASS。

**最優はEXP-055の元Lトポロジー再最適化：最悪IL0.817365589674dB**。EXP-055記録からの差 −8.66×10⁻¹¹dBは数値誤差レベルであり改善実績と解釈しない。**新規9構成はすべて悪化**。新規最良はNode3シャント端Lを入力へ付替えた構成IL0.914280717727dB、次点はNode4接地C端Lを入力側へ付替えた構成IL0.915934801091dB（いずれも同面積）。変更Lグラフ集合での有限・局所結果であり全構成の下界や大域最良の証明ではない。

[EXP-057実験説明](../experiments/chatgpt_topology_search/runs/EXP-057/README.md)、[10構成数値結果](../experiments/chatgpt_topology_search/runs/EXP-057/run_summary.json)、[3つの完全設計ベクトル](../experiments/chatgpt_topology_search/runs/EXP-057/checkpoints/)、[独立MNA3件](../experiments/chatgpt_topology_search/runs/EXP-057/validation/)をGitへキュレーション。元20試行の完全raw JSONはActions artifact ID12241866186（30日保持）。ZIP SHA256 791abf3fa2f44fdca9ca738439269088e46b1a28e90ba672f50dad6acba232bd、元JSON SHA256 6662d8a89dfca7d8c462825535ea63113c10bb6a15a831ef412752e0636f6c17。

次の仮説（EXP-057では**未実行**）：EXP-055の優位な4L電気接続を維持し、固定Cまたは非接地DTC橋絡枝の配置を周辺再探索。今回は余剰H2/H3マージンや結合kの物理的同時実現性研究を行わず、35dB/IL≤0.3dB未達、連続極値／Q(f)／SRF／EM／公差未検証。正式RF-F003不変更、Phase2継続・Phase3未承認。

## 2026-10-20：今後のPhase2 SLSQP反復上限標準化（ポリシー変更、RF条件不変更）

オーナーの指示「適切な上限を設定して、今後の標準にしましょう」に基づき、**新規2段階SLSQP探索**に通常「粗240／精密120」、`Iteration limit reached`時のみ1回「粗500／精密280」（精密単独なら精密のみ）でウォームスタート救済する`slsqp-staged-v1`を設定。詳細は[`docs/slsqp_iteration_policy.md`](slsqp_iteration_policy.md)、実装は[`src/lpf/slsqp_budget.py`](../src/lpf/slsqp_budget.py)。新規探索は共有関数を利用し、適用／例外理由／停止メッセージ／反復数／前後ベクトル／収束状態／dense H2/H3・独立MNA結果を個別保存する。

根拠：EXP-055の160/80上限到達事例、EXP-056の500/280＋保存解ウォームスタート再探索（6試行全収束、IL新記録なし）。**通常値240/120は運用選択であり独立ベンチによる最適値の証明ではない**。救済値500/280の効果はウォームスタートと未分離であるため収束保証とみなさない。旧EXP-001〜056と実験数値、従来runコードは不変更。通常／救済の回帰テストをCIで実行、物理RF条件不変更、Phase2継続・Phase3停止。

## 2026-10-20：EXP-056（RF-T007・4L未収束2候補のSLSQP反復上限拡大）

**実行済み、Phase2。** 前回EXP-055でCV1(2,4)／CV1(0,1)のSLSQP粗探索が`Iteration limit reached`に達した件を再評価。これはGitHub Actions実行時間の不足ではない。main台帳にEXP-056を実行前予約し、保存済みEXP-055の各29値ベクトルを初期値として採用、SLSQP粗探索上限160→500、詳細80→280反復へ増加。RF-T007、固定外部入出力S2P、6設定、接地Cv0の固定寄生0.5pF/Q40、必須H2/H3≥30dB、4L/Q25・固定Cと可変C/Qを変更していない。

**結果：** [Actions 39344219070](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39344219070) SUCCESS。2接続×3試行の**6/6で粗／詳細の両SLSQP正常収束**、実行失敗0。Cv1(2,4)：IL0.849084050391dB（粗24・詳細25反復）、Cv1(0,1)：IL0.857268582225dB（粗48・詳細1反復）。両解とも28区間×1001点の必須H2/H3≥30dB適合、独立84点9×9結合L枝電流MNA・電力収支PASS。従来EXP-055で各0.849084050371dB、0.857268573929dBだった非収束局所値との差は微小。**EXP-055新最良IL0.817365589761dB（4L、面積5⅓）は更新なし。**

**解釈：** 温スタート化と反復上限延長を**同時に**行っているため、反復上限拡大だけの独立した効果を証明したわけではない。EXP-055の古いソルバー状態を収束済みに書き換えず、EXP-056の別々の**新規収束ベクトル**として保存。[EXP-056実験記録](../experiments/chatgpt_topology_search/runs/EXP-056/README.md)、[6試行の収束記録](../experiments/chatgpt_topology_search/runs/EXP-056/run_summary.json)、[完全設計ベクトル2件](../experiments/chatgpt_topology_search/runs/EXP-056/checkpoints/)、[独立MNA2件](../experiments/chatgpt_topology_search/runs/EXP-056/validation/)。原artifact ZIP SHA256 ab548ebb5a76ea680b6dbd83e4ee411ed7444f5cc4d60a088dddef68283efa38、原JSON SHA256 35a38af9b9f1a0599252c9351a69e2032ab6e37ac40dd1410d652a2242f02ac2。

有限格子、公称Q一定、局所最適化のみ。余剰H2/H3マージン追求、kの物理実現性、SRF/Q(f)、EM、製造公差、実測、Phase3は未実施。正式RF-F003不変更、**Phase2継続／Phase3停止**。

## 2026-10-20：EXP-055（RF-F003由来4LをRF-T007へ再合成・新局所IL最良）

**Phase 2／RF-T007実行済み。** EXP-047のRF-F003・4L・面積5⅓・2可変C保存ベクトルを出発点とし、RF-T007の接地Cv0(3,GND)へOFFでも常在する**別固定0.5pF/Q40**を加え、接地DTC数は1を維持したまま第3非GND可変Cの配置5案と2DTC基準型の計6トポロジーを探索。mainでEXP-055を事前予約、出典完全ベクトルと新スクリプトをPR #135へ追加。初回CIは新規予約行の日時形式ミスにより数値計算前に停止、日時形式修正後の同一Actions run [39341678211](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39341678211) 再実行が**SUCCESS**。

固定入出力原S2P、50Ω源、60−j40Ω負荷、6設定、28区間×1001点の外部端子IL/UL H2/H3≥30dB、4×LQP02HV/Q25、2×GJM/Q80、2×PCB-C/Q40、3可変C/Q35、隣接signed |k|≤0.10を維持。**18局所SLSQP試行（収束13／未収束5／失敗0）**。6構成すべての選別した必須30dB適合候補が84点の独立9×9結合L枝電流MNA・受動電力収支PASS。旧F003保存ベクトルは寄生なしでIL0.843652332dBを再現したが、T007寄生を無調整で加えるとIL1.160642294dB・H2/H3 13.74/18.48dBで不適合。F003実績をT007適合結果として扱わない。

**新観測最良（収束済み）：4L／面積5⅓／第3非GND Cv1(0,3)／worst IL0.817365590dB、最小H2 30.005000dB、最小H3 30.004810dB。** 以前のEXP-053の同面積4L・IL0.875794664dBより**0.058429074dB改善**。独立84点9×9 MNA最大IL差4.55e−13dB、電力差7.81e−18W。別案Cv1(2,4)はIL0.849084dB、Cv1(0,1)はIL0.857269dBだが**選択SLSQP未収束**（有限格子/MNA適合とは区別）。2DTC基準はIL0.881136dB。

根拠：[EXP-055 README](../experiments/chatgpt_topology_search/runs/EXP-055/README.md)、[6構成結果・収束台帳](../experiments/chatgpt_topology_search/runs/EXP-055/run_summary.json)、[新最良29値・6設定DTC完全ベクトル](../experiments/chatgpt_topology_search/runs/EXP-055/checkpoints/cv1_input_tip_best.json)、[独立MNA](../experiments/chatgpt_topology_search/runs/EXP-055/validation/cv1_input_tip_independent_mna.json)、[RF-T007観測局所パレート](../data/pareto_snapshots/rf_t007_exp055_4l_20261020.json)。実行ソースSHA e0b824c1、原Actions ZIP SHA256 995b86ad76a1530bb36820d89b51e5e9fefd8559b64c39c681934b3905058564、JSON SHA256 2d0fa0d7c1cbc8c3349f620a3fa2f20e40fd9dea8d90ff0616e9b4d4fcaf7f64。

**留保：** 最小H2/H3マージン約0.00481dBしかなく、正式IL≤0.30dB・公称35dB未達。隣接k2箇所が±0.10上限、PCB-Cが0.02/0.2pF境界。連続周波数極値・物理的同時k実現・Q(f)/SRF・EM・公差・実測は未実施（今回のオーナー指示では物理kと余剰減衰最適化はスコープ外）。局所有限格子の結果であり大域最適の証明ではない。**正式RF-F003不変更、Phase2継続、Phase3は明示承認まで停止。**

## 2026-10-19：EXP-054（RF-T007／4L固定Cと非接地DTCの複合トポロジー探索）

EXP-053で確認した4L・面積5⅓・最悪IL0.875794664dBの`split_input_shunt_center` L接続を保持し、GJM Q80×2、PCB固定C Q40×1、可変C Q35×3の接続変更を組み合わせた19新案と基準1案の計20構成を探索した。mainでEXP-054を数値実行前に予約・pre-run Git-only保存台帳を設定。RF-T007の対GNDシャントDTCはCv0(4,GND)の1枝とし、OFFでも存在する**別固定0.5pF/Q40**を常に保持。正式RF-F003不変更、Phase2のみ。

**実行済み：** 20構成×2初期値＝40試行、**33収束、7未収束**、実行失敗0。全20構成で28×1001有限周波数格子のH2/H3≧30dB適合候補を取得し、選択した20候補について84点の独立9×9結合インダクタMNA／電力収支はPASS。結果は**新構成での更新なし**。変更なし基準の最悪IL0.875794664233dB（実質EXP-053と同じ）に対し、最良の新配置はPCB Cf1(1,2)＋Cv1(0,3)で**0.884150780247dB**（悪化）。次点はCf1(3,2)＋Cv1(0,3)：0.884194124880dB。両者ともチップ面積5⅓。実験索引は完了、原Actions [39291751571](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39291751571)、SHA-256 `28cfe12add525cacdf674ac94e75a7f1637089239db119722ef5606ce28f1853`、3完全ベクトルと独立MNA、20候補要約と保存台帳を [EXP-054](../experiments/chatgpt_topology_search/runs/EXP-054/README.md) に記録。

オーナーの指定により、**追加H2/H3減衰マージン最適化と相互結合の物理実現性研究は行っていない**。必須30dBのみ維持。公称Q一定の局所探索と有限格子結果であり連続極値・グローバル最適を意味しない。次のPhase2では4Lの**L接続と固定C/DTC接続を同時に変えるグラフ**を検討する。RF-F003不変更、Phase3未承認。

## 2026-10-19：EXP-053（RF-T007／4Lインダクタ接続グラフの系統探索）

オーナーの「探索を続けて」指示により、EXP-053をmainで事前予約し、EXP-052の4L最良（チップ面積5⅓、PCB-Cf1を(0,2)入力―出力ブリッジへ接続、最悪IL0.885189326dB）の回路ベクトルを凍結した。RF-T007の公称固定対GND DTC寄生0.5pF/Q40はCv0(4,GND)に1枝のみ。GJM01/Q80×2、PCB-C/Q40×1、DTC/Q35×3、LQP02HV/Q25×4、面積・S2P・6設定・RF-T007必須H2/H3≥30dBは不変更。今回の**探索変数は4個のL接続グラフそのもの**（基準含む連結5ノード木グラフ12種類）。

**実行済み：[GitHub Actions 39284039531](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39284039531) SUCCESS。** 計24局所SLSQP初期値（**収束19／未収束5**）、12構成すべて有限格子における必須H2/H3≥30dB適合局所候補を得た。28区間×1001点・6設定で評価し、各候補独立9×9結合L枝電流MNA 84点のIL一致／電力収支PASS。**新最良4L** はL0(0,3)、L1(1,2)、LsA(3,1)、LsB(1,4)の「入力側L分割＋中央シャント」型で、面積5⅓・最悪IL **0.875794664dB**、最小H2/H3各約**30.005dB**。EXP-052の同条件0.885189326dBから**0.009394662dB改善**。独立MNA最大IL差4.405×10⁻¹³dB、最大電力収支残差5.204×10⁻¹⁸W、数学的L行列SPD確認。これをkの実装可能性研究として扱わない。

証跡：`experiments/chatgpt_topology_search/runs/EXP-053/README.md`、全12構成のIL／H2／H3と24初期値の収束件数`run_summary.json`、[最良4Lの完全29要素ベクトル](../experiments/chatgpt_topology_search/runs/EXP-053/checkpoints/split_input_shunt_center_best.json)、他2件の多様性保持回路、各3件の独立MNA、2つの原artifact SHA256（JSON `b684316bd98141ffce2f36ad5f33be256e443ca86116dce251d69db52c775338`／ZIP `499452c354f4dffc5e07e8f1d3fcbb8f0a5d526b5d6074f406bb338874a341fe`）と実行コミット。更新[RF-T007局所パレート](../data/pareto_snapshots/rf_t007_exp053_4l_20261019.json)では、観測済み14保存候補の非支配は3L面積3／3⅔／4⅓と、**新4L面積5⅓（IL0.875795）**。

ユーザー指示に従い、**H2/H3の追加減衰マージン改善および相互結合の物理実現性の検討を今回も実行していない**。数値30dBは必須条件として維持。局所・有限格子公称モデルであって大域解／連続周波数保証・SRF/Q(f)/EM/量産特性の保証ではない。正式RF-F003不変更、**Phase2継続／Phase3は承認待ち**。

## 2026-10-19：EXP-052（RF-T007／4L追加トポロジー探索・接続位置の体系的変更）

オーナーの追加指示により、**相互結合の物理実現性とH2/H3減衰マージン拡大の研究をこの実験対象から除外**し、RF-T007のH2/H3必須30dBだけを維持した4L接続探索に集中した。EXP-052をmainに事前予約し、EXP-051の4L最良面積5⅓、GJM×2/Q80・PCBパターンC×1/Q40・DTC×3/Q35（対GND DTC×1、固定寄生0.5pF/Q40×1）を比較基準に固定。チップLQP02HV×4、面積・部品個数・外部S2P・6設定・RF-T007制約は不変更。

**実行済み：** (1) 可変DTCの接続先9案×2初期値＝18最適化（18収束）、(2) 固定GJM/PCB-Cの接続先10案×2初期値＝20最適化（19収束、1未収束）。両系列の基準案が重複するため、実回路トポロジーは**18通り（既存基準1＋新規17）**、評価19設定、計38局所最適化。28区間×1001点の6設定UL/DL最悪IL・H2/H3≥30dBを評価し、各19設定の適合局所解は**独立9×9結合L枝電流MNA・84点検証PASS**。

**最良新4L**：PCBパターン固定C `Cf1` を従来の(1,2)出力L並列から、**(0,2)入力―出力ブリッジに再接続**。固定Cf0(0,1) GJM Q80、Cp(4,GND) GJM Q80、可変Cv0(4,GND)/Cv1(0,1)/Cv2(1,2) Q35とCv0固定対GND寄生0.5pF/Q40は維持。面積**5⅓**・最悪IL **0.885189326dB**、H2/H3いずれも最小約30.005dB。独立9×9 MNA最大IL差1.599e−13dB・電力収支差9.541e−18W、PASS。新接続は内部数値ガード30.005dBで同時に再最適化した旧4L接続0.888790901dBより**0.003601575dB**良好。EXP-051旧公開値0.888992895dBの内部ガード30.02dBと混同して優位を誇張しない。

試験結果証拠：[EXP-052 README](../experiments/chatgpt_topology_search/runs/EXP-052/README.md)、全19数値行および38回収束台帳、トップ3完全29パラメータ／6設定DTC、各3件の独立MNA結果、2系統のGitHub Actions原JSON SHAとソースコミット。新[RF-T007観測11点パレート](../data/pareto_snapshots/rf_t007_exp052_4l_20261019.json)では3L面積3/3⅔/4⅓と、新4L面積5⅓の計4候補が非支配。これは**公称一定Q・有限周波数格子の局所探索成果**であり、大域的な優位・実機を主張しない。

**次のPhase2研究方向（オーナー指定スコープ）**：4LそのもののL接続グラフ変更、1シャントDTCを維持した別の共振枝/可変C配線の組合せなど、**新規トポロジーとIL低減**の研究を続ける。追加のH2/H3減衰マージン最適化や相互結合物理実現性の評価を勝手に再優先しない。正式RF-F003不変更、Phase3停止。

## 2026-10-19：EXP-051（RF-T007／1シャントDTC・4L回路の新トポロジー）

オーナーの「4L構成の改善」指示を受け、EXP-051をmainに事前予約（`rft007-single-shunt-fourL-phase2-20261019`）。既存EXP-050では4L×2シャントDTCが3L解に支配されたため、**4LのままシャントDTCをCv0の1枝に削減**し、Cv1/Cv2を非接地のままとする4L分割シャントインダクタ回路を設計した。チップインダクタ4個の物理一列L0–LsA–LsB–L1、相互結合は隣接のみ|k|≤0.10。固定CはGJM Cf0/Cp(Q80)＋PCB Cf1(Q40)。選択的に追加PCB共振Ctrap Q40(3,4)を検討。Cv0の対GND固定寄生0.5pF/Q40を1枝に限定し、OFF=0pFでも存在する。全3DTC可変成分は0–3pF/Q35、チップ面積は両4L案とも5⅓。

3L保存最良（EXP-050面積4⅓ IL0.891827dB）を同一L/R/相互結合の4LシャントL二分割へ写像し、28×1001点で電気的等価性誤差最大6.395e−14dBを確認。その上で2構成×3初期値＝6回のSLSQP最適化を実行、6回すべて収束。**結果（公称、H2/H3最小値とも約30.020dB）：** Ctrapなし4L＝**IL0.888992895dB**、Ctrap 0.02pF追加4L＝IL0.889175564dB（どちらも面積5⅓）。各候補、84点の明示9×9結合L枝電流MNA・電力収支PASS。初回計算で継承した3L固有値サマリーの不一致を発見し、4×4 L行列に修正・単体回帰後に再実行した。新4Lは**同面積の旧EXP-050 4L（IL1.054412）から0.165419dB改善**。旧3L面積4⅓とのIL差0.002834dBは小さいため、公差・EM/実装で維持される保証はない。

正本：`experiments/chatgpt_topology_search/runs/EXP-051/README.md`、完全29要素ベクトル2件、設定別Cv全6件、独立MNA2件、保存マニフェストと`data/pareto_snapshots/rf_t007_exp051_4l_20261019.json`。観測したRF-T007計8候補の非支配集合は3L面積3/3⅔/4⅓および**4L面積5⅓**。ただし有限格子の局所探索であり、**H2/H3必須30dBからのマージンは約0.02dB**、L行列SPDのみ確認、2つの隣接|k|が0.1に近い同時物理実現、量産DTC寄生変動、実コンデンサQ(f)/L SRF/基板EM/高密度連続極値は**未検証**。次のPhase 2優先課題はL結合実装可能性/寄生の変動ロバスト性を重視した4L探索と、30dB制約の数値マージン拡大。正式RF-F003・旧RF-T005/T006は不変更、Phase 3停止。

## 2026-10-19：EXP-050 RF-T007／T005保存パレート6構成の逐次対応（数値実行済み）

ユーザー指示によりRF-T007追加の[PR #123](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/123)をmainへマージし、EXP-050をmain台帳へ事前予約。旧RF-T005の面積3、3⅔、4⅓、4⅔、5⅓、6の**6保存トポロジーを順番に**固定0.5pF/Q40のシャントDTC寄生込みで局所再最適化した。旧T005保存ベクトルは不変更。寄生は3L候補には1枝、EXP-042由来4L候補には2枝（Cv0,Cv1）で、非接地Cvには追加しない。

**実行済み公称RF-T007 best-found IL (dB)：** 面積3→0.938309、3⅔→0.909729、4⅓→0.891827、4⅔→1.744673（SLSQP未収束）、5⅓→1.054412、6→1.233552（近傍H2未達を追加3-startで修復）。すべて全6設定・28区間×1001点でH2/H3≥30dB、個別の84点明示7×7／9×9結合L枝電流MNAによるIL一致・受動電力収支PASS。6トポロジー・合計19局所初期値（収束12／未収束7）。**非支配は面積3、3⅔、4⅓の3L候補のみ**（観測済み6点に限る）。面積4⅔以上の今回の4L局所点は4⅓の3Lに面積/ILで支配されるが、4L一般の最適性能限界ではない。

証拠正本は[EXP-050 README](../experiments/chatgpt_topology_search/runs/EXP-050/README.md)（全6設定容量・完全L/C/kの6 JSON／独立MNA 6結果／失敗反例をSHA付きでmanifest保管）および[T007ローカルパレート](../data/pareto_snapshots/rf_t007_exp050_20261019.json)。スクリプトは[GitHub Actions各PR](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/129)で実行し、source run IDと原artifact SHAを保持した。**結果はconstant-Q/S2P基準の有限格子局所探索**であり、真の大域/連続区間の最適性・製品SRF/Q(f)・EM/公差/実測による実装保証ではない。今後の再最適化は特に2枝固定寄生による4Lの減衰/IL低下を解析する必要がある。正式RF-F003と旧試験RF-T005/T006は変更せず、Phase 2継続／Phase 3は承認待ち。

## 2026-10-19：RF-T007シャントDTC固定寄生（実行予定と保全ゲート）

所有者確認済みの新Phase 2試験RF-T007はRF-T005相当の最大3枝DTC（0～3pF/Q35）を継承し、**接地シャントDTCごとに固定0.5pF/Q40**を常時並列に追加する。EXP-042ではCv0とCv1に追加、ブリッジCv2にはなし。0.5pFのばらつきは当面評価せず公称固定値のみ。正式RF-F003および旧RF-T005/別試験T006は履歴として変更しない。

**準備した範囲：** `data/constraints/trial/RF-T007.json`、台帳登録、ローダによる明示opt-in、新規寄生枝生成・損失アドミタンスAPIと単体テスト。これらを実装したことと旧EXPソルバーへの自動反映は異なる。

**未実行・今後のゲート：** (1) branch PRをmainへ反映し回帰CI確認、(2) RF-T007で新EXP番号をmainに予約して照合PASS、(3) EXP-042を含む3L/4Lトポロジーの最適化器と独立MNA双方に固定枝を確実に挿入、(4) 6設定28区間の新条件数値最適化・高密度/独立評価、(5) 旧RF-T005との同条件比較はモデル相違を明記、(6) 周波数・温度ばらつき、SRF/EM/実測は別評価。Phase 2継続、Phase 3未承認。

# Phase 2 研究ロードマップ（現行入口：2026-10-17）

> **現在の閲覧入口：** [Phase 2現行サマリー](current/phase2_status.md) ／ [未解決課題と実施ゲート](current/open_research_questions.md) ／ [RF-F003・RF-T005パレート一覧](results/README.md) ／ [文書総合目次](README.md)。
>
> **研究Phase 2継続、Phase 3はユーザー明示承認まで停止。** 現行正式数値正本は [制約レジストリ](../data/constraints/registry.json) のRF-F003、周波数帯は [bands.csv](../data/bands.csv)。RF-T005は試験条件であり正式RF-F003へ昇格していない。
>
> **時系列の解釈：** この下には2026-10-16以前に書かれた未実装・未実行計画が歴史として残る。**2026-10-17のEXP-047局所数値探索・独立MNAを消さず、かつRF-F003共通runnerによる網羅最適化の完了ともみなさない**。過去のRF-F002成果・旧PRの状態は現在の公式実績を意味しない。

## 2026-10-18：EXP-049 RF-T006面積拡大・高Q局所探索（実行済み）

ユーザーの実用目標**最悪UL/DL IL≤1.1dB**に向けて、main事前予約済み[EXP-049](../experiments/chatgpt_topology_search/runs/EXP-049/README.md)を実行。Q25 4～7L・GJM増量では面積9⅔で**1.303473dB**、RF-F003で許されたQ33 LQW04仮定では面積19で**1.158264dB**まで改善した。ただし後者には公表製品範囲より小さい0.4nHが含まれる。公表レンジの**0.8～33nH**を条件として同じQ33モデルで再探索し、**面積18・4L/9GJM・最悪IL1.166797dB**、H2最小30.039123dB・H3最小30.040091dB・3～6GHz最小20.079968dB、114点独立MNA PASSを確認。**1.1dB目標は未達**、最小減衰余裕は小さい。部品の値の実在、Q(f)/SRF、0.005pFの極小GJM、EM/公差未確認。Phase 2継続、正式RF-F003と試験RF-T005は不変更。短命の数値実行workflowは終了後に退役してmainへ残さない。

## 2026-10-18：RF-T006試験条件の追加（条件・判定器整備、数値探索未実行）

**ユーザー指示に基づきRF-F003ベースのRF-T006を追加。** 正式RF-F003と3可変C試験RF-T005は変更せず、RF-T006は最大2可変Cのまま、全6設定・外部端子間・3.000～6.000 GHzで減衰≥20dBを必須条件とする（端点を含む1MHz格子・計18,006点）。従来UL/DL・H2/H3（最低30dB、公称35dB）は継承。試験条件は[RF-T006](../data/constraints/trial/RF-T006.json)と[レジストリ](../data/constraints/registry.json)、評価手順は[制約ガイド](../data/constraints/README.md)。**現時点は条件JSONと評価器・回帰テストの整備だけで、新EXP予約・探索・T006適合候補の取得は未実行。** 3～6 GHzの減衰要件に既存F003パレート点が適合済みだとは扱わない。Phase 2継続、Phase 3停止。

## 2026-10-18：Issue #93の追跡ファイル全体の直接参照監査（PR #97、退役なし）

[PR #97](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/97)で正本PR #91に[読み取り専用の参照監査](phase2_issue93_reference_consumer_audit_20261018.md)を追加。初回CIは[SUCCESS](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39108818212)で、1196追跡ファイルのうち1194 UTF-8ファイル（約15.9 MB）を走査し、7ファイルに名称の直接参照があった。**`scripts/`/`tests/`/`src/`等のcode/configで直接一致0**。ただし旧バイナリZIP 1件と自己監査スクリプト1件は除外し、動的・外部参照、required checks、artifact/API利用は検証していない。**PR #92・旧5workflow・元EXP-046 JSONは全件保持**。Owner個別退役承認0、Phase 2継続。

## 2026-10-18：PR #92重複workflowの個別退役（所有者承認あり・統合前の変更記録）

**2026-10-18 18:46 JSTのユーザー明示指示**により、直前に提示したPR #92由来の`.github/workflows/phase2_first_wave_retention_parity.yml` **1件のみ**の退役・削除を承認済みとして扱う。旧5件の監査workflow、EXP-046元3 JSON、その他研究原本の削除は**承認されていない**。[個別退役・元Git blob復元・残余リスク記録](phase2_issue93_pr92_retirement_20261018.md)に対象SHA・PR #91正本との違い・実行済み前提を明示。新PRで削除を提案し、CI成功・main検証後に実退役を確定する。旧job/check名、3 artifactの外部下流依存は未知のままであり、不存在は証明していない。Phase 2継続、Phase 3停止。

## 2026-10-18：PR #94・#95 main統合後の確認結果

- **正本**：[PR #91](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/91)の`phase2_bc_wave1_consolidated.yml`を[PR #94](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/94)で広域trigger被覆しmain統合。main `69247eba09a8...`の[Phase 2 regression](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39107016474)はSUCCESS。
- **main同SHA固定出典監査PASS**：[PR #95](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/95)で正本workflow自身のmain更新時のみ`push`起動を追加。マージSHA `a8cf6ee98b06a3f2ce0cee3a5e7f845dfda3d49d`の[統合監査run 39107751329](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39107751329)はSUCCESS（旧5監査＋EXP-046可逆原本）。同SHAの[全回帰run 39107751399](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39107751399)はこの記録時点では実行中。経過は[Issue #93](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/issues/93)と[正本化追補](phase2_issue93_pr91_canonical_reconciliation_20261018.md)を参照。
- **停止・削除なし**：PR #92重複CI、旧5workflow、EXP-046元3 batch JSONを保全。6 workflowの元Git blobを取得・現物一致確認。対象85文書・49workflow YAMLの静的参照調査は実施済みだが、外部artifact/check名依存、実験runや手動起動の用途は未確定。**個別退役は対象別のユーザー明示承認と別PRまで保留**。正式RF-F003・試験RF-T005を区分しPhase 2継続、Phase 3未承認。

## 2026-10-18：Issue #93／PR #91正本化と非破壊整理の着手

所有者の明示指定により、**PR #91の`phase2_bc_wave1_consolidated.yml`を第1波監査の正本とする**。[正本化・機能差・退役ゲート報告](phase2_issue93_pr91_canonical_reconciliation_20261018.md)と[8項目の対応行列](../data/repository_reviews/phase2_issue93_pr91_canonical_parity_matrix_20261018.csv)を作成し、PR #92の広域`pull_request.paths`を正本側へ追加する[非破壊PR #94](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/94)を作成。初回PR-head同一SHAで正本・比較CIはともにSUCCESS（main統合後の同SHA検証は未実施）。独立jobのcheck名とartifact名・外部依存、同一main SHAでの後継CI再検証・branch protection詳細は未解決。**重複するPR #92 workflowと旧5件、EXP-046元JSONは全件保持し、削除・停止は個別owner承認後の別PRに限定する。** Phase 2継続、Phase 3停止。

## 2026-10-18：B/C第1波の実行結果（削除・停止なし）

[旧5監査CIとEXP-046可逆集約の調査](phase2_bc_wave1_consolidation_20261018.md)を実施。旧5workflowの検査処理を[新しい共通CI](../.github/workflows/phase2_bc_wave1_consolidated.yml)で同条件実行できる見込みを確認し、EXP-046元3batch（RF-T005、10配置、計424,233報告評価、全30要素ベクトル）について34,818元bytes→11,692 bytesの可逆保存JSONを追加した。保存元は削除せず、後継CIの検証ステータス運用・trigger同等性と原本パス依存を継続審査。**原本退役承認0・変更0・Phase 2継続**。

## 2026-10-18：研究証拠の保存を守る「C寄りのB」整理方針（審査中）

ユーザー選択により、[Phase 2の段階的保管・退役方針](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/214cbb21e87d3f3e99177d4a7c9eaf741a74394b/docs/phase2_Bc_retention_and_retirement_policy_20261018.md)を**案として確定**。現行47 workflowは必須運用2・代替CIまで保持7・統合審査1・先行退役審査9・実験再実行代替後の退役審査28に分ける。元225証拠は必須原本128・数値等価性未確認81・集約審査16に分ける。最初は旧監査workflow5件とEXP-046の元中間JSON3件の**使用・出典・等価性調査のみ**進める。各元ファイルの個別削除承認はまだなく、変更・削除0件。Phase 2継続。

## 現行の管理課題（2026-10-17）

| 優先 | 論点 | 出典・次工程 |
|---|---|---|
| 対応済み／出典欠損は継続 | 元EXP-047 manifestは旧形式のまま保持。索引専用アダプターにより[PR #71の全回帰](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39028160775)は**マージ前SUCCESS** | [現行課題](current/open_research_questions.md)。元実行SHA・seed・環境は未確定。厳格manifestの完全復旧と区別 |
| 完了／旧14件の構造属性は未抽出 | 2026-10-17の旧14件＋現行10件を[24候補台帳](../data/catalog/phase2_candidate_catalog_20261017.csv)へ統合し、[W2構造検索索引](results/phase2_topology_search_20261017.md)をPR #78でmain導入 | RF-T005 6件／正式RF-F003 4件の区分を維持。旧14件は未抽出=unknown、結合の物理実装性未検証 |
| P1 | RF-F003共通探索pipeline、同条件での共通格子・独立検証、Q(f)/SRF/EM/実測・公差検証が未完了 | [RF-F003当時の計画](rf_f003_phase2_rebaseline_plan_20261016.md)、[現行課題](current/open_research_questions.md) |
| P1 | 2026-10-17のStep 1～5は[PR #71](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/71)、追加整理W0～W2は[PR #72](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/72)・[#73](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/73)・[#75](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/75)・[#78](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/78)でmain統合済み | [W3旧文書7件レビュー](phase2_cleanup_w3_document_review_20261017.md)では各固有情報を確認。所有者がD-001～004の元path削除を承認。固有情報を[歴史資料](archive/w3_consolidated_documents_20261017.md)へ統合して元4pathを削除。D-005～007・旧46件は保持 |

| P1 | W4実験証拠・旧workflowのレビュー | [W4非破壊監査](phase2_cleanup_w4_evidence_workflow_review_20261017.md)でE-001/E-002の747件とworkflow39件を実走査し、旧46件原本を保持。225件の機械索引未参照は**削除許可ではない**。[追加の実行済みW4精査](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/727de04781cf42e6a9aaa710dc33f0ab0fb78b6d/docs/phase2_cleanup_w4_forensics_20261017.md)では225件（うちJS解析ソース59件）・7源グループを個別分類し、39workflowのAPI実行履歴を確認 | [225件CSV](../data/repository_reviews/w4_unindexed_225_review_20261017.csv)／[39workflow CSV](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/045d286cf09fd45d74580d9bf6c98e7d9fcde698/data/repository_reviews/w4_workflow_runs_20261017.csv)。API可視32件に履歴あり、7件0は非使用の証明でない。元runの再現性・動的参照・代替手段と承認を追加確認するまでE/W削除0件。[2026-10-18 W4再実行依存監査](phase2_cleanup_w4_replay_dependencies_20261018.md)で225原本SHA・元manifestの参照・Python27/JS59件の構文だけを確認。EXP-042の6件の実runと10件の期限付きArtifactメタデータを保存。[EXP-042 ZIP原本バイト保全](phase2_w4_exp042_artifact_preservation_20261018.md)で10ZIP／19内部ファイルを取得、ZIPと全memberのSHA-256を紐付けて[Gitへ元ZIPのBase64バイトを保全](../data/repository_reviews/w4_exp042_actions_original_zip_b64_20261018.json)。有効期限経過後もオフライン検証可能。RF数値再実行なし。[W4 EXP-042 ZIP⇔Git checkpoint照合](phase2_w4_exp042_artifact_checkpoint_crosswalk_20261018.md)で10 ZIP／19 memberを比較し、30dB選別は一致、35dBとcf1は別stage、cf2/both/pcb_cf2の3 variant・6 memberは対応する選別済みGit checkpointパスが存在しないと確認。元ZIP・チェックポイントを共に保持。[未選別3変種の元データバイト復元・IL/面積比較](phase2_w4_exp042_missing_variant_recovery_20261018.md)で6件の元JSONを保全。cf2/both/pcb_cf2は同面積の既存RF-T005観測パレート候補より最悪ILが大きいため現行候補台帳に追加しない。保存元と既存選別元のActions run IDが別であることを35dB/cf1について確定。[EXP-046/047の131原本のSHA・訂正出典レビュー](phase2_w4_exp046_exp047_source_review_20261018.md)でRF-T005と正式RF-F003を区別し、旧46件と131原本SHA、EXP-047のQバグ除外5原本、正式RF-F003パレート4候補の元SHAを確認。**W5は読取専用の完了監査に限定**し、研究原本・workflow削除判断は未承認 |
| **監査完了判定のみ／W4退役は未完了** | **W5：Phase 2リポジトリ整理の読み取り専用総合監査（2026-10-18）** | [W5総合報告](phase2_w5_readonly_closure_20261018.md)／[14ゲート](../data/repository_reviews/w5_phase2_gate_matrix_20261018.csv)／[固定機械監査JSON](../data/repository_reviews/w5_phase2_readonly_closure_20261018.json)でW3の4件削除と3件保持、旧46・W4 225・EXP-046/047 131・旧39workflow・EXP-042 10ZIPの保全を横断検証。**研究実験・workflowの削除を承認したものではなく、W4の削除工程は未完了**。旧T-001～010は[W5後続の現況照合](phase2_w5_followup_disposition_20261018.md)で個別検査済み。Phase 2継続 |
| **文書の現況照合済み／退役承認待ち** | **W5後続：T-001～010／workflow47件／未索引元225件の分類（2026-10-18）** | [判定報告](phase2_w5_followup_disposition_20261018.md)／[T10件](../data/repository_reviews/w5_followup_T001_T010_status_20261018.csv)／[workflow47件](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/045d286cf09fd45d74580d9bf6c98e7d9fcde698/data/repository_reviews/w5_followup_workflows_47_20261018.csv)／[証拠225件](../data/repository_reviews/w5_followup_evidence_225_20261018.csv)。旧T台帳の未着手は歴史状態で、策定時から9文書が更新済み。EXP-004の古いActions Webリンクのブラウザー遷移のみ未確認。旧39＋後続8を含むPR-head47 workflowは全件保持、静的書込兆候5件の詳細点検が重要。元225件も全件保持。**研究原本／workflowの削除は0件、個別承認なし** |
---

## 2026-10-17以前の計画・進捗（時点情報として保存）


## 2026-10-17 現時点のパレート解を保存（数値探索・検証済み成果の追記）

**現行の保存済みbest-found**：[RF-T005 / RF-F003 面積–ロス・パレート比較](pareto_rf_t005_rf_f003_20261017.md)、[機械可読JSON](../data/pareto_snapshots/rf_t005_rf_f003_20261017.json)。同一制約ごとにH2/H3必須30dBの有限格子適合候補を整理し、**RF-T005 6点（面積3〜6、最悪IL 0.944268〜0.805149dB）／正式RF-F003 4点（面積4⅔〜6⅔、最悪IL 0.882647〜0.833188dB）**を記録。EXP-042/043/045/047既存の完全ベクトルと数値検証を参照。新規実験・最適化・計算の完了を宣言するものではない。各候補の公称35dB/IL≤0.30dBは未達、物理・公差・SRF/EM等は未保証。Phase 2継続、Phase 3停止。

> 下記「2026-10-16」節の「RF-F003フル最適化未実行」は**当時の状況記録**。その後のEXP-047のin-chat局所数値探索・独立MNAの実行済み事実は上記追記を優先する。ただしGitHub Actions等で全探索を再現・実行したとの意味ではない。


**RF-F003採用**：旧RF-F002から、外部固定入力寄生S2P＋LPF＋外部固定出力寄生S2Pへの外部端子総合評価、chip隣接LとPCB-L間の|k|上限0.10、IC可変C最大2枝・各0～3pF・Q35へ移行。**RF-T005**はRF-F003に対し可変Cのみ最大3枝へ拡張した承認済みPhase 2試験条件であり正式化ではない。固定寄生S2Pはハッシュ検証済みのファイルをキャッシュして利用する。Q(f)/SRF/EM/寄生抽出基準面・物理実現性およびRF-F003実LPF最適化は未検証で、旧RF-F002最良結果と比較・混用しない。試験結果・最適化実験は必ず新規EXPのmain事前予約と検証を実施してから着手。Phase 3は引き続き所有者の明示承認まで停止。

## 2026-10-16 RF-F003実行計画（新しい現行ゲート）

[RF-F003 Phase 2再ベースライン・実装・探索計画](rf_f003_phase2_rebaseline_plan_20261016.md)を現行の具体的工程とする。PR #56で新正式制約と固定入力/出力S2Pの読込・縦続接続primitiveはmainへ導入済み。ただし旧`full_lpf` optimizer/runnerはRF-F002専用であり、**RF-F003の外部端子間6設定Full-LPF最適化は未実装・未実行**。

工程は **P0 main同期/旧仕様回帰 → P1 LPF無終端2ポート化・独立寄生込み検証 → P2 RF-F003専用solver/runner → P3 mainでEXP番号予約後の旧候補新条件再ベースライン → P4小規模二重BSF探索 → P5物理モデル不確かさの評価**。新runの番号は最新mainに予約・事後照合PASSまで未割当とし、旧EXP-017/F002 IL値は新仕様の達成値へ流用しない。RF-T005（3可変C）は正式RF-F003（2可変C）と別の試験結果にする。S1 100グラフ以上は今回未承認・未実行、Phase 3も未承認・停止。

---

## 2026-10-15以前の状況（RF-F002の履歴）

# Phase 2 現行状況 — 2026-10-15 (JST) / main e069c70fd（PR #53統合後）＋RF-F002 EXP-017原データ回収追補PR

> この節が現時点の開発状況の入口です。以下の2026-10-10～14の日付付き段落は**当時の計画・数値・PR状態の履歴**として保持しており、現在の未マージ状態や現行RF制約の宣言ではありません。現行数値制約は data/constraints/registry.json の正式 RF-F002、帯域は data/bands.csv。Phase 3は所有者の明示承認まで停止。

## 次回新規実験の必須開始ゲート（PR #53統合済み）

- **EXP番号は開始前にmainへ予約する。** [中央台帳と並列予約設計](experiment_number_reservation_policy_20261015.md)を参照。過去39実験と歴史的欠番EXP-018/019を保護し、次番号候補は**EXP-042（未予約）**。
- GitHub Actionsから予約をmainのGit履歴へ非force pushで確定し、最新版mainを再取得してから実験を開始。重複pushは再採番、branch protectionで拒否された場合は予約用PRをmainへ反映するまで開始禁止。
- **予約台帳・workflowはPR #53でmainへ統合済み**。ただし手動予約workflowの本番実行は未検証。EXP-042は未予約。Phase 2継続。

## mainへ統合済みの作業と検査

- [PR #48](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/48)（2026-10-14にmerge）：EXP-034～041のRF-F002 Full-LPF runner復旧・継続試験。元のremap不備があるrunと後続の修正runを区別する。
- [PR #49](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/49)：Phase 2成果候補と未解決課題の基本登録。
- [PR #50](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/50)：全39実験の証拠インベントリ、36件の補助証拠参照、EXP-016の試験RF-T004候補4件の事後CI再計算。
- [PR #51](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/51)：535ファイルの保全区分、13候補/8条件群の暫定面積–IL ParetoをCI生成。
- [PR #52](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/52)：要レビュー46ファイルの根拠台帳（参照あり32、同一内容の別パスのみ9、元PR説明README5）、元PR #38の17ファイルSHA256照合、R1復旧ZIPのCRC確認。**元資料の削除・移動は0件**。
- main ad1cda8cの[Phase 2 regression](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38651724459)：**PASS**。検査は保存証拠の完全な再現性やRF物理実装を保証するものではない。

## 現行のRF数値評価（EXP-017の14件目を追補するPR）

| 条件 | 台帳内の最小worst IL | 区分と限界 |
|---|---:|---|
| RF-F002正式 30dB | **0.301248245 dB** | **回収したEXP-017正式2可変C・strict_finite_grid**。独立9×9MNAで7001点/区間を検証。**IL 0.30dB未達** |
| RF-F002正式 35dB | 0.378797914 dB | strict_finite_grid（保存候補） |
| RF-F002正式 30dB | 0.318693189 dB | tolerance_only。H2/H3生値は30dBを微小に下回る |
| RF-T004試験 35dB | 0.297114032 dB | 3可変C、strict_finite_grid。**正式RF-F002の達成ではない** |

上記は選別台帳内の値であり全合法回路の大域最適性、同一格子比較、連続帯域・EM・Q(f)/SRF・製造公差の検証を主張しない。**正式RF-F002に対するIL≤0.30dBのstrict達成候補は未登録**。S1の100 graph/start大規模探索は未開始。

## 重要な未解決ゲート

1. **RG-001／欠落ベクトル回収・独立有限格子追試済み:** 元正式RF-F002 ZIPを回収し、EXP-017の0.301248245dB・30dBの**完全23要素ベクトルと6設定Cv**を新ファイルへ記録。9×9独立MNAの7,001点×28区間で元値を再現、K SPD・電力保存PASS。[追補・元ソースの区別](phase2_exp017_checkpoint_provenance_review_20261015.md)を参照。IL目標と実装物理検証は**未達／未実行**、元ZIP全体のGit原本保存と全453最適化試行の再実行は**未実施**。
2. **P0 / RG-003:** EXP-034～037の旧warm-start端子remap不備を修正後の成果と混同しない。実行基盤性能と回路性能を分離する。
3. **P1 / RG-004・RG-008:** 統合候補台帳は回収した正式候補を加えて14件（本追補PR反映時）の選別結果であり全成果網羅ではない。EXP-016/017/021/022/023/024の元manifestのevidence登録は0件（遡及改変せず補助索引あり）。
4. **P1 / RG-005・RG-007:** **外部アーカイブは使用しない（ユーザー指示）**。現行main 731ファイル/約8.45MB。新規実験の完全候補と再現用最小証拠をGitHubへ保存し、全iterationログは原則保管しない[Git-only保存方針案](experiment_result_storage_policy_proposal_20261015.md)へ変更した。旧6ブランチの先端監査・一時Git bundle復元PASSだが、ブランチ削除は**承認とGitHub内archive ref保全**まで保留。RF-T004小容量ZIPは35member SHA登録済み・**元バイナリGit未収録**。[保管最適化監査](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/12b1dfd7a91ab466a6cfbbb8b4db968715e91d5f/docs/phase2_repository_optimization_review_20261015.md)を参照。
5. **P1:** 候補間の周波数格子・独立MNAの共通条件での再比較、元試行環境・seedの再現性確認、物理SRF/寄生/EM・温度公差。新規解析を実行した場合は別検証記録として出典を固定する。

現在の課題ステータスは [研究レビュー台帳](../data/research_review_issues.csv)、候補区分は [研究候補台帳](../data/research_candidate_register.csv)、全39実験は [証拠インベントリ](../data/experiment_evidence_inventory.csv) を参照。

---

## 以下は過去時点の記録（現行ステータスではない）

**2026-10-14 現行作業状態（RF-F002 Full-LPF runner recovery/refinement）。** PR #47は最新`origin/main` `eb1de13841c1b4a74f18f4f9320e0316fbdd478f`に含まれる。追試branch `test/rf-f002-full-lpf-recovery-20261014` はレビュー用で、mainへ未merge。EXP-034～041でlive manager/worker停止・再開、1/2 worker、正規checkpoint warm-start、scaled/unscaled/FTOL、9→17 gridを記録。正しくremapしたEXP-041 30dB stageはIL 0.318693189dB（生H2/H3は30dBを約3e-9dB下回り、1e-5 tolerance内）、35dB stageは0.378349100dB。どちらもIL≤0.30dB未達、30dB点は実質余裕なし。**S1 100 graph searchを開始せず、Phase 2継続、Phase 3停止、RF-F002不変。** bounded evidenceとS1/S2/S3予算は[Phase 2追試報告](rf_f002_full_lpf_phase2_20261013.md)を参照。有限grid/MNAのみで連続band・物理性能証明ではない。

**2026-10-14：RF-T004・EXP-021（既存EXP-020との対比）。** [実験記録](../experiments/chatgpt_topology_search/runs/EXP-021/README.md) に文献着想の4L固定橋絡＋最大3可変Cの再合成、合法範囲の隣接磁気結合|k|≤0.15、LQW04 Q33置換、GJM固定C増設の有限探索を記録。7001点／各CSV周波数区間と84点独立枝電流MNAで、公称30dB条件4HV・面積8のIL=**0.393327dB**、公称35dB条件4HV・面積8のIL=**0.447944dB**を確認。4×LQW04（Q33仮定・SRF未確認・面積16）は30dBで0.310621dB／35dBで0.348604dB。いずれも0.30dB未達であり**EXP-021限定**の結果。重要：既存[EXP-020](../experiments/chatgpt_topology_search/runs/EXP-020/README.md)にはRF-T004・35dB・IL=**0.297114dB**／面積13⅔の独立再検証済み公称数値解があるため、これをプロジェクトの先行基準として保つ。今回の結合上限0.15は複数ペア同時実装未証明、全Q33候補はSRF/Q(f)/物理寄生未検証。比較条件の混同を避け、Phase 2継続／Phase 3停止。

**2026-10-14：RF-T004試験探索 EXP-016（Phase 2）。** [実験記録](../experiments/chatgpt_topology_search/runs/EXP-016/README.md) に文献着想による22種の有限トポロジー探索と局所最適化・独立枝電流MNA（21点/候補）・各帯域2,001点/区間の再評価を記録。RF-T004（RF-F002ベース、可変C最大3枝、各0～1.5pF/Q50、その他は正式条件のまま）で、30dB必須条件のbest-foundは面積4⅔・最悪IL=**0.480214dB**（PCBパターンC×2）、35dB公称条件のbest-foundは面積4⅔・最悪IL=**0.596216dB**（固定トラップCのみ）。3L＋1固定Cの小型候補では面積3⅔・30dB時0.497264dB／35dB時0.630323dB。**いずれもIL≤0.30dB未達。** 候補は試験版の数値照合であり、数学的連続極値保証、Q(f)/SRF/EM/寄生、実レイアウト、WSL2 uv lockによる再実行、解決済みtrial条件ハッシュは未完了。正式RF-F002の最良候補へは昇格させない。これにより本ファイルの旧「RF-F002下のLPF性能最適化は未実行」の記述をRF-T004試験結果へ拡張解釈しない。Phase 2維持、Phase 3停止。\n\n**2026-10-13：現行正式RF-F002、試験RF-T004を承認・登録。** 結合／PCB-L／可変C容量・Q・配置／LQW04 Qを改訂。Phase 2の制約台帳、互換JSON、旧RF-F001再現、基礎結合検証、およびP4-Aの可変C配置列挙を更新。回帰CI [run 38410571500](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38410571500) はPASS。RF-F002下のLPF性能最適化や達成値の独立確認は**未実行**。残作業は制約適用範囲の監査、候補探索、各6設定の全帯域高密度検証、独立MNA・電力収支・SPD・実装性確認。以下のRF-F001「現行」記載は記録当時のもの。Phase 3移行は未承認。

# Phase 2 ロードマップ（現行版）

**2026-10-12 RF-F001の正式方針更新：** チップ面積コストのハード上限を廃止し、6設定UL/DL最悪ILとのパレート評価軸とする。以下にある「hard cap6」「面積最大6」は過去の探索条件・旧実験予算の記録であり現行正式RF制約を表さない。当時の有限探索範囲と正式RF制約は区別する。旧候補の実測/数値記録は不変更。詳細は[制約版管理](../data/constraints/README.md)。

## 2026-10-14 Phase 2 / Full-LPF 追試状況

PR #47（Full-LPF runner統合）は`origin/main`の`eb1de13841c1b4a74f18f4f9320e0316fbdd478f`に含まれる。追試branch `test/rf-f002-full-lpf-recovery-20261014` は[PR #48](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/48)としてレビュー中で、EXP-034～041を事前登録・記録。live SIGINT/SIGTERM/lock/resume/hash拒否、4-task 1/2-worker比較、checkpoint terminal remapping、warm/multi-start、9→17 grid refinement、scaled/unscaled/FTOL比較を実行した。詳細は[Phase 2 Full-LPF追試報告](rf_f002_full_lpf_phase2_20261013.md)と各manifestを参照。

正規importされたEXP-017 warm-startの30dB stageはIL 0.318693189 dB（H2/H3生値29.999999997/29.999999999 dB、1e-5 tolerance内）、35dB stageはIL 0.378349100 dB。1001点/segment有限確認で数値一致したが、IL≤0.30dB未達、30dB点のraw marginは実質ゼロ。scaled条件は35dBで収束し、unscaledは低IL/低marginのtradeoff。よってPhase 2継続、S1（100 start）未開始、Phase 3停止、正式RF-F002不変。最新実測start時間96.7–145.0 worker秒を単純外挿したS1は1 worker 2.7–4.0h。2-workerの1.6–2.3hは短いEXP-035倍率を仮置きしただけで、長時間correctly-mapped throughputは未確認。

## 当面の目標

**LPF-007を上回る現行仕様の`full_lpf`回路を発見する。** LPF-007の保存済み有限グリッド値は6設定UL/DL最悪IL=0.513168414 dB、H2/H3最小約35.07 dB、面積6。最適化未収束・EM未検証。EXP-038/039のcorrectly mapped warm-startは35dB within 1e-5 toleranceでIL 0.378349100 dBまで改善。EXP-041の30dB boundary stageはIL 0.318693189 dBだが、raw H2/H3は30dBを約3e-9 dB下回り、35dB nominalを満たさない。**どちらもIL≤0.30dB未達**であり、現時点で受け入れ済み目標候補ではない。新候補は同じ制約・同じ帯域で再評価し、35dB公称性能または明示した30dB tradeoffとresidualを個別に報告する。

## 開発順序

| ゲート | 作業と実測による完了条件 | 状態 |
|---|---|---|
| **G1** | GitHub Actionsの決定的分割・Artifact保存／別run復元・再開・集計。1/2シャードの実機smoke。 | **完了**（main `35642be3`、[2シャード最終run](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38128871403)）。 |
| **R0/R1** | LPF-007/008を汎用MNAで同値再現する回帰テスト。任意内部ノードへの対GND可変C配置を許す共通回路表現。既存G1との互換性テスト。 | **一部完了**：LPF-007/008の基準値固定回帰とG1再開スモークPASS。内部可変C位置の一般化は未完了。 |
| **G2** | MNAの実測profiling・高速化、SLSQP／epigraph minimax／多初期値・継続法。時間、収束率、評価回数、ILを同条件で比較。 | **部分完了**：bounded Full-LPF runnerの実process recovery、scaled/unscaled、FTOL、warm/multistart、9→17 gridをEXP-034～041で実測。IL≤0.30dB候補は未発見。 |
| **E2** | ChatGPT発案の専用ソルバと汎用グラフ探索の両トラックで`full_lpf`最適化。LPF-007を上回る有望解の独立検証。 | **部分完了**：既存4L/2C warm-startの有限局所最適化は実施。目標IL≤0.30dB達成なし、全合法graph探索でもない。 |
| **V1** | 6設定UL/DL・UL H2/H3の高密度周波数評価、独立式、SPD、電力収支、物理配置、部品・公差の確認。未解決項目を列記。 | **数値のみ部分完了**：EXP-041を1001点/segment・独立MNAで確認。連続band proof、SRF/Q(f)/parasitic/EM/tolerance/physical implementationは未実施。 |

## PR #10再編成後の検証記録（2026-10-11）

- 回帰CI：[実行38139630762](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38139630762) **PASS**。89ユニットテスト、監査、LPF-007/008の保存済みIL/H2/H3との数値照合、Q・可変C制約、代表点独立MNAと電力収支を実行。matching-only既知回路の解析解回帰を追加。新しいLPF回路の最適化はしていない。
- G1新構成スモーク：[実行38139630751](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38139630751)、ソースコミット `fe322ea204b5ff232150da0902cead2923980205` で **PASS**。GitHub-hosted Ubuntuの3ジョブで、1シャード・3サンプリンググラフを1件ずつ計算。Artifactを2回復元し、最終チェックポイントは`completed`、残り0件、`resume_count=2`。既存のG1集計器が`overall_complete=true`、`optimized_graphs=3`、欠落0件・エラー0件を報告。
- このスモークの条件は各グラフ1初期値・1最適化反復、粗い通過帯域2点/セグメント、検証3点/セグメント。**数値精度・高調波減衰・P4-Aの探索網羅率・新性能の証明ではない**。修正後もPhase 2のまま、Phase 3は未承認。
- PR #10では設計仕様文書への参照先等が変わり、以前のG1チェックポイントとは設定ハッシュが異なる。**旧Artifactを互換とみなして復元しない**。計算条件のソース指紋が一致する新runだけ再開可能。スモーク後にワークフローを手動専用の[再利用可能な検証手順](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/lpf-p4-a-smoke.yml)へ整理した（計算ソース・RF数値制約は不変更）。

**ChatGPT主導の新トポロジー考案は上記ゲートに並行して継続**する。良好解を体系探索の初期値に、体系探索の良好グラフを専用最適化の対象にする。

## 2026-10-11 PCBパターン固定Cの設計条件追加\n\nPCBパターン固定C（Q40、0.02≤C≤0.2pF、最大3個、チップ面積0）を新しい探索素子クラスとして受け入れた。まずPCB-Lなしの既存LPF-007/008に対する寄生依存・損失感度を評価し、次に固定GJM01との置換・併用を比較する。容量上限0.2pFを厳守し、数値探索の範囲設定でも遵守する。計算ジョブで有限の数値探索範囲を選ぶ際は、設計上の上限と区別して明記する。**既存P4-Aの実行は自動で探索クラスを広げず**、新種別を有効化する探索ジョブの対象数・計算時間を事前に評価する。\n\n## 旧4可変C設計から学ぶ新トポロジーの優先事項（2026-10-11）

[EXP-003制約比較](../experiments/chatgpt_topology_search/runs/EXP-003/README.md)を確認。旧CP07の0.328924dBは4本のCを6設定ごとに個別連続変更（うち3本は非対GND）できた理論解で現行制約を満たさない。旧回路の4可変Cを維持して結合だけ現行一列・隣接ルールへ再最適化すると、有限局所探索で0.337660dBの成立解が出た（未収束、実レイアウト未検証）。現行A7-01は0.508389dB。次に優先するのは、チップ部品追加だけでなく、**2本の対GND可変Cで複数の高調波伝送零点を動かす結合共振型**を発想・列挙すること。旧4可変Cの位置自由度を勝手に承認済み条件として復元しない。

## Phase 2の中間性能ゲート：IL≤0.40dB（2026-10-11）

[EXP-004探索レポート](../experiments/chatgpt_topology_search/runs/EXP-004/README.md)に、6設定のIL≤0.40dB・公称H2/H3≥35dBを中間目標として設定。保存済みコスト7基準はA7-01の0.508389dB。3直列LC・2シャントLC・5チップLの有限局所探索98件では更新解未発見、42組合せ未完了。高速周波数方向一括MNAのA7-01基準照合と101ユニットテストは成功。コスト7は別の実験予算であり、承認済みhard cap6はそのまま保持する。

次は[手動4シャードGitHub Actions](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/lpf-target040.yml)を使って、複数初期値・十分な反復・失敗を含む進捗記録を確保する。新しい最良解は高密度の6設定全帯域・独立MNA・電力保存・SPD・面積で再確認するまで基準へ昇格させない。なおスクリプトやワークフロー追加を計算完了とはみなさず、実行済みArtifactを根拠とする。目標0.30dBとPhase 3停止は変更しない。

## EXP-005：コスト7ベンチマーク更新（2026-10-12）

[EXP-005](../experiments/chatgpt_topology_search/runs/EXP-005/README.md) で、新規局所最適化132回（PCBパターンC追加24、GJM/PCB-C置換36、5L＋3GJM・3直列2シャント72）と、既存A7-01の制約付きminimax精密化を実施した。追加回路族では0.508389dBを更新できなかったが、再精密化によって**0.507331dB、H2/H3最低35.02dB**の[A7-03](../experiments/chatgpt_topology_search/runs/EXP-005/A7-03.json)を発見した。現行の35dB公称減衰下で0.40dB目標には未達。未収束の局所解をトポロジー限界とせず、未探索の2・3PCB-C、多初期値継続法、2つの可変Cが複数伝送零点に作用する新構造を優先する。正式面積hard cap6とPhase 3停止は変更しない。

## 2026-10-12 EXP-006：2可変対GND Cによる伝送零点制御を重点化

[EXP-006](../experiments/chatgpt_topology_search/runs/EXP-006/README.md)にて、コスト7の既存A7-03のSLSQP制約境界再最適化でIL **0.506951dB**を発見。H2/H3最小減衰は約35.002dBで、公称仕様には成立するが余裕極小。独立MNA54点・SPD・エネルギー収支と高密度周波数メッシュで検証。さらにPCBパターンC×2の30配置、×3の12配置、5LQP02+3GJM01の56配置を各少数初期値でスクリーニングしたが、最良数値を更新せず。**有限探索であり物理的性能限界ではない。**

従来回路族の単純追加より、旧CP07の伝送零点を現行の2つの対GND可変Cで連動させる新トポロジー設計を優先する。モード電圧に基づく2制御C対複数零点の感度、適応的周波数格子、独立検証を導入し、GitHub Actionsで多初期値・checkpoint付き大規模ジョブへ移行する。新しい数値候補A7-04と、公称減衰余裕の比較用A7-03は両方保持。正式hard cap6・Phase3停止は変更しない。

## EXP-007：単一枝再配置の限界と次の重点（2026-10-12）

[EXP-007](../experiments/chatgpt_topology_search/runs/EXP-007/README.md)で固定GJM01接続変更44、チップL接続変更44、PCB-L1本追加15の**103局所最適化**を実施。各31点/区間の35dB粗グリッドを満たす解は19+20+5=44件。GJM-C枝変更の最良は0.524581dB（7,001点／区間・54独立MNA点で確認）で、コスト7の[A7-04](../experiments/chatgpt_topology_search/runs/EXP-006/A7-04.json) 0.506951dBを更新せず。A7-04の2可変C→H2/H3局所最小減衰の感度行列ではB71の条件数≈9.36と制御感度の偏りが確認された。単一枝の置換が悪かったことを新トポロジーの理論的下界と解釈しない。次は**複数枝の同時再合成、共振零点の感度行列を考慮した構造的枝刈り、継続初期値を使う多初期値GitHub Actions探索**へ重点化する。Phase 3停止・正式hard cap6維持。

## 技術的な優先事項

1. トポロジー探索の可変C配置を一般化し、LPF-007/008の内部シャントLCを共通モデルで評価できるようにする。
2. `src/lpf/`の共通解析／最適化APIを、既存テストとG1再開互換を確認しながら整備する。実験固有コードは`experiments/`に残す。
3. 粗い最適化、精密最適化、独立検証を分離する。未収束を性能限界と解釈しない。
4. 自動探索の「網羅」は宣言した有限グラフクラスに限定し、連続素子値の大域最適性と混同しない。

Phase 2の最終結果は、同条件で比較できる候補群・コスト別性能・探索範囲・未確認物理項目・再現条件を揃えて報告する。**Phase 3へは自動移行しない。Phase 4以降の旧計画は採用しない。**
