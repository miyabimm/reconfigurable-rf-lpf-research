# Issue #254：共通curated保存改修と容量STOP

## 結論

**#250の本番再開はSTOPのまま。例外未申請・未承認。** 最小の重複削減を実装したが、
科学証拠を保持した全容量は512KiBに収まらない。追加の抽象化や証拠間引きは行わない。
この報告はmock/templateの保存容量検査であり、RF適合・G0/G1正式固定・科学的検証ではない。
新EXPの作成、番号予約、実SciPy pilot/remaining、歴史的証拠変更は実施していない。

## 実装と不変事項

- `experiment_run._curated_result`：G1のactual ID・input_source SHA・完全C1 SHAを参照。
  stage入力／出力がseedまたは過去outputとcanonical JSONで完全一致する場合だけ後方参照にする。
  不一致のベクトルは全桁のまま保持。最後の完全L/C/k/6設定CvはG1のdefinition/schemaと
  `restore_curated_result(curated, input_source)`だけから復元でき、rawを必要としない。
  全stageのstatus/message/nit/nfev/maxiter・warm-start・例外・controller/recovery・費用は保持。
- `_package`：G1にある73 logical→58 actual／方式・seed対応表とscreen費用をsummaryに複製しない。
  summaryにG1 SHAと実行identityを保持。Paretoの除外理由や失敗・未収束行は削らない。
- `checkpoint_io.atomic_write_json(..., compact=True)`は今回のmulti-start curated証拠だけに適用。
  既定のindent=2／従来1-start APIは不変。compactでは非有限値を拒否し、sort/UTF-8/fsync/atomic
  replaceを維持。保存後JSON readbackと既存file SHA／Git HEAD byte監査を使用する。
- raw/in-progress/STOP、ソルバー、RF条件、初期値、数値精度、予算、選別ポリシーは変更しない。
  従来checkpointの完全candidate_recordも変更しない（ここが依然大きい）。

## 同一58 start・旧／新の全容量実測

旧実装はmain `a39e26c4742f3e4e383743699410145e12b5e971` の `_package` を直接ロード。
`project/experiments/issue250.yaml` と既存 `results/issue250/frozen-plan.json` を使用。
新旧に**同一の全58結果**を入力。通常2stage／救済4stage、各stageでLを0.0001変更し、
同一outputだけの過度に圧縮しやすいケースを避けた。seedは実58 startの完全C1をそのまま保持。
forwardはIL=0.25/H2,H3=36の定数mock、C1 replayは保存済みrecordを返すmock。
**元C1の実RF replayを検証したものではない。** optimizer evidenceはsynthetic_callback。

同一面積／同一mock ILの58点は全て非劣点になる合法な保存上限ケースを採用した。
`top_k=5`はPareto必須点の切捨て上限ではない。pilotから残るcheckpointもこの58件に含む。
17点は58件、dense1001と独立MNA/power/SPD/passivityは15件。
各overlay templateは全28個別区間の周波数境界・極値・極値周波数、入力vector SHA、
G1 SHA、source/environment、独立誤差・SPD最小固有値・電力／受動性誤差欄を含む。
全て `template_only=true, status=not_run`。未実施の値欄はサイズ用の仮数値である。
全点波形／iterationは未追跡C扱いで容量に含めず、A/B証拠の代用にしない。

| bytes | 通常・旧 | 通常・新 | 救済・旧 | 救済・新 |
|---|---:|---:|---:|---:|
| manifest.json（完全G1とoverlay refs） | 300,842 | 181,518 | 300,841 | 181,517 |
| run_summary.json（全58結果・Pareto） | 691,481 | 321,869 | 1,027,285 | 479,093 |
| storage_record.json（全証拠分類） | 33,643 | 27,375 | 33,643 | 27,375 |
| checkpoints 58件 | 2,782,052 | 1,604,710 | 3,711,130 | 2,067,642 |
| 検証overlay template 88件 | 678,326 | 480,678 | 678,326 | 480,678 |
| **全体** | **4,486,344** | **2,616,150** | **5,751,225** | **3,236,305** |
| **524,288B基準に対する残量** | **−3,962,056** | **−2,091,862** | **−5,226,937** | **−2,712,017** |

- 単一ファイル1,048,576B境界：4ケースともPASS。最大は各summary（上表）。
  旧救済の余裕は21,291B、新救済は569,483B。
