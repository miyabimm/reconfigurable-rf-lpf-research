# #521 C/D 固定入力診断 — 採用保留、実装未完了

追加承認後の実コード・標準CLI・20 seed比較と最新の採否は [cli_report.md](cli_report.md) を参照。以下は当時の診断記録である。

## 独立レビュー後の追加検証

Issue #521の `74a4c7a` 独立レビューを受け、C単独・D2の深追いはせず、D1/CD1を現行の固定基準インピーダンスで優先検証した。mainは引き続き `7957fd60e685b6afb2f62fcdc1551ab8bdbfc43d`。**新たに現行と同じZでも合成波動層で旧非有限をD1が隠す例が見つかった**。IssueのSTOP差に関する採用保留条件に従い、本番には未反映。実回路到達可能性は未検証であり、現実の回路runでSTOPが変化すると主張しない。

### 固定ZでのSTOP差

`fixed_z_stop.py` / `fixed_z_stop.json` はseed 521で作った、固有値 `I-fullᴴ full` が約 `[0.635, 0.992]` の受動・非相反 `full` と有限の合成 `dfull`、Z=`[50, 60-40j]` を用いる。`power_response(..., check_power=True)` はPASS、外部S21 ≈`-0.46530-0.06441j` と非ゼロ。方向成分を `1e307` 倍した場合、旧packed wave感度のIL Jacは `nan`（既存 `sensitivity_nonfinite` の条件）、D1/D2では約 `+1.6304e308`（有限、同STOPを起こさない）。0.5×/0.8×では両式有限、0.9×〜1.1×では旧非有限・新有限、1.15×では両者非有限。入力・結果と各scaleはJSON参照。これは元の`1e-200 Ω`事例とは異なり**基準Zを変えていない**が、`dfull` は合成で極大であり、現行の回路・部品範囲からの到達可能性は示していない。製品回路や物理実装への主張には使わない。

### 固定9点の追加FD・異常回帰

`real_z_validation.py` はbase/D1/CD1の同じ9 vectorを対象に、全25列の正規化ILと複素S11/S21/S22の独立差分、設定外C方向の複素感度厳密ゼロを比較。境界では2次片側を使い、指定の2刻み `1e-6` / `3e-6` に加え `1e-7` / `3e-7` を切り分け用に実行（追加刻みを指定2刻みの代わりにはしない）。IL toleranceは要求どおり `rtol=1e-4, atol=1e-5`、複素Sは `rtol=1e-4, atol=1e-7`。全成分の最大絶対・許容差換算差と**全失敗**は `real_z_validation.json`。

