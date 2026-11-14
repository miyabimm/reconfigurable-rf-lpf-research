# Issue #425 — decode周辺の重複処理

## 判断と範囲

**簡素化として採用候補、Draft PRで独立レビュー待ち。速度改善や大きな退行の不存在は、この外乱の大きい測定だけでは確証できない。** 数値vectorはdecode後のencodeを省く一方、直接の`CircuitValues`は従来どおりencodeでschema・設定間固定値を検査する。`take`のfloat変換を取り除き、既存の公開`CircuitValues`構築・検証に委ねた。RF演算、制約、探索は変更していない。特別なtrusted経路やcacheはない。正式EXPではない。

- 着手時main `c927cb94fba14f97601026d9523b3eed3101e423`（#421マージ後）。測定時の実装HEAD `d6dc192340cc2ae1921164663e43e4e1cfea3c40`、RF source identity `babba9a30417f14b27985c8bf61b8dc31c6d9a5c204eadbac9263a3fd5042afe`。3回目の測定時はテスト追加のみ未commit、RF source identityは同一。旧methodは固定mainからGitで取り出して元moduleのglobalsでコンパイルし置換、新は本番methodそのもの。旧はmain checkout全体の実測ではないが、他のRFコードは共通。
- RF-T008 rev3 **trial opt-in / full_lpf**、effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。active formal RF-F003は `e12c42b11d12db7f20983c48cfa441ea96e362e533450d5862aa8a271c82af86`。正式条件への一般化ではない。
- #410固定100 vector（入力SHA `e87355eb364073a5743062e8e4ee7c90c3012cbfb5e38bef6283860381736ba0`、各vector SHAも照合）。seed 1002、start vector SHA `6203467121a4e37baaa51c471aaecb3174f3374f9ab955d6fbf101f7b5ce935f`、starts file SHA `63b671ea269656843df118230b7d920e91515188235809b6dd0efd667ac997ab`。25変数、6設定・28別interval・70点、mandatory_g 42。Plan SHA `8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e`、grid SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`。生成条件は[Issue #413](issue413_report.md)。
- bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、固定入力S2P `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、出力S2P `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。

## plain計測

fresh processごとに100回warmup後、同じ100 vectorをdecode単独は20周、完全`RFEvaluator.evaluate`は1周まとめてwall/CPU計時。各方式warmup process 1個は集計外、10 pair、順序交互。計器付き内部区間を速度換算していない。CPU affinity 2、BLAS/OMP/MKL各1、WSL2共有host Ryzen 7 PRO 4750G、Python 3.12.15、NumPy 2.5.4。専有・温度・周辺負荷・電源制御なし。

下表はms/100 vector、pair差は新−旧、warmup除外。CPUも同傾向だが**全3スイートの138run（各46run）**のwall/CPU、setup、warmup、旧新実行順序、全外れ値、ソース・入力指紋および同値性のshape/max差/bit一致は[統合compact原記録](issue425_timing_compact.json)に保存。選別していない。共通メタ情報だけを1回格納し、各runの実測値は元のfull rawと同じ値を保持。

| 回 | 経路 | 旧/新wall中央値 | pair差中央値 [最小,最大] | 新が速い |
|---|---|---:|---:|---:|
| 1 | decode | 6.375 / 6.142 | −0.180 [−1.182,+0.401] | 8/10 |
| 2 | decode | 6.330 / 6.241 | −0.103 [−1.685,+0.101] | 7/10 |
| 3 | decode | 6.439 / 6.310 | −0.111 [−3.870,+2.395] | 8/10 |
| 1 | forward | 72.051 / 56.648 | −10.802 [−26.772,+0.506] | 9/10 |
| 2 | forward | 54.699 / 62.704 | −1.109 [−24.501,+16.479] | 6/10 |
| 3 | forward | 47.161 / 47.683 | +0.385 [−3.095,+3.899] | 4/10 |

forward初回の異常な差は変更量に比べ大きく、再測定でも方向・分布が安定しない。共有hostの外乱が疑われるが原因は未特定。3回目の中央値は小さな逆方向で、大きな退行を示す安定した証拠も、退行がないことの確証もない。decodeの微小な差もノイズと重なり、一般的改善率は主張しない。必要なら負荷制御可能な環境で再検証する。

## 数値と検証

各回の旧新100 vector × 70点、外部ポートSの4複素要素、IL/APL/両RL、worstIL、mandatory_g全42要素、encode結果、6行Cはいずれも最大差0・ビット一致。各回旧新それぞれ代表0/49/99の全70点を独立branch-current MNAで比較し、固定S2P・複素負荷、受動性、枝損失・電力保存を検査。最大誤差 `2.2134e-12`、許容絶対 `1e-9`。全入力STOPなし。有限入力に対する検査であり全入力・連続周波数の証明ではない。

回帰：`test_issue309_rf_core.py` 8、`test_issue410_c_assembly.py` 5、`test_issue421_schur.py` 3、`test_phase2_branch_mna.py` 6、`test_phase2_numeric_diagnostics.py` 3、`test_phase2_generic_coupled_lc.py` 2、`test_issue415_production_stamps.py` 3、`test_rf_f003_t005.py` 6、`test_issue307_constraints.py` 5、`test_trial_ic_fixed_c_t008.py` 9、`test_ci_test_selection.py` 16、各PASS。新テストの初回追加後、整数vectorの結合係数を1にしたためSPDエラーになったが、0に修正して再実行PASS。storage auditは正常終了、EXP-058 running、EXP-116/117 preservation_incompleteを含み、全EXP完全性PASSではない。CIと独立レビューは別ゲート。

3回合計、forward 13,800（warmup process・各process warmup・比較capture含む）、requested samples 966,000、独立MNA 1,260 samples。decode単独 138,600呼出（warmup含む）。これらに単体テストを含まない。EM・SRF・Q(f)・公差・実測、物理実現性および連続帯域保証は未検証。

## 再現

```bash
uv sync --frozen
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --frozen python project/diagnostics/issue425_benchmark.py --output /tmp/issue425-new.json --pairs 10
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --frozen python -m unittest discover -s tests -p test_issue309_rf_core.py -v
```

出力は未存在のパスを指定し、affinity CPU 2が利用可能であること。driver SHA `69889a05496276f53d40d5db437a59ed29ffed5c83ce44629d8f21a148c04da2`。

**保存形式の整理（測定・RF実装・結果は変更なし）：** 旧full raw 3ファイル（計3,214,921 bytes／各46run）は共通provenanceの毎run反復を除き、1個の[compact JSON](issue425_timing_compact.json)（108,804 bytes／全138run）に統合。旧rawとcompactの対応はrun単位のwall/CPU、setup、warmup、順序・失敗状態、MNA、同値性について照合済み。統合後SHA256 **`be83b75da0a9b00133b01b29cf966d32f9b112099045ff76702db2015e1c4862`**。元のfull rawは本PRの修正前commit `dff19bc2db8c8ea33d7a6eddad2db2372321def7` のGit履歴から追跡可能。元raw SHA256（初回/2/3）は `ab4788fdeb14e5bc7fb11ebdca579dec16496f3c7bdc7708e5a6d7302a54e010` / `93c22379ac4df38e46f72c31eedbeba46d12a0677648bfb02246a626145abb0a` / `da6b99be4e7e89b88a8b601af8a1f2ad4462dfc983e2d6bfc3afb757626df0e9`。元提出HEADのGitHub Actions smoke [run 43581771669](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/43581771669) はPASS。
