# Phase 2 Step 5：リポジトリ整理の統合整合性検証（2026-10-17）

> **マージ後の追補（2026-10-17）：** [統合PR #71](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/71)はmainに**マージ済み**（merge commit `055b222c79c73c7fbeacb19383f21c1da0625195`）。[最終レビューHEADのPhase 2 regression](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39028160775)とStep 3／4／5の専用CIは**マージ前SUCCESS**。マージ時点でレビューHEADとのGit tree差分は0件。マージ後mainのpush CIは別実行として確認が必要。以下の「未マージ」「Draft」表示は**当時の検証コミットに紐づく履歴**であり、現在のPR状態を意味しない。

> **状態：検証実行済み／全4ワークフローPASS。** この文書はPR #67～70の統合検証ブランチの結果であり、元4 PRのmainへのマージ完了を意味しない。Phase 2を維持、Phase 3は所有者の明示承認まで停止。
>
> **基準main：** `bdb39904379637aeca5cf56ec3096e9e1b15f62a`。  
> **検証基準の統合ブランチHEAD：** `d1e8111f32d5762266faaa92e3968566ef829d2c`（後続の本報告追加コミットとは別）。  
> **検証ブランチ／Draft PR：** [PR #71](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/71)。  
> **参照元：** [Step 1：PR #67](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/67)、[Step 2：PR #68](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/68)、[Step 3：PR #69](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/69)、[Step 4：PR #70](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/70)。すべてDraft・main未マージ。

## 2026-10-17 マージ前レビュー修正・追補（上記旧テスト記録との区別）

本節は下記「最初のStep 5検証」より**新しい修正後の観測**を示す。歴史的な旧コミット・旧run値はその時点の証拠として本文に保持する。2026-10-17のレビューで問題となった固定main SHA、監査ファイル自己上書き、PR検証書込みトークン、将来のRF条件改訂時のアーカイブ監査停止を修正した。

- **2026-10-17保存元をコミットSHAで固定：** Step 4の元56文書・46保全対象およびStep 5の元1,043ファイルは`bdb39904379637aeca5cf56ec3096e9e1b15f62a`を直接参照する。**現在のorigin/main HEADが固定値に一致する必要はない**。将来の新しい実験や資料への保全ゲートとは区別する。
- **監査実行時にコミット済みファイルを修復しない：** Step 3/4 CIはまず`--check`のみ実行し、変更済みCSV/JSON/Markdownがあればfail-closed。保存用git pushジョブも廃止。ジョブ権限は`contents: read`、checkout認証情報の残留も無効。
- **歴史候補の変化耐性：** 旧14件CSV・RF制約レジストリ・実験索引を[固定2026-10-17入力](../data/catalog/README.md)にGit blob SHA一致で別保存した。現在の`data/research_candidate_register.csv`や現行active RF番号が更新されても、この日の24件の検証は元の証拠で行える。通常CIは引き続き現行リポジトリの監査を実行し、保存当時の値を現行設計目標達成と呼ばない。
- **適用範囲：** 日付付きStep 3/4/5の特別なPRジョブは、対応する監査コード・証拠・レポートの変更がある場合のみ走るよう`pull_request.paths`で限定。新しい一般PRを「昔の1,043ファイルの許可リスト」に固定しない。
- **追加の検証根拠（修正後統合コミット`7ed8e305ae992892c4d2a81d15c5d1533242d4df`）：** [Step 3](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39027871885)、[Step 4](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39027871809)、[Step 5](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39027871788)の専用監査はSUCCESS。Step 5の計数は**元1,043件・削除0・元blob不変1,032・既存11件の明示変更・現在の追跡1,092件・ローカルリンク403件未解決0**。
- **最終マージ時のCIゲート：** マージ対象HEADの[Phase 2 regression](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/workflows/audit.yml)と専用CIを確認する。現在のGitHub Actionsが記録するrun/HEADを最終状態の証拠とし、上記の過去SHAを「最終HEAD」と読み替えない。

本PRは原RF-F003制約・S2P・パレート原スナップショット・実験checkpoint・EXP-047旧manifestを変更しない。**Phase 2継続、Phase 3未承認。**

---

## 1. CI実行結果（統合ブランチに対する実行済み証拠）

| ゲート | GitHub Actions | 結果 | 実行範囲 |
|---|---|---|---|
| **Phase 2 regression** | [run 39024824321](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39024824321) | **SUCCESS** | 325 unittest全件PASS、RF正式制約、実験45件、旧検証パイプライン、候補24件・10比較群、元ZIP・元ブランチ・予約・Git保存監査 |
| **Step 3派生候補の検証** | [run 39024824317](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39024824317) | **SUCCESS** | 旧14候補とRF-F003 4／RF-T005 6候補の派生台帳・出典blob・条件別非支配点 |
| **Step 4歴史文書・保全監査** | [run 39024824319](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39024824319) | **SUCCESS** | mainの56文書、同一blob34組／追加38path、従来の46要レビュー件 |
| **Step 5統合保全・リンク監査** | [run 39024824311](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39024824311) | **SUCCESS** | 全旧Git treeの変更許可監査、S2P/制約、パレート出典、387ローカルMarkdownリンク、限定EXP-047アダプター |

**注意：** 上記runは報告文書の作成**前**のコミットに対するPASS。文書追記後の再実行で最終HEADも確認する。全回帰PASSはソフトウェア再現性・既存モデル内の検査を示すだけで、物理性能保証や全設計空間の探索完了ではない。

## 2. 元1,043ファイルの保全結果

[読み取り専用統合監査スクリプト](../scripts/verify_repository_step5_integration.py)により、Git blobをmainの固定コミットと比較。

| 監査項目 | 結果 |
|---|---:|
| main基準trackedファイル | **1,043** |
| 元blobをバイト単位で不変保持 | **1,032** |
| 意図した11個の既存ファイル変更 | **11** |
| main由来のファイル削除 | **0** |
| 明示許可リスト外の既存path変更 | **0** |
| 新規ファイル（上記テストHEAD時点） | **44** |
| 統合ブランチtrackedファイル（同時点） | **1,087** |
| ローカルMarkdownリンク（16追加ページ＋既存3ページ） | **387件、未解決0件** |

既存11ファイルの変更は文書入口・ロードマップ・条件別レポート生成・実験証拠インベントリ・旧EXP-047互換検査・対応テストとCIに限定。元研究checkpoint、旧run、S2P、bands、制約JSON、元manifest、Git履歴・branchesの移動・削除・上書きは行っていない。新規ファイル数は本報告・追加台帳のコミットで変わるため、常に監査時HEADと一緒に扱う。

## 3. RF-F003、RF-T005、パレートの照合

- 正式制約 [RF-F003](../data/constraints/formal/RF-F003.json) は [レジストリ](../data/constraints/registry.json) のactiveであり、[互換用design_constraints.json](../data/design_constraints.json)とバイト一致。
- 外部固定S2P：入力 `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、出力 `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da` が正式RF条件の指定SHA-256と一致。
- [不変スナップショット](../data/pareto_snapshots/rf_t005_rf_f003_20261017.json)のRF-T005試験6候補／RF-F003正式4候補に対し、[派生24候補CSV](../data/catalog/phase2_candidate_catalog_20261017.csv)の条件区分とILが一致。元完全ベクトルのGit blob SHAも10/10一致。
- [報告器](../scripts/report_research_pareto.py)は**24候補・比較条件10グループ**を再生成。RF-T005と正式RF-F003は混ぜない。**RF-F003のIL≤0.30dBを達成した候補はない**。公称H2/H3≥35dBも未達。
- 保存済みRF-F003 4GJM候補のchip面積原記録誤記は、原ファイルを変更せず派生スナップショット・カタログの**6⅔**を参照。
- 既存RF-F002 EXP-017の28×7,001点独立MNA回帰もPhase 2 regressionで通過。ただしこれは**旧RF-F002**の保存結果であり、最新RF-F003候補を新たに全格子MNAで再計算したものではない。

## 4. EXP-047の旧manifestを非破壊的に整合

mainに保存された [EXP-047元manifest](../experiments/chatgpt_topology_search/runs/EXP-047/manifest.json)（Git blob `94973b5e5a9e9b0fcd3a3ad9ffd39ea4197475e0`）は、旧形式の**局所in-chat実行記録**であり、現在の標準事前予約・完全実行manifestの9必須項目を欠く。これがStep 1～4の全回帰CIを停止させた既存問題。

- [出典固定の互換overlay](../data/validation/exp047_legacy_manifest_adapter_20261017.json)と[限定アダプター](../src/lpf/legacy_manifest_adapter.py)を新設し、元Git blob SHA・RF-F003実効SHA・bands・固定S2P・記録済み局所探索・元候補JSONの存在を点検した。
- 索引用には`formal RF-F003 / full_lpf / partial / numerical screened / independent passed`を、旧[実験索引](../data/experiment_index.csv)の当時の状態として再現。 [実験証拠インベントリ](../data/experiment_evidence_inventory.csv)は**45件**に更新し、EXP-047の独自形式を`legacy_partial_noncanonical_manifest`で明記。
- **元manifestは不変。** 元コード実行SHA、乱数seed、環境、全候補の収束状態はnull・未確認とし、架空の値を記録しない。`validate_manifest`の一般的な厳格なスキーマ要求は緩和せず、原本は依然として標準manifestの完全条件を満たさない。
- 他のEXPにこの例外を自動適用しない。出典SHAが変われば検査は明示的に失敗する。

## 5. 歴史資料とGitHub-only保全

- mainに存在した56文書は [歴史目次](archive/README.md)、[手法目次](methods/README.md)、[運用目次](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/governance/README.md)から閲覧可能。実際の元文書パスは維持。
- 同一blob 34組・38追加pathは条件／run出典の役割が異なり、Git packの削減見込みに読み替えない。正式RF-F003互換コピーは特に保持。
- 旧46要レビュー資料は元blobが一致し、**46件すべて保全継続**。削除・移動の承認を得た資料は0件。
- GitHub Actionsの期限付きartifactは検証の補助に過ぎず、重要な監査記録はPRのGit追跡ファイルとして保存する。

## 6. 残る確認とマージ判断

**Step 5実行上の検証：完了。** ただし以下を「終わった」とはしない。

1. mainへの実際のPR #67～71の反映：**未承認・未マージ**。内容の重複したPRを無条件に5本ともマージせず、統合PR #71か順次マージかをレビューして選択する必要がある。
2. 古い46件の意味を踏まえた削除可否・ブランチ削除：**別の所有者承認が必要**。今回の処置は保全のみ。
3. 現行RF-F003の全候補に対する同一高密度格子・独立MNA、連続帯域の厳密極値、SRF/Q(f)、公差、EM/物理実測：**未実施・未保証**。
4. EXP-047の厳格な形式への移行は、実行当時のSHA・seedなど不明な情報を埋めない限り事実上の完全復旧ではない。今回の処置は明示的な旧形式互換である。
5. 数値の全域パレート最適性、正式のIL≤0.30dB、公称35dB、物理的な同時結合実現性：**未達・未証明**。

**研究Phase 2のまま。Phase 3移行を実施・許可していない。**
