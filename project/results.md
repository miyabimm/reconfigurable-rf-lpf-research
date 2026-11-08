# RF-LPFの保存結果と検証証拠

数値原本は[実験索引](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/data/experiment_index.csv)と各EXPのmanifest・候補・検証記録です。有限格子のbest-foundを大域最適性、連続帯域保証、実装性能の保証とは扱いません。正式／試験／旧条件、`matching_only`／`full_lpf`、bare LPF／外部ポートを混ぜず、実効制約SHA・格子・検証深度が同じ候補だけを比較します。

| RF条件 | 保存証拠への入口 | 注意 |
|---|---|---|
| **RF-F003（正式）** | [EXP-047](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/main/experiments/chatgpt_topology_search/runs/EXP-047) | 正式2可変C、2026-10-17固定パレート4件は当時の記録 |
| **RF-T005（試験）** | [EXP-042](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/main/experiments/chatgpt_topology_search/runs/EXP-042)、同階層EXP-043/045 | 最大3可変C、固定パレート6件 |
| **RF-T006/T007（試験）** | [EXP-048](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/main/experiments/chatgpt_topology_search/runs/EXP-048)、同階層EXP-049/055 | 追加阻止帯・固定寄生モデルを区別 |
| **RF-T008 v3（試験）** | [EXP-058](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/main/experiments/chatgpt_topology_search/runs/EXP-058)、同階層EXP-062〜068 | IC固定C＋最大2可変C、各EXPの収束・独立MNAを個別確認 |

[旧RF-T005/F003パレートJSON](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/data/pareto_snapshots/rf_t005_rf_f003_20261017.json)と[固定24候補CSV](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/data/catalog/phase2_candidate_catalog_20261017.csv)は現行最良一覧ではありません。4GJM候補の原検証JSONの面積6は、固定カタログでは**6⅔**へ訂正（原本不変）。最低必須30dB、公称35dB、IL目標0.30dBは別判定です。Q(f)・SRF・EM・公差・実測は未保証。[ロードマップ](roadmap.md)／[手法・解釈](methods.md)。

## RF-T008 v3の横断比較（2026-10-20の固定履歴）

EXP-062〜065の264試行（249収束・15非収束）、全6設定・28区間×1,001点の記録です。後続EXPを含む最新値への更新でも正式RF-F003への昇格でもありません。

| chip面積 | worst IL dB | 出典 |
|---:|---:|---|
| 3 / 3⅔ / 4⅓ | 1.010350255 / 0.934027580 / 0.928118761 | EXP-058。EXP-063は24/24両段階収束、固定3L配置で更新なし |
| 4 | 0.929126781 | EXP-064、4L/0GJM・PCB-C配置 |
| 5⅓ | 0.829711540 | EXP-065で更新（EXP-062時点0.833505430） |
| 6 | 0.827841148 | EXP-062、4L/3GJM |

選別10解の部品・SPD・既存MNA記録を照合したレビューであり、レビュー自体が全28区間を独立RF解法で再計算したものではありません。[統合スナップショット](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/data/pareto_snapshots/rf_t008_exp062_065_integrated_20261020.json)と[逐語レビュー原文](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/3370ea4/docs/results/rf_t008_pr148_151_independent_review_20261020.md)を参照。EXP-058のrunning/preservedとreadbackの区別を後日のレビューで遡及変更しません。

## 旧RF-F001/T003・R2の成果と限界

以下は旧一定Q・旧可変C範囲・強結合モデルの履歴で、現行RF制約へ持ち越しません。各候補の全L/C/kと6設定Cvは[保存validation](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/main/data/validation)、探索の試行数・中断・未実行範囲は[整理前の逐語文書](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/3370ea4/docs)にあります。新たなRF再計算は行っていません。

