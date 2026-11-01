# Issue #243: DE探索用の部品存在・roleの評価境界（mock限定）

- 基点 main `e819314fc6880f2c64bad8403540ee254ebe00f9`。
- 変更はユーザー指示による**探索時の取扱い**であり、正式RF-F003・trial RF-T008 rev3の数値・接続条件、保存済みEXP/SLSQPを変更しない。
- RF-T008のGJM01（固定chip C）は最終的な搭載部品なら `C>0` のまま。ただし**明示された探索評価だけ**、`C=0` は0アドミタンス（固定C枝非搭載の代理表現）として評価してよい。
- `NominalCircuit.validate_components(..., allow_absent_gjm=True)` はRF-T008限定の評価検査。ゼロのGJM01に対して `component_policy_pass=False`、`exploration_absent_gjm_indices`、`absent_gjm_requires_topology_redefinition` を返し、候補昇格はできない。既定の `validate_components` は0を引き続き拒否。
- `generate_starts(..., for_exploration=True)` と `make_seed(..., for_exploration=True)` のみ、GJM01の開いた下限とL-treeだけでは証明できない`series`宣言を探索時に許容する。既定3-startの生成・完全SHA・順序は変更しない。未証明roleは別途監査結果として残り、実装や候補昇格の根拠にはならない。
- `PhysicalComparison.evaluate(..., for_exploration=True)` でRF-T008の0 GJM01と未証明roleを許容する。DE mock adapterはこの経路を使用する。0以外のL/C/k・PCB_Lのゼロ・非有限値・SPD・部品数・接続スキーマなどは従来どおり厳密に検査する。H2/H3厳密30dBのRF制約は変更しない。
- DEの `best_observed` に、ゼロGJM01の元固定Cインデックスと`requires_topology_redefinition`、role証拠状態、昇格禁止を記録。辞書式ランクや科学的合否・部品面積・トポロジー識別子を書き換えない。
- **本Issueで枝削除後の新しい回路定義生成・warm-start変換・再最適化は実装しない**。最終的にゼロなら別トポロジーの問題を明示的に構成し、再探索、RF/面積/独立MNA/パッシビティを検査する。0のまま搭載GJM01として記録しない。
- これはsynthetic/mock境界テストとコード修正のみ。実RF探索・新EXP・本番runner/自動変換・新RF数値の採用、科学的PASS判定は`not_run`。
- 既存コードが`for_exploration`を指定しない場合は、従来どおり厳格な最終部品検査とroleによる探索中断を保持する。後方互換のため意図的に明示opt-inとした。
