# Issue #237 / Stage 9B-1b：物理座標と正規化座標の9ペア対照

## 結論（限定的観測）

**18 start / 38 stage を一度だけ実行した。数値収束は A=7/9、B=8/9、17点/区間の厳密H2/H3≥30dB適合は両方式とも0/9。**
正規化を標準採用する根拠や、初期値非依存性・大域最適性の証明ではない。
Bは物理有限差分幅も変えるため、座標変換だけの純粋な因果効果とは呼ばない。
Phase 2のまま、9B-2/9B-3は未実装・未実行。

## 条件と出典

- Issue: <https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/237> とユーザーのPi Code起動指示。
- 着手main: `6ddc3deca86af9674d3167035397d59315c8cec3`、postmerge CI [41274578450](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/41274578450) SUCCESS。
- 明示trial **RF-T008 rev3 / full_lpf** / effective SHA `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`。
  active formal RF-F003は不変更。外部input→output、source50Ω/load60−j40Ω、固定外部S2Pの全cascade/SHA、6設定・28不連続区間、部品/Q/結合/SPD/面積モデルを維持。
- A=`coordinates="physical"`、B=`coordinates="normalized"`。どちらも `finite_difference_eps=None`。
  SciPy1.18.1の既定絶対eps=`1.4901161193847656e-8`（各座標単位）、ftol=`1e-6`不変更。
  Bの物理変数の差分幅はbox幅倍、tは両者ともdB。固定座標は固定のまま。
  新guard、30.005dB余裕、可行化、適応格子、格子再最適化、別seedは導入しない。
- EXP-086〜094の保存済み完全初期値をread-only使用。生成し直さず、保存seed（t含む）を再現・SHA照合した。
  [pairs.json](pairs.json) に旧manifest byte SHA、topology/definition/vector/seed SHA、完全seed、A/B予約番号を事前固定。
- 実行ソース `e1a29ac03d54dc451daf0118dad217a0beb5aac8`（pairs/reportの `execution_source`）。
  科学モデル・SLSQP本体はmainと同一。既存driverの `partial(scipy_slsqp_stage, ...)` 出典分類だけを修正し、関連6テストPASS後にG1を固定した。
- Python3.12.15 / NumPy2.5.4 / SciPy1.18.1 / frozen uv。
  `OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=1`、uv.lock SHA・OS・uv版は各manifest。

## 予算と方式別結果

既存v2：粗2点240→精3点120、停止理由に応じた既存回復だけ、最大4stage/start。
全体上限18start/72stage。stage境界協調timeout300秒/start（SciPy内部の強制killではない）。

|指標|A：物理|B：正規化|
|---|---:|---:|
|planned / attempted / not_started|9 / 9 / 0|9 / 9 / 0|
|converged / nonconverged / failed|7 / 2 / 0|8 / 1 / 0|
|17点H2/H3厳密30dB適合|0/9|0/9|
|部品/接続role/box/全L行列SPD|9/9|9/9|
|stage数|18|20|
|nfev（SciPy目的関数評価回数）|12,206|10,312|
|driver内実時間合計（秒）|11.809|20.872|
|optimizer stage実時間合計（秒）|7.776|16.987|
|既存v2の回復start|0|1|
|追加retry / timeout / STOP / exception|すべて0|すべて0|

BのEXP-100のみ粗status8→精status0で、既存v2の同予算ウォーム再始動（粗240/精120）を1回実施、status列は8/0/0/0。
反復上限救済は0件、予算増額なし。他は各2stage。
同じ初期値・同じv2予算規則であり、実際のstage/nfev消費まで同数に強制した比較ではない。
実時間は同一環境での各driver呼出し内計測であり、保存・Git・17点再評価時間を含まない。
短時間・単回・非ランダム順の観測で、速度の統計的比較や純粋な座標変換効果の証明ではない。

## 9ペア（17点/区間・全6設定）

下表の損失はtではなくforwardのworst IL。全精度H2/H3・残差・時刻・vector差は [report.json](report.json)。
`最大負残差` は別列で harmonic-only と passband epigraphを含む全残差を保存する。
厳密30dB判定は丸め前で行い、表のIL表示丸めでPASSにしない。

|pair / 旧EXP|構成|新A / B|status A / B|IL A → B (dB)|17点厳密30 A/B|
|---|---|---|---|---:|---|
|1 / 086|3L0GJM|096 / 095|8,8 / 8,8|7.950033417043 → 26.507351757752|FAIL / FAIL|
|2 / 087|3L0GJM|097 / 098|0,0 / 0,0|1.361978466421 → 1.361978459638|FAIL / FAIL|
|3 / 088|3L0GJM|099 / 100|0,0 / 8,0,0,0|1.361978466146 → 1.361978468325|FAIL / FAIL|
|4 / 089|3L1GJM|101 / 102|0,0 / 0,0|1.120318970880 → 1.120249721237|FAIL / FAIL|
|5 / 090|3L1GJM|103 / 104|0,0 / 0,0|25.605759763818 → 29.513320013326|FAIL / FAIL|
|6 / 091|3L1GJM|105 / 106|0,0 / 0,0|31.148088710033 → 23.448542342637|FAIL / FAIL|
|7 / 092|4L0GJM|107 / 111|0,0 / 0,0|8.069326667902 → 14.640609338454|FAIL / FAIL|
|8 / 093|4L0GJM|108 / 109|4,4 / 0,0|30.203757366032 → 3.322520673494|FAIL / FAIL|
|9 / 094|4L0GJM|110 / 112|0,0 / 0,0|1.110074108221 → 1.110073643164|FAIL / FAIL|

