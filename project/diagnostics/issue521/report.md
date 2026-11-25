# #521 C/D 固定入力診断 — 採用保留、実装未完了

## 結論

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
