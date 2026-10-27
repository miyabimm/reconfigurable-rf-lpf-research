# W3 歴史文書統合：D-001～D-004（2026-10-17、Phase 2）

> **現在のGit treeから削除した旧二次文書4件の要点と出典を保持する歴史資料。** 旧文書自体は削除直前コミット `88562135dae2edf8ba7763aa529181c05f7c1ded` とGit blob SHAからバイト単位で復旧可能。ここに書く「正式」「現行」「未実装」は各**原作成日**の意味であり、2026-10-17のRF-F003正式／RF-T005試験を上書きしない。
>
> 所有者は2026-10-17 14:55:06 UTCの「削除を承認します。作業を進めて」で、直前のW3判定における**条件付き削除候補D-001～D-004**の整理・削除を承認した。D-005～D-007の歴史的Pareto数値、EXP-015独立MNA、P4-A有限探索範囲は削除対象から除外して保持する。承認したのはGit追跡treeの旧二次文書の整理であって、研究の生データ、実験run、履歴、ブランチの削除ではない。

## 0. 削除した4件の元出典と復旧性

| ID | 元path（削除直前のバージョンへリンク） | 元Git blob SHA-1 | 旧W0記録のbytes |
|---|---|---|---:|
| D-001 | [docs/repository_reorganization_plan.md](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/88562135dae2edf8ba7763aa529181c05f7c1ded/docs/repository_reorganization_plan.md) | `1c0673ed2f19b3e98d5c1c06b6ff1e3617f827c6` | 7,978 |
| D-002 | [docs/research_result_governance.md](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/88562135dae2edf8ba7763aa529181c05f7c1ded/docs/research_result_governance.md) | `946049b8ceba42b589142c8ce073098ec95fcea6` | 10,959 |
| D-003 | [docs/phase2_actions_ci_repair_20261017.md](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/88562135dae2edf8ba7763aa529181c05f7c1ded/docs/phase2_actions_ci_repair_20261017.md) | `4c45f2b05e6831d1f536c6a1fc2beb29b4d11a2d` | 7,720 |
| D-004 | [docs/repository_storage_audit_20261014.md](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/88562135dae2edf8ba7763aa529181c05f7c1ded/docs/repository_storage_audit_20261014.md) | `2918391b5ceb8b78f8166abd6ed626f15fe4d1a3` | 4,745 |

復元例：`git show 88562135dae2edf8ba7763aa529181c05f7c1ded:docs/research_result_governance.md > /tmp/research_result_governance.md`。同一commitにある残りの3pathも同じ方法で復元できる。変更や出典の完全再実行が必要ならこの元文書を優先し、要約だけから失われた文言を推定しない。GitHub上の旧pathリンクは**固定コミットを指定した履歴URL**であり、現在のmainの物理pathではない。

## D-001

**2026-10-12のCodex向けリポジトリ引継ぎ計画（RF-F001時点）**。旧面積ハード上限を正式制約から除き、探索面積6はP4-Aジョブ固有パラメータとした。高調波30dB必須と35dB公称、`matching_only`と`full_lpf`、旧LPF-007/008/009・EXP-001～015の履歴と新規RF条件を分離した。

元文書の**R1～R5（時点付き未完了・予定事項）**：
- **R1 制約・実験版管理**：RF-F001を上書きせず新RF-F002 IDで変更、試験条件は別ID、各EXPに元実行情報を確認可能な範囲でmanifest登録、旧候補に条件ID・effective SHAを紐付け。未確認seed・環境は捏造しない。試験overrideの型・承認・正式昇格阻止を検証。
- **R2 共通回路・ソルバー**：HV/HQを明示シリーズとして受け付け、内部ノードへのシャント可変C配置の一般化、LPF-007/008の一般化MNA同値検証、SPD・6設定共通固定素子・結合の物理制約チェック。`experiments/matching_limit`から`src/lpf`への共通API段階移管は「計画」であり完了扱いしない。
- **R3 P4-A範囲・Pareto**：面積6をRF必須値と誤用しない。`--max-search-area`等の実験スコープ、グラフ／初期値／セルごとの探索済・未探索・失敗・非収束・計算時間・目的・閾値・seed・コードSHAを記録。同一制約・同一検証格子・同一depthでのみ比較し、`full_lpf`の高調波制約付き最適化は別に必要。
- **R4 Actions・保管**：依存環境・BLAS固定、CIと探索runnerの分離、Artifactsの停止・中断・再開の実機確認、期限付きArtifactからの重要証拠選別保全、旧EXP専用workflowの削除は事前調査と別PRが必要。
- **R5 文書整理**：READMEには現行成果入口、歴史的数値は日付・RF条件付きで移管。`hard cap6`の旧記述を公式に読み替えない。変更パス、レビューと正本の優先関係を案内するガイド作成は原時点の提案。

