# Issue #375 — Hybrid 6,500評価 Pilot 結果

## 結論

Phase 2／**非EXP・開発専用**として、RF-T008 trial rev3・full_lpf・既存の固定4L/2複合Cv回路に対し、seed **1002 → 1001**の順で各1つの新規Jobを実行した。Seed 1002のraw・費用・終了状態・実行時間を照合してからseed 1001へ進んだ。両Jobのraw readbackとrequested/completed費用は一致し、unknown/reservedは0。追加の最適化・追加探索は行っていない。

- Seed 1002: 6,500 nfevまで到達、**solver未収束**（evaluation budget exhausted、exit 4）。84点格子の最終時点で違反量は大幅に減ったが、ILは増加し、17点terminalはstrict FAIL。
- Seed 1001: solverは2 local run後に収束して終了（6,006 nfev、exit 0）。6500点目のanytime閾値には達していないため、6500の値は**未実施**。最後の6000点anytimeと17点terminalはいずれもstrict FAIL。
- 3000 forwardまでの共通閾値（1000/2000/3000）は、両seedとも前回#372 rawと同一84点格子で**三指標すべて完全一致**。今回もresumeではなく同じ初期vectorからの新規再計算である。
- 最大/合計違反の低下はRF strict適合を意味しない。ILとのトレードオフも観測され、両seedとも最終候補は30dB必須制約を満たさない。大域最適性・正式RF認定は主張しない。

## 固定条件・再現入力

- 実行元: 最新 `main` `b4fe6d64c7a68f8a3817e48fd2d7e22c12b43349`。source identity SHA `7eb87b29995db44d36948bd051ad8572fc88d293868582a73f7ae2f6f4555fa0`。実行時の追跡対象source差分なし。
- 現行active formalはRF-F003。今回のみRF-T008 rev3を明示opt-in（effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`）。正式RF条件は変更していない。
- `full_lpf`、6設定・28個別のUL/DL/H2/H3区間、固定S2P、固定4L/2複合Cv定義（definition bytes SHA `e8ac857c063e0b9d2eb8eaf629c2e4b700a694e9241f3bbc596d99f6374487f6`、canonical SHA `bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068`）。bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、input S2P SHA `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、output S2P SHA `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。
- Search: 70 RF samples/forward。Anytime/selection: 84 samples/forward、同一grid SHA `29e918981abda38c4becb14b1874bd7af5380b4ccaebecb5faafab6f9a51bfdb`。Terminal: 476 samples、grid SHA `28ee5b630e4842b183a7c36fd610cc32e2509c0044c6a5848ce2fbd147a22e29`。Search grid SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`。
- Hybrid(sum)、`maxiter=300/local run`、`max_restarts=1`、`restart_sigma=0.1`、`max_evaluations=6500`。各seedごとにstep予約455,000 / Job・Trial cap 460,000 samples。事前preflight静的上限は456,400/seed、2 Job cap合計920,000。別枠read-only上限1,120（84×2初期vector + 476×2科学順位best）を事前凍結し、実費用1,120。
- Seed 1002 start SHA `6203467121a4e37baaa51c471aaecb3174f3374f9ab955d6fbf101f7b5ce935f`。Plan SHA `317a282836fd5a566837546b63ff1c47282e81f672f94c66f9a7542427ffcd98`。
- Seed 1001 start SHA `49f9f53b0220f4e81332fbe94cebe2482e436b1a313aaabbae696a6b015761e5`。Plan SHA `349cedd21903578db24e2f7fe43b1a174a09b05d32650c9d53418ff2f601bf44`。
- 凍結したYAML・startsは本ディレクトリの `pilot-seed1002.yaml`, `starts-1002.json`, `pilot-seed1001.yaml`, `starts-1001.json`。ファイルSHAは `pilot-summary.json` に保存。変更点はIssue #375指定のseed分割・solver/評価上限・anytime・費用capのみ。
- 環境: Python 3.12.15 / NumPy 2.5.4 / SciPy 1.18.1、`uv sync --frozen`、`OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=1`。uv.lock SHA `52144cfd0dfc7249e78c24942bac69fddc8dc3ae088799d9cf31d0d90e824e0b`。static preflight SHA `a0432b48272571a8fd7e35171a2be0b748ec447d827137ccc3b9ca90ecad9f18`、read-only ledger SHA `96f740bffd58f12bb32ff0925814da9b366002928f033187bcfaa8a7a46457fb`。

## 84点格子の違反量・IL推移

各milestoneの値は、その時点で測った**現在点**であり、履歴bestではない。`max_violation_db`は14個のmandatory H2/H3区間違反の最大、`sum_violation_db`はその合計、`worst_il_db`は14個のUL/DL区間における最大IL。初期vectorも同じ84点gridで別枠read-only評価した。strictはmandatory 30dBの有限grid判定。

