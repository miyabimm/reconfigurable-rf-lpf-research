# EXP-062 — RF-T008 v3 Phase 2 高コスト4Lでの対GND PCB-C水平展開

- 状態：数値探索準備済み。**完了結果がない状態でパレートを更新しない**。
- EXP ID：main中央台帳予約済み `EXP-062`。2026-10-20T15:15:45Z（timestamp精度修正はmainコミット `bc1c10ad841bd9d7cb2e047a5393f8655a432007`）。
- 固定RF条件：RF-T008 revision 3、正式RF-F003の外部固定S2P、6設定、28×1001帯域、H2/H3≥30dB。
- トポロジー：4×LQP02HV Q25、IC固定Q60+可変Q35複合枝2個（各0..3pF可変）、隣接符号つき |k|≤0.1。
- 初回：2GJM/3GJM/4GJM＝面積5⅓/6/6⅔、各4種類の固定GJMとPCB-C配置、2初期値、計24初回試行。
- 技術仮説：EXP-059の面積4⅔でのPCB-CのN3–GND/N4–GND接地化（IL0.854367→0.837134dB）が高コスト群にも通用するかを、同面積の元EXP-058制御配置と比較する。
- 独立検証：候補を28×1001密格子で評価後、明示9×9 MNAの84点/候補と受動電力収支、L行列SPD、収束フラグを検査。
- SLSQP：`slsqp-staged-v2`、粗240/精密120、真のiteration-limitのみ条件付き増額、その他は規定のウォーム再始動。
- 保管：本runと収束・未収束・停止理由を別記録。最良ベクトルとMNAをGitへ別途選別保持し、元のEXP-058/059数値は改変しない。
- Actions：<https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/workflows/exp062_rft008_4l_high_cost_pcb.yml>
- 留保：局所探索、有限格子、公称Q一定。35dB目標、IL≤0.30dB、連続極値、Q(f)、SRF、EM、実際の結合・公差・Phase3は未検証。
