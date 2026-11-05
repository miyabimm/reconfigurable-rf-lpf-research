# Issue #311 — Stage 3 性能要求・区間別評価・共通順位

## 実装契約

- `search.performance.compile_requirements(policy, bands, mode='full_lpf')` は
  schema 2 の宣言のみを読む。bands は CSV path または元行順の CSV 辞書列。
  既存 band validator の6設定順と28行の意味検査を再利用する。
  行IDは `csv:<ヘッダを含む1起算行番号>:case:region:type:note`。
  `segment` は Stage 2 の0起算行順を維持。B13/B14や周波数ギャップを統合しない。
- selector は case/region/note/type の文字列のAND一致。defaults の同一区間×指標×level
  の重複を拒否。overrides は既存defaultの同じキーだけを置換（方向も置換可）。
  margins の形式は `{selector, lower_mhz, upper_mhz}`、直接拡張のみ。
  未知・ゼロ一致・競合・非有限・負のマージン・S2P範囲外を停止する。
  対応指標/上限/下限を合成テストするが、実制約の閾値は追加・変更しない。
- `evaluate_requirements(response, requirements, *, requested_grid)` は **別途凍結済みの
  要求格子**を必須とする。Stage 4 の格子生成は未実装。応答の格子との完全一致、
  区間/設定帰属、全アクティブ区間の存在、重複sample、shape/NaN/未定義dBを検査。
  通常区間の密度や端点をPython側で強制せず、要求格子の全sampleを評価する。
  T006追加区間だけはJSON指定の両端含む全点を検査し、端点だけなら停止する。
- STOPは `ValueError`。未評価を有限のmandatory FAILに変換しない。
  正当なゼロ振幅の `+inf` は維持（該当するS振幅がゼロかを照合）。
  attenuationは外部transducer powerの `il_db` そのもの。
  各要求に全sample index/観測/残差/合否、argworst、違反を記録。
  必須残差のみ `mandatory_g=-e` に格納。nominalは報告のみ。
- 全必須PASSを優先し、PASSはworst IL→完全vector SHA、FAILは区間別必須の
  Vmax→Vsum→worst IL→SHA。`rank_candidates` は既存 `validate_values` を再使用し、
  非合法/未実行/数値失敗を比較集合から分離。異なるpolicy/mode/grid/要求を比較拒否。
  RFResponseはxの識別子を持たないため、呼出元が応答と完全vectorの対応を保証する。
- 合否は有限要求格子・指定mode内のみ。matching_onlyをformal full-LPF PASSと呼ばない。
  RFコアから性能層のimportは追加しない。旧scalar/score/rank経路は保存し、新経路では不使用。

## 検証と範囲

新規テスト `tests/test_issue311_performance.py` は、現役5条件×2modeの展開、
selector/override/margin/未知形式、各指標の上下残差、nominal分離、正当なinf、
欠損/誤帰属/NaN、T006完全格子の必要条件、辞書式順位と比較拒否を検査する。
既存RFコア接続はF003の56sampleだけ。T006の18,006sampleは**合成応答配列のみ**であり、
実RF scanではない。厳密 `e<=0` 判定で、合否用数値許容差はゼロ。
合成Vsumの小数演算確認はunittest `assertAlmostEqual` の既定7桁。

再現コマンド（BLAS各1スレッド推奨）:

```sh
uv sync --frozen
uv run --frozen python -m unittest discover -s tests -p test_issue311_performance.py -v
# sparse checkoutで実行（historical dirsがあるcheckoutでは専用境界テストが失敗する）
PI_SPARSE_RF=1 PYTHONPATH=tests uv run --frozen python -m unittest -v \
  test_constraint_versioning test_issue307_history test_issue307_snapshot_equivalence \
  test_issue307_constraints test_issue309_rf_core test_issue311_performance \
  test_phase2_s2p_grid_cache.Phase2S2PCacheAndGridTests.test_28_segments_six_settings_and_frequency_endpoints \
  test_pi_sparse_rf
```

通常smokeとsparse CIに新規テストを追加。実行HEAD・件数・CI URL/結果はDraft PRに記録する。
初回ローカル確認では既存docs/data/experimentsディレクトリがあるためsparse境界検査が失敗。
また既存dependency allowlistがband validator再利用を拒否したため、`_grid` を明示追加した。
歴史ディレクトリの削除/改変による回避はしない。
初回通常CIでは既存の `src.lpf` scalar importに対し、新しいトップレベルの
`lpf` importが干渉して停止。RFコア型importを新API内へ遅延し、scalar側は相対importに
修正。隔離subprocessでリポジトリrootだけをsys.pathに追加する回帰テストを追加した。

RF ID/effective SHAは `rf/constraints/registry.json` の現役値を維持。
F003: `e12c42b11d12db7f20983c48cfa441ea96e362e533450d5862aa8a271c82af86`。
新EXP、本番最適化、T006実RF全点scan、独立dense検証、連続帯域/物理成立認定、
solver/Runner/格子生成の接続は未実施・対象外。独立レビュー前にmergeしない。