- 必須2刻みについて、複素Sは全9点・全列で許容差内。ILは`1e-6`全点許容差内、`3e-6`では3 vector・計12サンプル不一致。base/D1/CD1すべて同じ位置で不一致、追加の小さい刻みでは該当IL不一致なし。数値差分の刻み依存と整合するが、要求刻みが全点PASSとは言わない。
- 追加の小刻みでは1020-5000に複素S21で2件、S22で103件の許容差超過があり、base/D1/CD1で同じ位置。丸めの影響と整合するが、原因を断定しない。`1e-6` / `3e-6` の上記結果とは区別。
- `test_issue521_candidate_validation.py` で各候補に既存#499の残存5回帰（2刻み・境界FD含む）と#519の6回帰を実行しPASS、candidate適用中のdeep hook復元も確認。#499の旧2 packed solve注入テストは除き、D1に残るY→S packed solveのraise/NaN、CD1ではpacked solve不在、両候補のinductor感度solve raise/NaNを別途注入しPASS。これらは限定的な故障注入であり全異常契約の証明ではない。
- 成功した追加FD本実行は1836 forward / 128520 samples（baseline算出・候補感度含む）。bring-up 2回は途中で停止（1回目は必須FD不一致をassert、2回目は境界点で負C）、消費forwardの完全な数は未集計。候補Runner・新EXPは0。これらの失敗を隠していない。
- 追加検証後、通常CI相当 `CI_EVENT=workflow_dispatch CI_FULL=true ... scripts/select_ci_tests.py` と保存監査は終了0。ログ `/tmp/issue521-review-ci.log`、監査出力 `/tmp/issue521-review-audit.json` は残存。追加checkout・worktreeは作成していない。

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
uv run --frozen python project/diagnostics/issue521/fixed_z_stop.py /tmp/issue521-fixed-z-new.json
uv run --frozen python project/diagnostics/issue521/real_z_validation.py /tmp/issue521-real-z-new.json
uv run --frozen python -m unittest discover -s tests -p 'test_issue521_candidate_validation.py' -v
```

`real_z_validation.py` は失敗ケースも記録するため、正常終了だけをFD全PASSと解釈しない。固定vector専用生成関数のみを使い通常探索Runnerは呼ばない。

## 初回診断の結論

本番 `src/` は変更していない。**D1/D2は有限の合成入力で既存IL感度STOPと異なる例があり採用保留**。旧式も同例で高精度参照から大きく外れるため、新式のみの問題や実回路での発生を断定しない。C単独は固定vector速度の短縮が明確でなかった。Issueの「固定kernelと実Runnerに明確な短縮がない候補は深追いしない」「STOP差は報告し採用保留」に従い、探索品質runには進んでいない。Dの到達可能性・扱いと追加の数値対策の範囲は独立レビューが必要。**DoDは未達**。RF条件・目的関数・forward・科学的意味の変更や正式EXPはない。

## 固定条件と再現

開始時最新main `7957fd60e685b6afb2f62fcdc1551ab8bdbfc43d`（#520 merge `03f9d89f79d19721991b8be53cebd94fac032924`を含む）。`src/lpf/rf_core/model.py` SHA256 `7c042e891a13f77ecc77f529e7fd630cc9932e362f60d9e2185a6cd1ea0db00a`。RF-T010 trial effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、base RF-T008、#517/#519と同じ4L2C・25変数、6設定・28区間、Search 70、Terminal 476。seed 1001/1010/1020の初期と#519保存3000/5000の計9 vector。vector SHAとplan SHAは `numerics.json` に記録、既存 `issue519/vectors.json` の保存SHAも照合。設定生成の識別子とchecksは `issue517/measure.py::setup` にある。

Python 3.12.15、NumPy 2.5.4、WSL2、Ryzen 7 PRO 4750G、OpenBLAS/OMP/MKL各1、affinity固定なし。共有CPU、周辺負荷未制御。固定kernelは `kernel.py` が**診断用関数のみ**をベースソースから生成・識別し、通常Runnerや本番メソッドを置換しない。候補source各SHA・wall/CPU全計測は `kernel.json`。D2はS11/S21/S22を実際に計算し、ILにS21を用いる。

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
uv run --frozen python project/diagnostics/issue521/numerics.py /tmp/issue521-numerics-new.json
uv run --frozen python project/diagnostics/issue521/edge_case.py /tmp/issue521-edge-new.json
uv run --frozen python project/diagnostics/issue521/kernel.py /tmp/issue521-kernel-new.json
uv run --frozen python -m unittest discover -s tests -p 'test_issue521_diagnostics.py' -v
```

出力は未存在パスが必要。計測結果は環境・外乱により再現値が変わる。`kernel.py` の最初の実行はソース置換位置のassertでforward前に停止、修正後の結果を記録した。

## 数値

9固定点でC/D1/D2/CD1/CD2の全forward S/IL/APL/両RLはbaseと `rtol=atol=1e-12` 比較。dcore・dfullは全4成分、D1は外部dS全4成分、D2はS11/S21/S22を旧式と比較。全点・全方向で最大絶対差は以下（正規化には各bound幅を使用）。完全な点別差とglobal相対差は `numerics.json`。最大cond(A)は32.99。

| 候補 | dcore | dfull | 外部dS（D1全4、D2は3） | 正規化IL Jac | 正規化残差Jac |
|---|---:|---:|---:|---:|---:|
| C | 2.29e-15 | 2.18e-15 | 2.43e-15 | 1.55e-11 | 2.19e-11 |
| D1 | 0 | 0 | 9.31e-16 | 7.28e-12 | 7.28e-12 |
| D2 | 0 | 0 | 8.09e-16 | 9.10e-12 | 1.46e-11 |
| CD1 | 2.29e-15 | 2.18e-15 | 2.39e-15 | 1.64e-11 | 2.32e-11 |
| CD2 | 2.29e-15 | 2.18e-15 | 2.39e-15 | 1.64e-11 | 2.32e-11 |