原文で実装済みと記述された事項は**RF-F001当時の基盤実装**であり、RF-F003共通runnerの完了を意味しない。新制約は[正式レジストリ](../../data/constraints/registry.json)、現行研究状態は[ロードマップ](../roadmap.md)を優先する。

## D-002

**2026-10-14の成果管理規則初版（当時はRF-F002）**。全39実験のmanifest/実験索引と、選別した9件（のち13件）の研究候補台帳を分離。原checkpointと検証結果・`checkpoint_stage_index`・effective制約SHAを残す。全実行結果を完全網羅したとの宣言ではない。

| 当時の成立区分 | 正しい意味 |
|---|---|
| `strict_finite_grid` | 生のmin-H2、min-H3がともに閾値以上。**有限格子のみ** |
| `tolerance_only` | 生値は閾値未達だが`1e-5 dB`以内。strictとは非互換 |
| `reported_finite_grid` | 元資料の報告値に基づく。独立再計算済みへの自動昇格は禁止 |
| `historical_only` | 旧モデル。現行正式条件への流用禁止 |

比較は`comparison_key`と条件ID／実効hash／目的／減衰閾値／検証方法が一致する範囲内。正式RF-F002と試験RF-T004、30/35dB、整合のみとfull-LPFの混合禁止。面積はハード上限ではなくPareto比較軸。元`scripts/audit_research_catalog.py`は出典と表の整合を調べる監査であり、RF新規計算ではない。

**当時の数値・進捗**：最初の9件に旧LPF-007/008/009、EXP-017/023の7001点checkpoint、RF-T004 EXP-020、EXP-041の30/35dB stageを含んだ。EXP-041は30dB stage IL`0.318693189dB`、35dB stage IL`0.378349100dB`（許容差のみ）。EXP-020の`0.297114032dB`は**RF-T004試験**結果でありRF-F002正式ではない。後にEXP-016の4件の報告候補を加えて13件に更新した。

**G-C2当時の39実験棚卸し**：正式19・試験5・歴史15、execution `completed`17・`partial`6・`unknown`16。原manifest `evidence=[]`はEXP-016/017/021/022/023/024の6実験（外部補助証拠が存在しない意味ではない）。seed未記録25、execution SHA未記録15、EXP-025～041には個別READMEがないもの17。補助索引36件を[Git SHA別の出典目録](../../data/supplemental_experiment_evidence_index.csv)へ保存（SHA-1とmanifest SHA-256を混同しない）。EXP-016の事後独立追試は[CI 38587242196](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38587242196)：7,001点/区間と独立84点MNAを保存した新しい検証overlayであり、元manifestの`execution=unknown`を遡及訂正しない。

**歴史的障害と保留**：EXP-017の元23要素欠落はその後回収済み（当時の課題RG-001を現行欠落と扱わない）。EXP-016のREADMEと旧manifestの矛盾、EXP-034～037のwarm-start端子remap誤り、EXP番号付け直しの歴史、lock/manager.log等の診断証拠は一次記録を保持。G-C1～G-C4は当時の段階計画で、G-C2以降を当時すべて完了したことにはしない。[訂正記録](../result_record_corrections_20261014.md)、[現行研究レビュー課題](../../data/research_review_issues.csv)を参照。

## D-003

**2026-10-17 CI/manifest修復の事故記録（RF設計性能の更新ではない）**。リポジトリpublic可視性変更後にworkflow YAMLとmanifest監査の別種類の失敗を確認した。課金設定を修正した主張ではない。