| Seed | search forward（milestone） | max violation (dB) | sum violation (dB) | worst IL (dB) | strict |
|---:|---:|---:|---:|---:|:---:|
| 1002 | 初期値 (0) | 28.515552372 | 388.448629893 | 6.288802429 | FAIL |
| 1002 | 1,000 | 21.922004086 | 256.010714819 | 0.987666304 | FAIL |
| 1002 | 2,000 | 10.921163950 | 93.520769810 | 7.427859136 | FAIL |
| 1002 | 3,000 | 10.444890439 | 92.632116117 | 7.649545633 | FAIL |
| 1002 | 4,000 | 12.237342170 | 79.679175430 | 8.039472390 | FAIL |
| 1002 | 5,000 | 9.416721650 | 38.464254245 | 9.165009387 | FAIL |
| 1002 | 6,000 | 0.934038003 | 2.850873409 | 9.258707657 | FAIL |
| 1002 | 6,500 | 0.710062672 | 0.957136164 | 9.279059497 | FAIL |
| 1001 | 初期値 (0) | 25.224754408 | 323.427211335 | 24.999944739 | FAIL |
| 1001 | 1,000 | 18.787686010 | 156.741688136 | 2.838496920 | FAIL |
| 1001 | 2,000 | 15.325718331 | 116.030297045 | 6.426806374 | FAIL |
| 1001 | 3,000 | 11.423037290 | 96.248537812 | 8.404197091 | FAIL |
| 1001 | 4,000 | 11.383523743 | 94.745397220 | 8.591734103 | FAIL |
| 1001 | 5,000 | 11.356991629 | 94.538356291 | 8.594095820 | FAIL |
| 1001 | 6,000 | 11.353896198 | 94.565353624 | 8.587452821 | FAIL |
| 1001 | 6,500 | **未実施**（solver収束後、455,000-sample閾値未到達） | — | — | — |

1002は違反量のsumを連続して減らし、6,000–6,500で最大違反も約0.71dBまで低下した一方、worst ILは0.988dB（1,000点）を底に9.279dBまで増えた。1001は初期値から6000までILが24.9999→8.5875dBへ下がったが、最大違反は約11.354dB付近で頭打ちになった。どちらもstrict FAIL。

### 前回#372 Pilotとの比較

#372で保存された同じstart・同じ84点gridの1000/2000/3000値と完全一致（数値差0、strictもすべてFAIL）。この完全一致は早期区間の再現確認であり、今回を厳密resumeとみなす根拠ではない。3000より先は#372に対応値がない。

| Seed | #372 → #375 `best_fun` | #372 → #375 nfev | #372 → #375 nit | 終了状態 |
|---:|---:|---:|---:|---|
| 1002 | 1874.259233318 → 9.847856315 | 3000 → 6500 | 80 → 97+87 (2 runs, 1 restart) | #372/1回目は予算切れ、今回2回目runが予算切れ。overall `not_converged`, exit 4 |
| 1001 | 2437.195385408 → 2400.022097767 | 3000 → 6006 | 90 → 165+22 (2 runs, 1 restart) | 今回2 runsともsolver収束、`restarts_exhausted`, exit 0 |

`best_fun`は同じHybrid(sum) optimizer目的値で、dB値ではない。前回は両seedとも3000 nfevで未収束。今回1001のnfev=6006は最大上限6500未満だが正常なsolver終了であり、追加forwardを無理に実行していない。

## 終了・費用・terminalと科学順位best

| Seed | solver / exit | nfev / nit (local runs) | requested=completed / cap | released / unknown | wall / CPU (user+system) | max RSS |
|---:|---|---:|---:|---:|---:|---:|
| 1002 | `not_converged`, exit 4; eval budget exhausted | 6500 / 97+87 (2; 1 restart) | 456,316 / 460,000 | 3,684 / 0 | 236.71s / 234.63s | 177,996 KiB |
| 1001 | `converged`, exit 0; restarts exhausted | 6,006 / 165+22 (2; 1 restart) | 421,652 / 460,000 | 38,348 / 0 | 220.34s / 218.39s | 172,368 KiB |

1002は3,000時点のpilot結果/時間/費用/byte readback確認後、wall 3:56.71（6分未満）かつunknown/reserved=0を確認してから1001を開始した。1001も3:40.34。2つのJob wall合計457.05s（7:37.05）で、Issue記載の線形見積約528sを下回った。実費用はPilot 877,968 + read-only 1,120 = 879,088 samples（上限921,120以内）。1002のexit 4は照合済み予算完走後のsolver未収束を表し、保存障害/unknownではない。