合成非相反2-portについてC全4成分、D1全4成分とD2の3成分を複素方向差分で検査。異なる複素基準、50Ω、反射ゼロ、伝送ゼロも含む。複素S微分の検査でありdB微分ではない。これらは任意入力の保証ではない。候補の全列回路FD、全異常優先順位、全極端条件は未実施。

### Dの極端有限値とSTOP差

`edge_case.py` に独立に再現。合成 `full=[[.8,.1],[.1,.2]]`、両ポート `z=1e-200 Ω`、`dfull` の全成分 `1e125`（有限）。現行 `power_response` は有限結果を返し、浮動小数点S21は `7.6315e-18` でゼロではない。旧式dS21 `9.5149e108`、IL Jac `-1.0830e127`（有限）に対し、D1/D2 dS21 `-2.0238e293`、IL Jac `+inf`（非有限STOP）。当該変換の `cond(a)` ≈1.53 だが、極小Zで `delta-S beta` が桁落ちする。

実数450桁Decimalによる別の暗黙微分参照（`(delta-S beta) dF inv(a)`、forwardも高精度で再計算）は S21 ≈`3.721e-203`、dS21 ≈`3.236e-77`。**旧forwardと旧感度も高精度参照から非常に離れる**。参照は十進入力でありbinary64入力の厳密値ではないが、この桁違いを説明する差ではない。結果は高精度の妥当性の確認であって現行STOP契約の変更根拠ではない。#419のpower-wave極端値に関する契約差も参照。この例は合成wave層であり、実際の回路・固定S2P・RF-T010の基準インピーダンスとパラメータ範囲から同じ `(full, dfull)` に到達できることは未検証。両式が異なるSTOPを返す可能性を示すもので、本番回路でのSTOP変更を実証したとはしない。

## 速度・消費

9点それぞれwarmup後、baseとの交互20ペア、plain全評価（deepなし）。下記は各点の対応wall差中央値の中央値［9点の最小、最大］ms、負が候補の短縮。全pairの外れ値をJSONに保持。数値・STOP差判明後のkernel時間は参考値のみで採用根拠ではない。

| C | D1 | D2 | CD1 | CD2 |
|---:|---:|---:|---:|---:|
| -0.002 [-0.021,+0.097] | -0.078 [-0.174,-0.046] | -0.056 [-0.096,-0.022] | -0.093 [-0.137,-0.051] | -0.084 [-0.136,-0.049] |

ペア全体のC差範囲は-7.72〜+2.07 msで外乱あり。Cに明瞭な改善なし。D1とD2の速度差は非対応の測定群であり優劣確定には不十分、いずれもSTOP差で保留。実Runner計測・校正・20 seed品質・MNA・収束比較は**未実施**。従って実Runner短縮、探索品質やRF適合は主張できない。

固定kernel 1899 forward / 132930 samples（warmup・比較含む）、数値比較で本番感度forward 9 / 630 samplesと別途9回のnode/感度計算、合成wave・差分テスト。テストのforward/sample消費は未集計。Runner、checkpoint、正式EXPは0。

## チェックと残課題

- 新診断test 3、既存#499感度6、#519感度6はいずれもPASS。#499/#519は**baseline**のテストであり候補のSTOP/全列FD PASSではない。deep hook復元もbaselineのみ。
- `CI_EVENT=workflow_dispatch CI_FULL=true ... scripts/select_ci_tests.py` 終了0、保存監査 `audit_new_experiment_storage.py audit` 終了0（既存個別記録のvalidation状態を変更・認定するものではない）。CI log `/tmp/issue521-ci.log`。
- 将来の検討: 実際に許されるZ・回路での到達性、旧新STOP同等性・高精度参照を含む境界、Cの再測定要否、Dを解決できる契約維持の最小式。owner/技術リードの判断なしに対象外のRF条件・契約の緩和はしない。
- worktree/追加checkoutは作成していない。上記CIログは `/tmp/issue521-ci.log` に残る。新EXP、実測、EM/SRF/Q(f)、連続周波数、物理実装は未検証。
