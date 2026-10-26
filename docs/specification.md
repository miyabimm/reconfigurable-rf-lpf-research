# 設計仕様 / Specification — RF-F003（2026-10-16正式承認）

現行正式正本は [RF-F003](../data/constraints/formal/RF-F003.json)、[台帳](../data/constraints/registry.json) の active_formal_id が指すものとする。`data/design_constraints.json`は現行正式版の完全一致コピー。旧 [RF-F001](../data/constraints/formal/RF-F001.json)・[RF-F002](../data/constraints/formal/RF-F002.json) は変更不可の履歴として保持。

## RF評価・性能目標

6設定：B71 / B12 / B28 / B13+B14共通 / B26 / B8。周波数は[data/bands.csv](../data/bands.csv)を正本とし、各設定のUL/DL全域で最大IL、UL-H2/H3全域で最小減衰を評価。不連続帯域を連結しない。源50Ω、負荷60−j40Ω（周波数一定）。IL=−10log10(Pload/Pavs)、最終公称目標IL≤0.30dB、H2/H3≥35dB（最低必須30dB）。面積コストはハード上限なし、ILとのパレート軸。

## インダクタ

| 部品 | Q（Phase 2仮定） | L範囲・上限 | チップ面積 |
|---|---:|---|---:|
| LQP02HV | 25 | 0.4–27nH、優先 | 1 |
| LQP02HQ | 20 | 0.2–56nH、必要時のみ | 1 |
| LQP01 | 15 | 未確定 | 2/3 |
| LQW04 | **33** | 未確定 | 3 |
| PCB-L | 12 | **各2nH以下（上限）、原則3本以内** | 0 |

チップLは一列配置、強結合は物理的に隣接するチップL同士のみ**|k|≤0.10**。非強結合ペアは公称k=0、感度解析時のみ**|k|≤0.03**。PCB-L同士**|k|≤0.10**、chip-LとPCB-Lは**k=0**。符号は物理配置・電流基準と整合し、全L行列正定値を必須とする。

## コンデンサ

GJM01固定C：Q80、各100pF以下、面積2/3。PCBパターン固定C：Q40、各0.02–0.2pF、最大3、チップ面積0。IC可変C：**正式最大2独立枝、各0–3pF、Q35、配置自由（対GND・非GNDブリッジ・主信号経路直列を含む）**。固定L/C・結合・トポロジーは全6設定で共通、設定別に可変C値だけを変更する。0pFの直列枝は開放として取り扱い、連結性を確認する。

## 外部ポートの固定寄生モデル（RF-F003）

[入力側S2P](../data/parasitics/circuit1_ant_coupler_0_6ghz.s2p) Port1→Port2 → LPF → [出力側S2P](../data/parasitics/circuit2_poc_through_0_6ghz.s2p) Port1→Port2 の順で直列接続。外部端子間の総合指標にIL≤0.30dB、UL H2/H3≥30dB必須・35dB公称を適用。入力源50Ω、外部負荷60−j40Ωは変更しない。S2Pの正規化50Ωは内部50Ω終端の意味ではない。

各固定S2PはDC～6GHz、1MHz刻み、RI形式、6001点。SHA256はRF-F003の外部寄生メタデータに固定する。解析ワーカー起動時の1回読み込み・キャッシュ、格子間で複素Sの実部虚部線形補間のみ許可し、毎回RLC回路を再計算しない。LPF本体の面積評価に寄生回路を加算しない（寄生の実装領域は別管理）。本S2Pは手書き図から解釈した理想RLC計算値であり実測ではない。基準面と容量値を物理的に検証する。

## 別登録の試験条件と研究ゲート

[RF-T005](../data/constraints/trial/RF-T005.json) はRF-F003基準のPhase 2明示opt-in条件で最大3独立可変C、各0–3pF・Q35・接続自由。RF-F003との差分は枝数上限のみ。旧[RF-T004](../data/constraints/trial/RF-T004.json) はRF-F002基準のPhase 2比較条件で、可変Cのみ**最大3独立枝**へ緩和する旧版。試験版利用には明示opt-in、実効条件ハッシュの保存を要する。RF-T001/T002/T003は旧RF-F001ベースのまま変更しない。従来のLPF-007/008等はRF-F002に適合した成果とは扱わない。

Q値は一定Q仮定であり、実SRF・Q(f)・寄生・同時結合・量産性は未検証。Phase 2を継続しPhase 3は明示承認まで停止。