- [失敗した旧run 38993047810](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38993047810)：`scripts/audit_results.py`がEXP-044の不正execution状態・EXP-046 manifest欠落を検知。`exp042_passband_q.yml`には`if-no-files-found`重複keyがあり、workflow loadingが失敗、実jobが0件だった。
- EXP-044は旧の自由書式execution/validation文言を正式フィールドへ対応させ、元の記述を`search_scope.pre_schema_repair_record_20261017`に保管。EXP-046はRF-T005試験のmanifestを追加したが、28×1001 reduced-nodal評価／84点独立MNAは**既存の報告**であり当該CIで再実行したものではない。EXP-045は当時予約済みでも元snapshotではmanifest未登録だった（その後の統合を次項で区別）。
- 正しいmain workflow blobは`fcb85b8b52603202a9d71e79bc96c05db7217e68`。`tests/test_github_actions_yaml_keys.py`の入力重複keyチェック追加commit`dd4e98ed934e61ff2f730ef559515462bf029e29`。[main CI 38996198991](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38996198991)および[38996711799](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38996711799) SUCCESS。
- 当時開いていたPR #65（YAML修正commit `cea5a551b9efda254135ea67f1f75d1a83dd956b`、新回帰は未確認）、#64（`ba46c0fc3911709f1d66a7ad538bc55b26267599`、[Q run 38996649034](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38996649034) PASS、EXP-045 manifest監査は別に失敗）、#62（`762940db822c7e88a0b1738c579a7aed6e7b83a1`、[Q run 38996651758](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38996651758)と[回帰38996651748](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38996651748)はPASS）へ修正を反映。
- [元PR #64の失敗run 38996649074](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38996649074)はEXP-045 manifest 10キー欠落による**監査jobの失敗**であり、上のYAML読込失敗とは別。エラーを隠したり実行SHA・独立MNAを創作したりして成功扱いしない。

**03:44 UTCの後日統合記録**（以前の「#64未解決」記述を当時の履歴として保持）：

| PR | mainマージSHA | 処理と検証 |
|---|---|---|
| #65 | `cc22c7ec2ff97b836365e77a14ca9d32832ff0b1` | EXP-045のin-chat出典・正規manifest、回帰38997436104成功 |
| #62 | `a3bed9b304e55f3fb623c8255d30478b986f1950` | T/π結合理論、`test_phase2_standalone_function_coverage.py`追加、回帰38998999844成功 |
| #64 | `39d394b9f310928115c119b7a253030441707505` | EXP-045別3L checkpoint追加、#65正規manifest不変、元PR版を`archive_PR64_original_manifest_20261017.json`等に保全。古い失敗runは失敗記録として残す |
| #59 | `e9ca3cab477ad0e8fc197f2817247b092998b38c` | EXP-042の4L追加出典、main回帰38999715559成功 |
| #58 | `6b4f3941067e3cb0823f602051e22bcccd72aebc` | EXP-042 Cf2∥Cv2訂正、PR check 38999677183/38999677194/38999677216/38999677351成功 |

[統合後main CI 38999850687](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38999850687) は上記最終統合コミットで28ステップSUCCESS。workflow/manifest修復のCI PASSは外部固定S2Pを含むRF-F003新最適化、独立物理SRF/Q(f)・EM・公差・実測を証明しない。

## D-004

**2026-10-14時点のGit保管構造・非破壊監査**。基準main `73c4f19b3b1264beeb5e8cbb2764ae3f82fb4f57`（PR #49後）の再帰Git tree（`truncated=false`）から追跡blob数・非圧縮bytesの合計を調査。**Git packサイズ／全履歴容量ではない**。

| 場所 | 追跡blob数 | 元報告の概数 |
|---|---:|---:|
| 全体 | 707 | 8.30MB |
| `data/validation/` | 262 | 4.38MB |
| `experiments/chatgpt_topology_search/runs/` | 249 | 2.62MB |
| `scripts/` | 32 | 0.306MB |
| `tests/` | 68 | 0.225MB |

当時は同一blob34グループ・追加38path。`data/validation`下の診断的内容はファイル名に基づき**144件／約2.35MB**。`.lock` 39件（うち`uv.lock` 1件、runtime lock38件）、`.log` 42件、`/tasks/` 29件、`/results/` 35件。これらの件数は**不要ファイル判定ではない**。当時の`data/constraints/formal/RF-F002.json`と`data/design_constraints.json`の同一blobは正本と互換コピーという**意図的重複**だったが、現在の正式条件RF-F003は別の時点。旧EXP-020/source_pr38・収束解析code_snapshotも再現証拠であり、単純な重複判定で削除禁止。

当時の保管5分類：**A不変正本**（制約・band・原checkpoint）／**B候補キュレーション**（完全ベクトル・6設定可変C・出典）／**C再現証拠**（run config・hash・環境・独立検証）／**D診断**（lock/task/manager.log、再開試験では一次証拠）／**E一時結果**（未選別の`results/`、通常Git対象外）。診断・再開の依存逆引き、manifestのSHA256と現在のpath互換性確認後にのみ移動／削除する設計。Git履歴`filter-repo`、force pushなし。将来の探索でも元エビデンスを保持する。

## 検証・最新研究との分離

- 本統合は**旧資料の読取と整理であり新しいRF解析、最適化、EM測定ではない**。RF-F003正式とRF-T005試験の数値比較は[現行結果](../results.md)、[固定仕様](../../data/constraints/registry.json)を優先。
- [W3個別審査](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/phase2_cleanup_w3_document_review_20261017.md)は**削除承認前に実行した当時のレビュー**。本書および削除PRのCI結果が後続の実施状態を更新する。
- [W3処分台帳](../../data/repository_reviews/w3_document_disposition_20261017.csv)、[削除計画台帳](../../data/repository_reviews/phase2_cleanup_deletion_candidates_20261017.csv)に削除直前SHAと所有者承認区分を記録。W3 CIで4件を歴史コミットから`git show`復元してSHAを照合し、保持するD-005～007と旧46ファイルは現在blobの不変性を検査。
- **削除4件は現在の追跡treeのpath数を4減らすだけ**。新統合文書・更新検証コードを加えるため、リポジトリ全体のnetファイル数やGit履歴pack bytesの減少を保証しない。

**研究Phase 2継続。Phase 3は未承認。**
