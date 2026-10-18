# EXP-049 — RF-T006の面積拡大と最悪IL 1.1dB探索

**2026-10-18、Phase 2・計算実行完了。試験条件RF-T006でのbest-found、目標1.1dBは未達。** RF-F003正式条件やRF-T005の旧候補は変更していない。新実験IDは探索着手前にmain `02282bfdb53660ac670b901ef4f20a97271562f4` で予約し、Actions内でもorigin/mainを照合した。探索開始時の正本mainは上記commit。

## 条件と探索方針

RF-F003基準の最大2個の独立IC可変C、固定入出力S2P、50Ω源／60−j40Ω負荷、6設定、H2/H3最低30dBを維持し、RF-T006の**3.000～6.000GHz、全6設定、外部電力伝送減衰最低20dB**も要求。研究上の**最悪UL/DL IL≤1.1dB**はユーザー指定の実用目標であり、正式RF-F003の公称IL≤0.30dBや公称H2/H3≥35dBを書き換えない。

EXP-048（面積5⅓、最悪IL2.920706dB）を踏まえ、まず4L/5L/6L・固定GJM-C数増加・2個のPCB-C・2個のCvを探索。追加でQ25 LQP02HVから、正式仕様で想定される**Q33 LQW04**への交換（1個あたり面積+2）を探索した。Q33は一定Qの**仮定**であり、個別部品のQ(f)・SRF・公差を裏付けない。

## 実行済み・保存証拠

| 計算 | 代表的結果 | 出典 | 実行状態 |
|---|---|---|---|
| Q25・面積増加、35テンプレート | 面積8・4L/6GJM・IL **1.847574dB** | [selected.json](selected.json) | [Actions 39136890188](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39136890188) SUCCESS |
| Q25制約付き再最適化 | 面積9⅔・5L/7GJM・IL **1.303473dB** | [continuation.json](continuation.json) | [Actions 39137386461](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39137386461) SUCCESS |
| Q33 LQW04置換 | 面積19・5L/6GJM・IL **1.159087dB** | [highq.json](highq.json) | [Actions 39138547705](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39138547705) SUCCESS |
| Q33のコンデンサ配置局所探索 | 面積19・5L/6GJM・IL **1.158264dB** | [target_1p1.json](target_1p1.json) | [Actions 39140650005](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39140650005) SUCCESS |
| **Q33の公表0.8nH下限を導入** | **面積18・4L/9GJM・IL1.166797dB** | [physical_q33.json](physical_q33.json) | [Actions 39141049810](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39141049810) SUCCESS |

記載した候補はすべてRF-T006の必須減衰を**有限周波数格子では満たす**。各保存JSONは面積ごとの最優候補、完全L/C/k/Cvベクトル（可変C全6設定）、試行件数・数値指標・ソースSHA・制約SHAと未収束の区別を保持。個々のrunの詳細な評価条件は[manifest.json](manifest.json)と各JSONを参照。計算済みの5段階の指標評価回数の合計は**約196.5万回**（113,647＋665,384＋230,371＋328,872＋627,072）。全探索空間を網羅したという意味ではない。

### 公表部品範囲を考慮した代表例（最良1.166797dB）

- **回路：** 4LQW04（Q33モデル）＋9GJM01（Q80）＋2PCB-C（Q40）＋2IC可変C（Q35）、チップ面積単位18。Lは**8.127418、9.082463、4.174867、0.800000nH**。全4個を0.8～33nHの製品ラインアップ範囲内に制限している。元データはphysical_q33.jsonを参照。
- **IL最悪：** 1.166797417dB（指定実用目標1.1dBとの差 **+0.066797dB**）。**H2最小30.039123dB／H3最小30.040091dB／3～6GHz最小20.079968dB**（B8設定・3.000GHz）。広帯域追加阻止の余裕は0.080dBのみ。
- **有限格子検証：** 28区間×1001点（28,028評価）と3～6GHz×1MHz×6設定（18,006評価）、合計46,034点／代表候補。別式の明示的9×9枝電流MNAで**114点PASS**、最大減衰差**2.92e−13dB**、電力収支残差**1.05e−17W**。全46,034点を別式で再検証したとは言わない。
- **部品・数値リスク：** 0.8nH下限は[村田LQW04AN_00ラインアップ](https://www.murata.com/ja-jp/products/inductor/chip/overview/lineup/rf1)に基づく粗い範囲検査のみ。**厳密な実在部品の値・Sパラメータ/Q(f)/SRFは未照合**。GJMの一部は最適化下限0.005pF（5fF）に張り付いており、標準品実装可否・面積対効果は未確認。3つの磁気結合kも±0.1近傍の端点で、実装・結合極性確認なしには安定性を主張できない。
- **比較上の注記：** 面積19・IL1.158264dBの先行点はLQW04の一つが**0.4nH**で、公表シリーズ範囲下限0.8nH未満。これはRF-T006有限格子の**数学的試験適合解**としては残すが、**範囲スクリーニング済みの実装候補には含めない**。
- **未収束・未実施：** 局所SLSQP/Powellの途中best-foundを採用しており全試行の収束、大域パレート最適性、1.1dBの不可達証明はない。連続周波数極値・メーカー品番別Q(f)/SRF/寄生/基板実装面積・PCB/EM/公差/温度/歩留まり・実測は未検証。Phase 3未承認のまま継続する。

**結論：** 面積増加とQ33モデルでILは2.92→1.16dB付近まで改善したが、**1.1dBは未達**。後続Phase 2探索では、部品実在性と阻止帯域マージンを保持しつつ、固定CブリッジやPCB小容量の利用を見直す必要がある。

**永久証拠：** 元の[optimize.py](optimize.py)、[refine.py](refine.py)、[highq.py](highq.py)、[target_1p1.py](target_1p1.py)、[physical_q33.py](physical_q33.py) と対応する選抜JSON・manifest・本README。探索用の臨時GitHub Actions workflowはmainに残さない。