- 131,072B個別soft：全ケースのmanifestとsummaryは要レビュー。他の各ファイルはこの閾値以下。
- EXP全体524,288B：**4ケースともFAIL**。通常・新もmanifest＋summaryだけで503,387B、
  残り20,901B。救済・新はこの2ファイルだけでも660,610Bで超過。
- 数値の丸めや計算／診断の削除で合わせていない。時刻・CPU/wallは実測値を全桁保持するため、
  再実行時のbytesは数十B程度変動し得る。これは将来の実結果サイズの上限保証ではない。
  仮messageやoverlay以外に追加のA/B証拠が必要なら、その分を更に加算する必要がある。

#250コメントの534,287/873,120B（actual_results断片）および259,400B（G1断片）は
全証拠集合ではない。今回の表は旧実装の実summary／checkpointまで生成した別の完全比較であり、
その過去断片のbytesと同一だとは主張しない。断片形状だけの追試もresultsに保存したが、
完全な保存判定は上表を使う。

## 出力・再現性

成果は新EXPではなくGit管理外の `results/issue254/` に保存：

- `size_mock.py`：使い捨てmock容量スクリプト（科学実験runnerではない）
- `baseline_experiment_run.py`：上記mainの旧ソース
- `implementation.patch`：計測時dirty差分
- `normal|recovery/full-results.json`：比較用完全結果、A/Bへ昇格しない
- `normal|recovery/old|new/`：manifest/summary/storage、58checkpoint、88template各ファイル
- `size-report.json`：**全ファイル個別bytes**、集計、入力SHA、patch SHA、復元件数
- テストログ、保存監査ログ。raw相当・full比較用結果はGitのEXP容量へ算入しない。

計測時input_source SHA：
`0f3277333bb201a264789ad94a0d71580ee2829e25dc4d9d00e55bc468288463`

計測時patch SHA：
`81ff5073677fbf3ade1674156b76ec06caba3391dff1e79834246308347c74dd`

mock script SHA：
`b71dd0ed042eb7f9a59286d485d5bbbe02dcfbc911abd439c3e6d403d5d75a95`

size-report SHA：
`aa706a7b8fd30f0ab5e7e3f20578595b70be5654c4fe6c54e56f22061a4942d7`

使い捨てscriptと全ファイルbytesは[Issueのレビュー用コメント](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/254#issuecomment-6574636273)にも保存した。
同一の準備入力を確保した環境で `uv run --frozen python results/issue254/size_mock.py`。
G1を実行したり、実RFやSciPyを呼び出したりしない。予約・Git auditはこのmock出力について
意図的に実行しないため、template集合をG3/G4 PASSと呼ばない。

## 検証と未実施

- 旧／新全58件×2stage/4stage：G1＋curatedのみで旧curated全辞書との完全一致をassert。
  数値／入出力／seed／stage順／controller／status／費用／原因を丸めず照合。
- 既存共通テストにchanged vector・後方参照・通常／救済／status8／数値例外・
  予算停止・G1/SHA改竄・未来参照拒否・compact readback・非有限値時の元ファイル保護を追加。
- sparse CIと同じ16モジュール **136 tests PASS**（限定の既存SciPy smokeを含むが本番ではない）。
- 保存監査ユニット **15 tests PASS**。
- 完全checkoutで `audit_new_experiment_storage.py audit` **PASS**：63既存EXPの形式／byte監査。
  既存RF数値の再計算ではない。
- 一時Git remoteを使う共通テストでpilot→remaining→resume/no-op、checkpoint再検査、G0/G1、
  実HEAD byte finalize、保存監査、finalized再実行拒否をPASS。STOP／未知中断はfail-closed。
- 実58 startの本番pilot/remaining、17点/1001点／独立MNAの科学検証、G1正式固定は**未実施**。

## 次の判断

このままでは本番保存容量ゲートを通らない。512KiB基準や監査判定は変更していない。
ownerが容量例外を選ぶ場合は、実際の追加A/B証拠も含む見積りをレビューし、
`storage_record.size_exception` に明示承認URL・承認者・理由を記録する別工程が必要。
別案はcheckpoint内の完全candidate_record等の重複削減だが、既存読者・検証契約への影響があり、
ここでは追加schema／抽象化を重ねずSTOPする。独立レビュー前にmainへmergeしない。