- Aは同条件の保存済み#233結果（status/nfev/forward IL）を再現した。旧実験を再実行・改変したのではなく、予約済みの新A EXPである。
- pair8のBは数値収束したが、H3最小 **29.996923233368015dB**（17点）でstrict FAIL。
  coarse/fineでのsolver successをRF適合に置換しない。
- pair3のBは回復後もH2 **29.999999999956906dB**。不足が小さくてもFAIL。
- pair1、5、7ではBのILが悪化。pair6、8では改善したが高損失/厳密不適合が残る。
  nominalのpair2、4、9の変化は微小。この9ペアから一般的優越性は主張しない。
- 非収束の巨大負tを物理ILと混同しない。特にA/EXP-108の全残差不足は約5.15e16dBで、回路の減衰ではなく破綻したepigraph変数に由来する。
- 最終物理vector差はL/C/kの完全座標別にB−Aで保存。混合単位のmax値と、box幅で割った無次元max値を分け、t差は別に保持。

**17点strict30適合候補ゼロのためdense1001/区間・独立MNA84・power/passivityは全件 `not_run`。**
受動性・電力・独立解析ゲートを緩めたのではなく、今回の実行対象にならなかった。
部品/SPD/接続検査PASSは、実装可能性やsigned kの実現性の証明ではない。

## G0–G4と保存証拠

1. 完全checkout（sparseでないこと・全tracked data/experiments存在）と最新mainを確認。
   中央台帳18件を既存予約workflowで確定、全18 Actions SUCCESS、push/fetch readback後のmainは
   `ee769bd`（完全SHAはpairs/gates）。番号は予約完了順なのでA/Bやpair順と一致するとは限らない。
2. 全18 planned manifest/storage/index と9ペア対応表をG1 commit
   **`64401192de43203ca15ff0591cb65456b1a21d2d`** でpush。
   GitHub Contents APIから全変更fileの実byteを再取得・照合してから、全18件の `prepare_one_start`/preflightと完全seed一致を確認。
3. 各EXPは既存 `run_one_start` を1回だけ呼出し、原子的rawを保持。
   17点overlayを別証拠として保存、既存 `finalize_one_start` の2commit/HEAD byte読戻し・保存監査、index更新、push、GitHub API byte読戻し後に次startへ進めた。
   [gates.json](gates.json) に各remote HEADとファイルSHA、G0/G1/G3の観測証拠を保存。
4. 各原manifest/storage/run_summary、全stage入出力/status/nit/nfev/時間/例外欄、17点overlayを保存。
   stage証拠・完全vectorはrun_summary/overlayにあり、checkpoint選抜は全件0。
   `storage_record.stage=complete` は保存完了のみ、RF PASSではない。
   overlayの `status=passed` はread-only scanの実行成功、RF判定はreportの `strict30_17=false`。
5. 新18索引行だけを追加・更新し、既存行のbyte prefixを維持。EXP-086〜094その他歴史manifest/結果、RFファイルは不変更。
   raw `results/EXP-095..112/run.json` は削除していない（G5なし）。

再現用の限定手順は [procedure.py](procedure.py)（汎用runnerではない）。
`prepare` は保存済み入力からG1を作り、既存ディレクトリがあれば拒否する。
`check` はplanned時だけ、`run EXP-NNN` は当該1startだけ、`overlay EXP-NNN` はread-only再評価。
集計のread-only再現は `OPENBLAS_NUM_THREADS=1 PYTHONPATH=src:. uv run --frozen python data/validation/issue237_coordinate_ab/summarize.py`。
**既存rawへの再実行は禁止**。再現とは既存証拠の読戻しとforward再評価を意味し、新規最適化には別の予約・承認スコープが必要。

## 実際のチェックと限界

- `uv sync --frozen` PASS。
- `test_phase2_shared_entry.py` 6件PASS（SciPy partialの出典誤分類に対する回帰1件を含む）。
- G1全18 prepare/preflight、G3全18 finalize・保存監査・remote byte readback PASS。
- G4全件監査・最終remote readback・CIはPRの実行結果を参照（実験結果からCI成功を推定しない）。
- 一般 `experiment_manifests.py index` は既存EXP-047のlegacy形式で失敗した。既存adapter/索引契約に従い、新18行のみ既存生成器で作って歴史prefixをbyte保持した。歴史manifestの修正はしていない。

17点は有限forward診断であり連続帯域保証ではない。Q(f)/SRF/EM/温度・公差・実測・実面積は未確認。
歴史的良好解との異格子/guard/接続によるPareto順位混合は行わない。
科学的受容・実装成立、CI成功、保存監査PASSは別判定。

## 次の9B-2 Issue案（提案のみ、未承認）

「RF-T008：固定9初期値での限定可行性回復」：まずforward-onlyで今回の失敗を
(a) 巨大負t/局所探索失敗、(b) strict境界直下、(c) 区間内部の見落としへ分類する。
可行性回復を実装するなら、残差尺度・回復目的・停止条件・追加予算・初期値・比較対象を事前固定し、
既存30dB評価/ftol/guard/評価格子と分離する。今回の正規化Bを無条件な新標準にしない。
同じseedと同じ合計予算でstrict30適合、IL、最大負残差、solver status、nfev/時間を別々に比較し、
dense/MNA/powerの昇格ゲートを維持する。適応格子9B-3は混ぜない。
**本PRで回復アルゴリズムの実装・追加EXP・予算は承認も実行もしていない。**