- **EXP-015/R2**：[固定監査JSON](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/r2/EXP015_COMMON_MODEL_AUDIT.json)は4候補を7,001点/区間で再現（保存メトリック差0）、各72点の3方式照合で最大利得差3.17e−15、電力残差3.36e−17W。旧3CのHV/HQ候補はRF-T002接続条件に適合、2C候補はF001/T001/T002いずれも不適合。全4件30dBを満たすが35dB・IL0.30dBは未達。API移管計画と実装済みを混同しない。
- **EXP-016旧F001探索**：GJM Q80とPCB-C Q40は別部品。元217探索・追補の実行環境と完全ログは不明。初期報告を後のRF-T004正式検証と読み替えない（下記の事後追試を区別）。
- **EXP-017旧2C統合比較**：共通シャントノード、片側シャント固定化、固定Cでの共振枝結合は別グラフ。35.005dB探索を後日承認された30dBのRF-T003成果へ再分類しない。非GND橋絡Cvは固定L並列であり主経路直列ではない。

RF-T003は旧F001基準（effective SHA256 `e0c45f7094ced1ed2ccb91cae474c7c3c1a6af73a495a2a9cf8f512ccb45ab08`）、1対GND＋1非GND橋絡Cv、各0〜4pF/Q80、隣接|k|≤0.4の**試験**です。下表の主要選抜解は28個別区間×7,001点＋84代表点独立枝電流MNA、SPD・電力の元検証記録を持ちます。全探索試行がこの深度で検証済みという意味ではありません。

| 系列／チップ費 | 保存時の最悪IL dB・最小減衰 | 元JSON（data/validation/以下）と解釈 |
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

- **EXP-017 0.301248245dBは30dB点、35dB点ではない。** 当初RG-001 openだった完全ベクトルは後日回収済み。旧「未回収」を現在の結論にしない。[回収追試](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/data/validation/exp017_rf_f002_recovered_20261015/summary.json)はIL0.3012482451489075、H2 30.004999999986865、H3 30.004641701571376dB、電力残差1.8214596497756474e−17W。IL目標は未達。
- 原ZIPの26member目録は[整理前の固定履歴](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/c2143b0f9322f0a16f2eb39073ed243a8d0e4b51/data/exp017_rf_f002_source_zip_index_20261015.json)。元2,959B候補は`EXP-017/EXP017-LQW4-H30-NEAR.original.json`、SHA256 `fa997fb131a1237c41ec8a42ead80e40fe2436275a7e944837afecea9c387896`。`.recovered.json`は正規化表現でバイト原本ではない。ZIP本体と残り25memberはGit未収録、453局所試行の再最適化はしていない。
- 別の`RF-T004-EXP017-bundle.zip`（118,646B、SHA256 `48175d3579d3814e5d3740858ee3959b88e9731b835cb2cd306ce6b0093ae640`）は**RF-T004試験**の証拠。14,001点のIL `0.2999624819232782` をRF-F002欠落ベクトルと取り違えない。元ZIPはGit未収録。
- **EXP-016 READMEの完了主張とmanifestのunknown/not_runは時点が違う**。後日の4保存候補の7,001点/区間＋84点独立MNA追試は`data/validation/exp016_ci_replay_20261014.json`と`data/validation/exp016_rf_t004_numpy2_replay_20261014/summary.json`に別保存。CI 38587242196、commit `90c87551c4720441ba7120f1457ea318c752dc34`、RF-T004 effective SHA `c66302a281a1fdb88da355fc44dac1ef3b1c4e18e8ff297db9e842b219b5b0c4`。保存ベクトルの数値再現であって、初回探索・環境・事前登録の遡及証明ではない。
- **EXP-034〜037のwarm-start端子remap誤り**：manager停止・lock/resume・改変拒否の元ライフサイクル試験とその保存summaryは、誤remapのoptimizer値が保存候補の再評価であることを意味しない。EXP-034はSIGINT後max_attempts=1でpartial、SIGTERM後は実行中workerが終了するまでresumeを拒否してから結果を採用。EXP-036はmax_attempts=2で再開後completed。いずれも2 startの限定検査でRF性能の結論ではない。EXP-035の旧benchmarkは1 worker 347.126秒、2 worker 201.347秒だが全出力非収束・端子remap誤りのため候補品質比較ではない。訂正済みEXP-038/039の35dBは1e−5dB tolerance内、strictと同一でない。EXP-040 unscaledは非収束でも30dB residualがtolerance内で、収束とは別判定。旧runnerの一時ログ・lockは#359で削減し、元manifestは不変。過去のライフサイクル結果を今回再実行したわけではない。
- EXP-041の30dB点IL0.3186931893、35dB点0.3783490996は共にtoleranceのみ、IL未達。matching-only速度からfull-LPFの予算／大域限界を推定しない。旧100 graph S1/S2/S3は報告時未開始。旧F002の小規模5 startや4task runner smokeを完全トポロジー網羅と扱わない。