window100 atomic checkpoint数はseed1002=138、seed1001=126。親/worker/summaryのJSON payload書込み・即時読戻しはそれぞれ総計142回/270,908,937 bytes、130回/244,204,044 bytesで一致。これはatomic payload I/Oの計測であり、他のmetadata/OS I/Oを含まない。親・worker・summaryの実bytes SHAとfinal readbackは全件一致。

選抜後のterminalは17点/区間（476 samples）。科学順位bestは粗70点上で記録されるbest-observed vectorで、solver採用terminalとは別。各科学順位bestを別枠read-onlyで476 samples評価した。

| Seed / ベクトル | grid | max / sum violation (dB) | worst IL (dB) | min H2 / H3 (dB) | strict |
|---|---:|---:|---:|---:|:---:|
| 1002 solver terminal | 17点 | 0.710062672 / 0.957136164 | 9.279059497 | 29.983914526 / 29.289937328 | FAIL |
| 1002 science best | 70点 best → 17点read-only | 0.710062139 / 0.957135596 | 9.279059482 | 29.983914479 / 29.289937861 | FAIL |
| 1001 solver terminal | 17点 | 11.353896198 / 94.565354602 | 8.587452821 | 22.494641401 / 18.646103802 | FAIL |
| 1001 science best | 70点 best → 17点read-only | 11.353576221 / 97.102973936 | 8.586290340 | 18.882071935 / 18.646423779 | FAIL |

初期vector 2本の84点read-only 168 samplesと、科学順位best 2本の17点/区間read-only 952 samplesはPilot optimizer費用とは別枠。read-only合計は事前凍結上限1,120と一致。SPDとcomponent policyは確認済み（全start/候補でmin eigenvalue >0）が、物理的実装性を証明しない。今回best/terminalのいずれもH2/H3必須制約FAILである。

## 保存・検証限界

- 全raw（親run/worker/summary、実行時間・monitor、read-only応答と保存script、入力、監査結果）はGit外 `/home/user/issue375-hybrid-6500-20261109/` に保全。二次コピー `/home/user/issue375-hybrid-6500-backup-20261109/` の全ファイルをSHA照合する。最終manifest `backup-verified-final.json` SHA `e734516f25398a9e7d02afea38ff30995b17860f3bbe82d237ff4a27380cfac3` は43ファイル／8,561,183 bytesを記録。両方とも同一 `/dev/sdd` 上のローカルコピーであり、**offsite backupではない**。後続の独立保管は別途必要。Gitにはfull raw responseを含めず、compact summaryと入力だけを記録する。
- 主要worker SHA: seed1002 `bfeb14820c7715d0ad69a529002c24555f41f622804e66b251cd6be3f92643bd`、seed1001 `988f73f5b88e0b4edb04e6545c2ed2bf6c88085e1683099eb5cfbb9fbc7472e2`。親/summary/monitor/time/read-onlyの全SHA・byte sizeは `pilot-summary.json` と外部raw manifestに記録。
- window100の通常mode（`--debug-forward-history`なし）は全forward毎の履歴を保存せず、各100-forward窓のcheckpoint・best-observed・指定されたanytime/selection/terminal等だけを保持する。したがってこの表は固定閾値の現在点であり、全iteration時系列や途中のHybrid objective履歴ではない。
- worker/parent/summary rawの実byte readback、Plan/JobSpec/source/grid/vector identity、forward/requested/completed/capが整合。両seedでunknown/reserved=0。開発用でG0/G1、正式EXP保存監査は非該当・未実施（summaryのG0/G1・G2/G5は `not_ready`）。
- 84点/17点有限gridの結果であり、1001点dense・全帯域独立MNA・独立passivity/power balanceはnot_run。連続帯域、Q(f)、SRF、EM、layout、公差、実測も未検証。有限grid strict FAILを連続周波数域の不可能性に読み替えない。
- Main/Extension、正式EXP、追加探索は未実行。Phase 2のまま。前回#361のunknown 250,000-sample予約は本Issueの新Job予算と別に保持し、#372既実行分とも相殺していない。PRは結果報告と再現入力だけで、solver/RF/API変更なし。

## Raw locations / identifiers

- Primary raw: `/home/user/issue375-hybrid-6500-20261109/` (persistent, Git外, checkout外, `/tmp`外)
- Local backup: `/home/user/issue375-hybrid-6500-backup-20261109/` (同一filesystem、SHA一致確認)
- New seed Plan SHA: 1002 `317a282836fd5a566837546b63ff1c47282e81f672f94c66f9a7542427ffcd98`; 1001 `349cedd21903578db24e2f7fe43b1a174a09b05d32650c9d53418ff2f601bf44`
- Compact summary: `project/diagnostics/issue375/pilot-summary.json` (SHA `974c229e85d5ef0cbcd0808c1ca157ca314e8032eade9348af5dd2f177eb246f`)
