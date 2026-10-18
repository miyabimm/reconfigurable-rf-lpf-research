# Phase 2 研究ロードマップ（現行入口：2026-10-17）

> **現在の閲覧入口：** [Phase 2現行サマリー](current/phase2_status.md) ／ [未解決課題と実施ゲート](current/open_research_questions.md) ／ [RF-F003・RF-T005パレート一覧](results/README.md) ／ [文書総合目次](README.md)。
>
> **研究Phase 2継続、Phase 3はユーザー明示承認まで停止。** 現行正式数値正本は [制約レジストリ](../data/constraints/registry.json) のRF-F003、周波数帯は [bands.csv](../data/bands.csv)。RF-T005は試験条件であり正式RF-F003へ昇格していない。
>
> **時系列の解釈：** この下には2026-10-16以前に書かれた未実装・未実行計画が歴史として残る。**2026-10-17のEXP-047局所数値探索・独立MNAを消さず、かつRF-F003共通runnerによる網羅最適化の完了ともみなさない**。過去のRF-F002成果・旧PRの状態は現在の公式実績を意味しない。

## 2026-10-18：PR #94・#95 main統合後の確認結果

- **正本**：[PR #91](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/91)の`phase2_bc_wave1_consolidated.yml`を[PR #94](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/94)で広域trigger被覆しmain統合。main `69247eba09a8...`の[Phase 2 regression](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39107016474)はSUCCESS。
- **main同SHA固定出典監査PASS**：[PR #95](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/95)で正本workflow自身のmain更新時のみ`push`起動を追加。マージSHA `a8cf6ee98b06a3f2ce0cee3a5e7f845dfda3d49d`の[統合監査run 39107751329](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39107751329)はSUCCESS（旧5監査＋EXP-046可逆原本）。同SHAの[全回帰run 39107751399](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39107751399)はこの記録時点では実行中。経過は[Issue #93](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/issues/93)と[正本化追補](phase2_issue93_pr91_canonical_reconciliation_20261018.md)を参照。
- **停止・削除なし**：PR #92重複CI、旧5workflow、EXP-046元3 batch JSONを保全。6 workflowの元Git blobを取得・現物一致確認。対象85文書・49workflow YAMLの静的参照調査は実施済みだが、外部artifact/check名依存、実験runや手動起動の用途は未確定。**個別退役は対象別のユーザー明示承認と別PRまで保留**。正式RF-F003・試験RF-T005を区分しPhase 2継続、Phase 3未承認。

## 2026-10-18：Issue #93／PR #91正本化と非破壊整理の着手

所有者の明示指定により、**PR #91の`phase2_bc_wave1_consolidated.yml`を第1波監査の正本とする**。[正本化・機能差・退役ゲート報告](phase2_issue93_pr91_canonical_reconciliation_20261018.md)と[8項目の対応行列](../data/repository_reviews/phase2_issue93_pr91_canonical_parity_matrix_20261018.csv)を作成し、PR #92の広域`pull_request.paths`を正本側へ追加する[非破壊PR #94](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/94)を作成。初回PR-head同一SHAで正本・比較CIはともにSUCCESS（main統合後の同SHA検証は未実施）。独立jobのcheck名とartifact名・外部依存、同一main SHAでの後継CI再検証・branch protection詳細は未解決。**重複するPR #92 workflowと旧5件、EXP-046元JSONは全件保持し、削除・停止は個別owner承認後の別PRに限定する。** Phase 2継続、Phase 3停止。

## 2026-10-18：B/C第1波の実行結果（削除・停止なし）

[旧5監査CIとEXP-046可逆集約の調査](phase2_bc_wave1_consolidation_20261018.md)を実施。旧5workflowの検査処理を[新しい共通CI](../.github/workflows/phase2_bc_wave1_consolidated.yml)で同条件実行できる見込みを確認し、EXP-046元3batch（RF-T005、10配置、計424,233報告評価、全30要素ベクトル）について34,818元bytes→11,692 bytesの可逆保存JSONを追加した。保存元は削除せず、後継CIの検証ステータス運用・trigger同等性と原本パス依存を継続審査。**原本退役承認0・変更0・Phase 2継続**。

## 2026-10-18：研究証拠の保存を守る「C寄りのB」整理方針（審査中）

ユーザー選択により、[Phase 2の段階的保管・退役方針](phase2_Bc_retention_and_retirement_policy_20261018.md)を**案として確定**。現行47 workflowは必須運用2・代替CIまで保持7・統合審査1・先行退役審査9・実験再実行代替後の退役審査28に分ける。元225証拠は必須原本128・数値等価性未確認81・集約審査16に分ける。最初は旧監査workflow5件とEXP-046の元中間JSON3件の**使用・出典・等価性調査のみ**進める。各元ファイルの個別削除承認はまだなく、変更・削除0件。Phase 2継続。

## 現行の管理課題（2026-10-17）

| 優先 | 論点 | 出典・次工程 |
|---|---|---|
| 対応済み／出典欠損は継続 | 元EXP-047 manifestは旧形式のまま保持。索引専用アダプターにより[PR #71の全回帰](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39028160775)は**マージ前SUCCESS** | [現行課題](current/open_research_questions.md)。元実行SHA・seed・環境は未確定。厳格manifestの完全復旧と区別 |
| 完了／旧14件の構造属性は未抽出 | 2026-10-17の旧14件＋現行10件を[24候補台帳](../data/catalog/phase2_candidate_catalog_20261017.csv)へ統合し、[W2構造検索索引](results/phase2_topology_search_20261017.md)をPR #78でmain導入 | RF-T005 6件／正式RF-F003 4件の区分を維持。旧14件は未抽出=unknown、結合の物理実装性未検証 |
| P1 | RF-F003共通探索pipeline、同条件での共通格子・独立検証、Q(f)/SRF/EM/実測・公差検証が未完了 | [RF-F003当時の計画](rf_f003_phase2_rebaseline_plan_20261016.md)、[現行課題](current/open_research_questions.md) |
| P1 | 2026-10-17のStep 1～5は[PR #71](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/71)、追加整理W0～W2は[PR #72](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/72)・[#73](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/73)・[#75](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/75)・[#78](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/78)でmain統合済み | [W3旧文書7件レビュー](phase2_cleanup_w3_document_review_20261017.md)では各固有情報を確認。所有者がD-001～004の元path削除を承認。固有情報を[歴史資料](archive/w3_consolidated_documents_20261017.md)へ統合して元4pathを削除。D-005～007・旧46件は保持 |

| P1 | W4実験証拠・旧workflowのレビュー | [W4非破壊監査](phase2_cleanup_w4_evidence_workflow_review_20261017.md)でE-001/E-002の747件とworkflow39件を実走査し、旧46件原本を保持。225件の機械索引未参照は**削除許可ではない**。[追加の実行済みW4精査](phase2_cleanup_w4_forensics_20261017.md)では225件（うちJS解析ソース59件）・7源グループを個別分類し、39workflowのAPI実行履歴を確認 | [225件CSV](../data/repository_reviews/w4_unindexed_225_review_20261017.csv)／[39workflow CSV](../data/repository_reviews/w4_workflow_runs_20261017.csv)。API可視32件に履歴あり、7件0は非使用の証明でない。元runの再現性・動的参照・代替手段と承認を追加確認するまでE/W削除0件。[2026-10-18 W4再実行依存監査](phase2_cleanup_w4_replay_dependencies_20261018.md)で225原本SHA・元manifestの参照・Python27/JS59件の構文だけを確認。EXP-042の6件の実runと10件の期限付きArtifactメタデータを保存。[EXP-042 ZIP原本バイト保全](phase2_w4_exp042_artifact_preservation_20261018.md)で10ZIP／19内部ファイルを取得、ZIPと全memberのSHA-256を紐付けて[Gitへ元ZIPのBase64バイトを保全](../data/repository_reviews/w4_exp042_actions_original_zip_b64_20261018.json)。有効期限経過後もオフライン検証可能。RF数値再実行なし。[W4 EXP-042 ZIP⇔Git checkpoint照合](phase2_w4_exp042_artifact_checkpoint_crosswalk_20261018.md)で10 ZIP／19 memberを比較し、30dB選別は一致、35dBとcf1は別stage、cf2/both/pcb_cf2の3 variant・6 memberは対応する選別済みGit checkpointパスが存在しないと確認。元ZIP・チェックポイントを共に保持。[未選別3変種の元データバイト復元・IL/面積比較](phase2_w4_exp042_missing_variant_recovery_20261018.md)で6件の元JSONを保全。cf2/both/pcb_cf2は同面積の既存RF-T005観測パレート候補より最悪ILが大きいため現行候補台帳に追加しない。保存元と既存選別元のActions run IDが別であることを35dB/cf1について確定。[EXP-046/047の131原本のSHA・訂正出典レビュー](phase2_w4_exp046_exp047_source_review_20261018.md)でRF-T005と正式RF-F003を区別し、旧46件と131原本SHA、EXP-047のQバグ除外5原本、正式RF-F003パレート4候補の元SHAを確認。**W5は読取専用の完了監査に限定**し、研究原本・workflow削除判断は未承認 |
| **監査完了判定のみ／W4退役は未完了** | **W5：Phase 2リポジトリ整理の読み取り専用総合監査（2026-10-18）** | [W5総合報告](phase2_w5_readonly_closure_20261018.md)／[14ゲート](../data/repository_reviews/w5_phase2_gate_matrix_20261018.csv)／[固定機械監査JSON](../data/repository_reviews/w5_phase2_readonly_closure_20261018.json)でW3の4件削除と3件保持、旧46・W4 225・EXP-046/047 131・旧39workflow・EXP-042 10ZIPの保全を横断検証。**研究実験・workflowの削除を承認したものではなく、W4の削除工程は未完了**。旧T-001～010は[W5後続の現況照合](phase2_w5_followup_disposition_20261018.md)で個別検査済み。Phase 2継続 |
| **文書の現況照合済み／退役承認待ち** | **W5後続：T-001～010／workflow47件／未索引元225件の分類（2026-10-18）** | [判定報告](phase2_w5_followup_disposition_20261018.md)／[T10件](../data/repository_reviews/w5_followup_T001_T010_status_20261018.csv)／[workflow47件](../data/repository_reviews/w5_followup_workflows_47_20261018.csv)／[証拠225件](../data/repository_reviews/w5_followup_evidence_225_20261018.csv)。旧T台帳の未着手は歴史状態で、策定時から9文書が更新済み。EXP-004の古いActions Webリンクのブラウザー遷移のみ未確認。旧39＋後続8を含むPR-head47 workflowは全件保持、静的書込兆候5件の詳細点検が重要。元225件も全件保持。**研究原本／workflowの削除は0件、個別承認なし** |
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
4. **P1 / RG-005・RG-007:** **外部アーカイブは使用しない（ユーザー指示）**。現行main 731ファイル/約8.45MB。新規実験の完全候補と再現用最小証拠をGitHubへ保存し、全iterationログは原則保管しない[Git-only保存方針案](experiment_result_storage_policy_proposal_20261015.md)へ変更した。旧6ブランチの先端監査・一時Git bundle復元PASSだが、ブランチ削除は**承認とGitHub内archive ref保全**まで保留。RF-T004小容量ZIPは35member SHA登録済み・**元バイナリGit未収録**。[保管最適化監査](phase2_repository_optimization_review_20261015.md)を参照。
5. **P1:** 候補間の周波数格子・独立MNAの共通条件での再比較、元試行環境・seedの再現性確認、物理SRF/寄生/EM・温度公差。新規解析を実行した場合は別検証記録として出典を固定する。

現在の課題ステータスは [研究レビュー台帳](../data/research_review_issues.csv)、候補区分は [研究候補台帳](../data/research_candidate_register.csv)、全39実験は [証拠インベントリ](../data/experiment_evidence_inventory.csv) を参照。

---

## 以下は過去時点の記録（現行ステータスではない）

**2026-10-14 現行作業状態（RF-F002 Full-LPF runner recovery/refinement）。** PR #47は最新`origin/main` `eb1de13841c1b4a74f18f4f9320e0316fbdd478f`に含まれる。追試branch `test/rf-f002-full-lpf-recovery-20261014` はレビュー用で、mainへ未merge。EXP-034～041でlive manager/worker停止・再開、1/2 worker、正規checkpoint warm-start、scaled/unscaled/FTOL、9→17 gridを記録。正しくremapしたEXP-041 30dB stageはIL 0.318693189dB（生H2/H3は30dBを約3e-9dB下回り、1e-5 tolerance内）、35dB stageは0.378349100dB。どちらもIL≤0.30dB未達、30dB点は実質余裕なし。**S1 100 graph searchを開始せず、Phase 2継続、Phase 3停止、RF-F002不変。** bounded evidenceとS1/S2/S3予算は[Phase 2追試報告](rf_f002_full_lpf_phase2_20261013.md)を参照。有限grid/MNAのみで連続band・物理性能証明ではない。

**2026-10-14：RF-T004・EXP-021（既存EXP-020との対比）。** [実験記録](../experiments/chatgpt_topology_search/runs/EXP-021/README.md) に文献着想の4L固定橋絡＋最大3可変Cの再合成、合法範囲の隣接磁気結合|k|≤0.15、LQW04 Q33置換、GJM固定C増設の有限探索を記録。7001点／各CSV周波数区間と84点独立枝電流MNAで、公称30dB条件4HV・面積8のIL=**0.393327dB**、公称35dB条件4HV・面積8のIL=**0.447944dB**を確認。4×LQW04（Q33仮定・SRF未確認・面積16）は30dBで0.310621dB／35dBで0.348604dB。いずれも0.30dB未達であり**EXP-021限定**の結果。重要：既存[EXP-020](../experiments/chatgpt_topology_search/runs/EXP-020/README.md)にはRF-T004・35dB・IL=**0.297114dB**／面積13⅔の独立再検証済み公称数値解があるため、これをプロジェクトの先行基準として保つ。今回の結合上限0.15は複数ペア同時実装未証明、全Q33候補はSRF/Q(f)/物理寄生未検証。比較条件の混同を避け、Phase 2継続／Phase 3停止。

**2026-10-14：RF-T004試験探索 EXP-016（Phase 2）。** [実験記録](../experiments/chatgpt_topology_search/runs/EXP-016/README.md) に文献着想による22種の有限トポロジー探索と局所最適化・独立枝電流MNA（21点/候補）・各帯域2,001点/区間の再評価を記録。RF-T004（RF-F002ベース、可変C最大3枝、各0～1.5pF/Q50、その他は正式条件のまま）で、30dB必須条件のbest-foundは面積4⅔・最悪IL=**0.480214dB**（PCBパターンC×2）、35dB公称条件のbest-foundは面積4⅔・最悪IL=**0.596216dB**（固定トラップCのみ）。3L＋1固定Cの小型候補では面積3⅔・30dB時0.497264dB／35dB時0.630323dB。**いずれもIL≤0.30dB未達。** 候補は試験版の数値照合であり、数学的連続極値保証、Q(f)/SRF/EM/寄生、実レイアウト、WSL2 uv lockによる再実行、解決済みtrial条件ハッシュは未完了。正式RF-F002の最良候補へは昇格させない。これにより本ファイルの旧「RF-F002下のLPF性能最適化は未実行」の記述をRF-T004試験結果へ拡張解釈しない。Phase 2維持、Phase 3停止。\n\n**2026-10-13：現行正式RF-F002、試験RF-T004を承認・登録。** 結合／PCB-L／可変C容量・Q・配置／LQW04 Qを改訂。Phase 2の制約台帳、互換JSON、旧RF-F001再現、基礎結合検証、およびP4-Aの可変C配置列挙を更新。回帰CI [run 38410571500](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38410571500) はPASS。RF-F002下のLPF性能最適化や達成値の独立確認は**未実行**。残作業は制約適用範囲の監査、候補探索、各6設定の全帯域高密度検証、独立MNA・電力収支・SPD・実装性確認。以下のRF-F001「現行」記載は記録当時のもの。Phase 3移行は未承認。

# Phase 2 ロードマップ（現行版）

**2026-10-12 RF-F001の正式方針更新：** チップ面積コストのハード上限を廃止し、6設定UL/DL最悪ILとのパレート評価軸とする。以下にある「hard cap6」「面積最大6」は過去の探索条件・旧実験予算の記録であり現行正式RF制約を表さない。P4-Aでは当面の計算範囲として面積6までを維持し、探索範囲の拡張は別管理する。旧候補の実測/数値記録は不変更。詳細は[制約版管理](../data/constraints/README.md)。

## 2026-10-14 Phase 2 / Full-LPF 追試状況

PR #47（Full-LPF runner統合）は`origin/main`の`eb1de13841c1b4a74f18f4f9320e0316fbdd478f`に含まれる。追試branch `test/rf-f002-full-lpf-recovery-20261014` は[PR #48](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/48)としてレビュー中で、EXP-034～041を事前登録・記録。live SIGINT/SIGTERM/lock/resume/hash拒否、4-task 1/2-worker比較、checkpoint terminal remapping、warm/multi-start、9→17 grid refinement、scaled/unscaled/FTOL比較を実行した。詳細は[Phase 2 Full-LPF追試報告](rf_f002_full_lpf_phase2_20261013.md)と各manifestを参照。

正規importされたEXP-017 warm-startの30dB stageはIL 0.318693189 dB（H2/H3生値29.999999997/29.999999999 dB、1e-5 tolerance内）、35dB stageはIL 0.378349100 dB。1001点/segment有限確認で数値一致したが、IL≤0.30dB未達、30dB点のraw marginは実質ゼロ。scaled条件は35dBで収束し、unscaledは低IL/低marginのtradeoff。よってPhase 2継続、S1（100 start）未開始、Phase 3停止、正式RF-F002不変。最新実測start時間96.7–145.0 worker秒を単純外挿したS1は1 worker 2.7–4.0h。2-workerの1.6–2.3hは短いEXP-035倍率を仮置きしただけで、長時間correctly-mapped throughputは未確認。

## 2026-10-12 Stage 2：WSL2ローカル実行基盤

**大規模P4-Aの主計算先をGitHub ActionsからWSL2ローカルへ移す方針**を反映した。これは計算環境の変更であり、RF-F001・RF-T001/T002/T003、P4-Aの回路探索、評価関数は変更せず、Phase 2を維持する。Phase 3への移行・大規模探索の開始はしていない。

- uv管理を導入。`pyproject.toml`を依存条件の正本、Python 3.12対象の`uv.lock`を固定環境としてGit管理し、`requirements.txt`は互換ミラーとして維持。監査・既存手動探索Actionsも`uv sync --frozen`を利用する。
- `scripts/local_p4.py`は計画、独立worker起動、RAM・CPU/RSS監視、SIGINT/SIGTERM停止、チェックポイント再開、互換性拒否、集計を提供する。既存`p4_batch.py`/`p4_sharding.py`と集計器を再利用し、RF解析・最適化本体は変更しない。既定worker数2、最大4、利用可能RAMが1.5 GiB未満では新規起動を保留する。
- `docs/local_execution.md`に環境構築・plan/run/status/resume/aggregate・停止・復旧・結果保管を記載。GitHub ActionsはCI・回帰試験用として維持し、既存P4-A等の手動探索workflowも保存する。
- 最終回帰: `uv lock --check`、`uv sync --frozen`、`uv pip check`、`scripts/audit_results.py`、ユニット203件、`scripts/verify_no_pcb_tunable_candidates.py`がすべて終了コード0。既存の5L試験コードから未close fileの`ResourceWarning`が1件出るが試験結果には影響なし。
- WSL2小規模ベンチ（RF-F001、`matching_only`、seed `20261013`、4シャード、最大5グラフ、SLSQP各1反復、粗2点/検証3点条件）では、1/2/4 workerすべて5グラフ・9候補を処理。グラフIDと数値・最適化結果は3条件で一致（完了時刻メタデータのみ異なる）し、失敗0・未実行0・収束0（全9件は1反復のため非収束）。これは実行基盤の比較でありRF性能試験ではない。

| worker | 最大同時worker | wall time（uv起動込み） | 合計ピークworker RSS | 最低available RAM | host CPU peak |
|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 7.06 s | 79.27 MiB | 5.69 GiB | 9.6% |
| 2 | 2 | 5.24 s | 158.09 MiB | 5.63 GiB | 13.0% |
| 4 | 4 | 3.97 s | 316.20 MiB | 5.53 GiB | 25.3% |

追加で1秒のwall-time制限による中断を実行し、終了コード130・各実行中シャードのcheckpoint保存を確認。`resume`後は5グラフ・9候補でcompleted、重複IDなし、失敗・未実行0。小規模機能検証であり、長時間停止時の実機環境挙動・4-worker時の大規模RAM需要・大規模計算性能は未検証。`results/`はGit管理外であり、生出力を正式研究候補に昇格させていない。

## 当面の目標

**LPF-007を上回る現行仕様の`full_lpf`回路を発見する。** LPF-007の保存済み有限グリッド値は6設定UL/DL最悪IL=0.513168414 dB、H2/H3最小約35.07 dB、面積6。最適化未収束・EM未検証。EXP-038/039のcorrectly mapped warm-startは35dB within 1e-5 toleranceでIL 0.378349100 dBまで改善。EXP-041の30dB boundary stageはIL 0.318693189 dBだが、raw H2/H3は30dBを約3e-9 dB下回り、35dB nominalを満たさない。**どちらもIL≤0.30dB未達**であり、現時点で受け入れ済み目標候補ではない。新候補は同じ制約・同じ帯域で再評価し、35dB公称性能または明示した30dB tradeoffとresidualを個別に報告する。

## 開発順序

| ゲート | 作業と実測による完了条件 | 状態 |
|---|---|---|
| **G1** | GitHub Actionsの決定的分割・Artifact保存／別run復元・再開・集計。1/2シャードの実機smoke。 | **完了**（main `35642be3`、[2シャード最終run](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38128871403)）。 |
| **R0/R1** | LPF-007/008を汎用MNAで同値再現する回帰テスト。任意内部ノードへの対GND可変C配置を許す共通回路表現。既存G1との互換性テスト。 | **一部完了**：LPF-007/008の基準値固定回帰とG1再開スモークPASS。内部可変C位置の一般化は未完了。 |
| **G2** | MNAの実測profiling・高速化、SLSQP／epigraph minimax／多初期値・継続法。時間、収束率、評価回数、ILを同条件で比較。 | **部分完了**：bounded Full-LPF runnerの実process recovery、scaled/unscaled、FTOL、warm/multistart、9→17 gridをEXP-034～041で実測。IL≤0.30dB候補は未発見。 |
| **E1** | P4-A（内部ノード≤4、固定枝≤8、面積≤6）を宣言した探索範囲で実行し、生成・未探索・失敗数、面積別best-found IL、計算資源を記録。 | **未開始**：S1 100 graph/start探索は明示的に未起動。topology coverage/長時間worker throughputを先にreview。 |
| **E2** | ChatGPT発案の専用ソルバと汎用グラフ探索の両トラックで`full_lpf`最適化。LPF-007を上回る有望解の独立検証。 | **部分完了**：既存4L/2C warm-startの有限局所最適化は実施。目標IL≤0.30dB達成なし、全合法graph探索でもない。 |
| **V1** | 6設定UL/DL・UL H2/H3の高密度周波数評価、独立式、SPD、電力収支、物理配置、部品・公差の確認。未解決項目を列記。 | **数値のみ部分完了**：EXP-041を1001点/segment・独立MNAで確認。連続band proof、SRF/Q(f)/parasitic/EM/tolerance/physical implementationは未実施。 |

## PR #10再編成後の検証記録（2026-10-11）

- 回帰CI：[実行38139630762](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38139630762) **PASS**。89ユニットテスト、監査、LPF-007/008の保存済みIL/H2/H3との数値照合、Q・可変C制約、代表点独立MNAと電力収支を実行。matching-only既知回路の解析解回帰を追加。新しいLPF回路の最適化はしていない。
- G1新構成スモーク：[実行38139630751](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38139630751)、ソースコミット `fe322ea204b5ff232150da0902cead2923980205` で **PASS**。GitHub-hosted Ubuntuの3ジョブで、1シャード・3サンプリンググラフを1件ずつ計算。Artifactを2回復元し、最終チェックポイントは`completed`、残り0件、`resume_count=2`。既存のG1集計器が`overall_complete=true`、`optimized_graphs=3`、欠落0件・エラー0件を報告。
- このスモークの条件は各グラフ1初期値・1最適化反復、粗い通過帯域2点/セグメント、検証3点/セグメント。**数値精度・高調波減衰・P4-Aの探索網羅率・新性能の証明ではない**。修正後もPhase 2のまま、Phase 3は未承認。
- PR #10では設計仕様文書への参照先等が変わり、以前のG1チェックポイントとは設定ハッシュが異なる。**旧Artifactを互換とみなして復元しない**。計算条件のソース指紋が一致する新runだけ再開可能。スモーク後にワークフローを手動専用の[再利用可能な検証手順](../.github/workflows/lpf-p4-a-smoke.yml)へ整理した（計算ソース・RF数値制約は不変更）。

**ChatGPT主導の新トポロジー考案は上記ゲートに並行して継続**する。良好解を体系探索の初期値に、体系探索の良好グラフを専用最適化の対象にする。

## 2026-10-11 PCBパターン固定Cの設計条件追加\n\nPCBパターン固定C（Q40、0.02≤C≤0.2pF、最大3個、チップ面積0）を新しい探索素子クラスとして受け入れた。まずPCB-Lなしの既存LPF-007/008に対する寄生依存・損失感度を評価し、次に固定GJM01との置換・併用を比較する。容量上限0.2pFを厳守し、数値探索の範囲設定でも遵守する。計算ジョブで有限の数値探索範囲を選ぶ際は、設計上の上限と区別して明記する。**既存P4-Aの実行は自動で探索クラスを広げず**、新種別を有効化する探索ジョブの対象数・計算時間を事前に評価する。\n\n## 旧4可変C設計から学ぶ新トポロジーの優先事項（2026-10-11）

[EXP-003制約比較](../experiments/chatgpt_topology_search/runs/EXP-003/README.md)を確認。旧CP07の0.328924dBは4本のCを6設定ごとに個別連続変更（うち3本は非対GND）できた理論解で現行制約を満たさない。旧回路の4可変Cを維持して結合だけ現行一列・隣接ルールへ再最適化すると、有限局所探索で0.337660dBの成立解が出た（未収束、実レイアウト未検証）。現行A7-01は0.508389dB。次に優先するのは、チップ部品追加だけでなく、**2本の対GND可変Cで複数の高調波伝送零点を動かす結合共振型**を発想・列挙すること。旧4可変Cの位置自由度を勝手に承認済み条件として復元しない。

## Phase 2の中間性能ゲート：IL≤0.40dB（2026-10-11）

[EXP-004探索レポート](../experiments/chatgpt_topology_search/runs/EXP-004/README.md)に、6設定のIL≤0.40dB・公称H2/H3≥35dBを中間目標として設定。保存済みコスト7基準はA7-01の0.508389dB。3直列LC・2シャントLC・5チップLの有限局所探索98件では更新解未発見、42組合せ未完了。高速周波数方向一括MNAのA7-01基準照合と101ユニットテストは成功。コスト7は別の実験予算であり、承認済みhard cap6はそのまま保持する。

次は[手動4シャードGitHub Actions](../.github/workflows/lpf-target040.yml)を使って、複数初期値・十分な反復・失敗を含む進捗記録を確保する。新しい最良解は高密度の6設定全帯域・独立MNA・電力保存・SPD・面積で再確認するまで基準へ昇格させない。なおスクリプトやワークフロー追加を計算完了とはみなさず、実行済みArtifactを根拠とする。目標0.30dBとPhase 3停止は変更しない。

## EXP-005：コスト7ベンチマーク更新（2026-10-12）

[EXP-005](../experiments/chatgpt_topology_search/runs/EXP-005/README.md) で、新規局所最適化132回（PCBパターンC追加24、GJM/PCB-C置換36、5L＋3GJM・3直列2シャント72）と、既存A7-01の制約付きminimax精密化を実施した。追加回路族では0.508389dBを更新できなかったが、再精密化によって**0.507331dB、H2/H3最低35.02dB**の[A7-03](../experiments/chatgpt_topology_search/runs/EXP-005/A7-03.json)を発見した。現行の35dB公称減衰下で0.40dB目標には未達。未収束の局所解をトポロジー限界とせず、未探索の2・3PCB-C、多初期値継続法、2つの可変Cが複数伝送零点に作用する新構造を優先する。正式面積hard cap6とPhase 3停止は変更しない。

## 2026-10-12 EXP-006：2可変対GND Cによる伝送零点制御を重点化

[EXP-006](../experiments/chatgpt_topology_search/runs/EXP-006/README.md)にて、コスト7の既存A7-03のSLSQP制約境界再最適化でIL **0.506951dB**を発見。H2/H3最小減衰は約35.002dBで、公称仕様には成立するが余裕極小。独立MNA54点・SPD・エネルギー収支と高密度周波数メッシュで検証。さらにPCBパターンC×2の30配置、×3の12配置、5LQP02+3GJM01の56配置を各少数初期値でスクリーニングしたが、最良数値を更新せず。**有限探索であり物理的性能限界ではない。**

従来回路族の単純追加より、旧CP07の伝送零点を現行の2つの対GND可変Cで連動させる新トポロジー設計を優先する。モード電圧に基づく2制御C対複数零点の感度、適応的周波数格子、独立検証を導入し、GitHub Actionsで多初期値・checkpoint付き大規模ジョブへ移行する。新しい数値候補A7-04と、公称減衰余裕の比較用A7-03は両方保持。正式hard cap6・Phase3停止は変更しない。

## EXP-007：単一枝再配置の限界と次の重点（2026-10-12）

[EXP-007](../experiments/chatgpt_topology_search/runs/EXP-007/README.md)で固定GJM01接続変更44、チップL接続変更44、PCB-L1本追加15の**103局所最適化**を実施。各31点/区間の35dB粗グリッドを満たす解は19+20+5=44件。GJM-C枝変更の最良は0.524581dB（7,001点／区間・54独立MNA点で確認）で、コスト7の[A7-04](../experiments/chatgpt_topology_search/runs/EXP-006/A7-04.json) 0.506951dBを更新せず。A7-04の2可変C→H2/H3局所最小減衰の感度行列ではB71の条件数≈9.36と制御感度の偏りが確認された。単一枝の置換が悪かったことを新トポロジーの理論的下界と解釈しない。次は**複数枝の同時再合成、共振零点の感度行列を考慮した構造的枝刈り、継続初期値を使う多初期値GitHub Actions探索**へ重点化する。Phase 3停止・正式hard cap6維持。

## 技術的な優先事項

1. 自動P4-AがIN/OUTの可変Cしか配置できない点を改め、LPF-007/008の内部シャントLCを共通モデルで扱えるようにする。
2. `src/lpf/`の共通解析／最適化APIを、既存テストとG1再開互換を確認しながら整備する。実験固有コードは`experiments/`に残す。
3. 粗い最適化、精密最適化、独立検証を分離する。未収束を性能限界と解釈しない。
4. 自動探索の「網羅」は宣言した有限グラフクラスに限定し、連続素子値の大域最適性と混同しない。

Phase 2の最終結果は、同条件で比較できる候補群・コスト別性能・探索範囲・未確認物理項目・再現条件を揃えて報告する。**Phase 3へは自動移行しない。Phase 4以降の旧計画は採用しない。**