### EXP-042、046/047の原本と訂正

- EXP-042の[元10 ZIP](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/data/repository_reviews/w4_exp042_actions_original_zip_b64_20261018.json)は26,953B・19memberをSHA/CRC付きで保存。既存Gitとのバイト一致は空stderr 1件だけ。ZIPハッシュ確認は数値独立再計算ではない。`target_35.json`の元run38999677194と選別run38774357292、`area_cf1.json`の38999677183と38775558755は**別Actions run**。単なる同run内stage差と断定しない。
- 未選別`cf2/both/pcb_cf2`の6元JSON（23,460B）は`data/repository_reviews/w4_exp042_recovered_original_members_20261018/`にバイト同一で保存。存在しない3つの選別checkpointを生成しない。元報告は1,001点＋84点MNA、暫定IL0.8dB未達、既存同面積よりILが悪くIL/面積の新パレート根拠なし。調波余裕等も含む全面的劣位や独立再検証済みを意味しない。
- EXP-046の初期「全て30dB未達」と後続別4Lの一部達成は別時点。容量損失会計の訂正版は`independent_verified_1001_corrected.json`。旧容量診断を引用せず、訂正前後を保持する（保存説明ではIL/H2/H3非影響）。dirty実行・seed/environment欠損を捏造しない。
- EXP-047のQインデックス誤りは`Q[5]=80`ではなく正しいGJMの`Q[1]=80`。元manifestの`q_bug_excluded_files`の5原本は正式性能順位から除外。manifest上6検証候補とパレート採録4候補を区別。optimizer commit/seed/environmentはunknown、Actionsでの元探索再実行証明はない。

## 文書統合と固定監査の読み方（Issue #352）

研究解釈は本ページと[methods](methods.md)、現役実装とゲートは[roadmap](roadmap.md)、運用は変更しない[instructions](../project/instructions.md)へ集約しました。W3/W4/W5の当時の監査完了・CI成功は、原研究の数値再実行、重要証拠の削除許可、研究Phase移行ではありません。225件、131件、46件の台帳は重複し得る別集合で、単純合算しません。旧39/31/3 workflow数や「未merge」は各報告時点の意味で、現役状態ではありません。

[W3統合文書](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/archive/w3_consolidated_documents_20261017.md)は当時のD-001〜004の出典・承認を記録する。元EXPや残存する[レビュー証拠](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/main/data/repository_reviews)は原blob・選別・終了状態・訂正の根拠です。時点固定のW4/W5保全一覧は[整理前tree](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/c2143b0f9322f0a16f2eb39073ed243a8d0e4b51/data/repository_reviews)にあり、数値再検証ではありません。削除した日付別文書の逐語内容と試行内訳は[整理前tree](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/3370ea4/docs)、元pathごとの処置・残置callerは[PR #353](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/353)に記録します。復元専用機能・新アーカイブは追加しません。

Phase 2継続、Phase 3未承認。この整理で新しい科学的結論、RF条件、原EXPの実行／検証状態を変更しません。
