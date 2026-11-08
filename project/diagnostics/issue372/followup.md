# Issue #372：レビュー後の実RF診断と2-seed Pilot

[途中停止記録](README.md)は歴史として保持。PR #373レビュー（HEAD `551fea3b4e17e0cbc245cd926d23fb7e61930082`）に従い、旧診断630 samplesを再実行せず実bytes/SHA照合し、新window100側だけ実行。その後、数値・費用・保存・速度ゲートを確認して新規Pilotを実施した。Main、Extension、正式EXPは実行していない。Phase 2、RF-T008 **trial**、full_lpf。これは有限探索結果であり大域最適性・RF認定を意味しない。

## 独立診断

- 元の欠陥スクリプトを改変せず、新規 [diagnose_window.py](diagnose_window.py) を使用。legacy `io` は `not_applicable`、window100 `io` は必須・readback照合。集計スキーマのmockテスト2件PASS。旧rawの全S・requirements・Hybrid sumに対し、window100同一vectorで**完全一致**。診断Plan SHA `2b6473ae28c0e86b3a6b2c88750c2502a03854e15a4ac18ebd5b9c3d7ad5dc28`、source HEAD `f36ce077a652fccf376cdaa89cbc94eb684c297b`、source identity SHA `4fe9dfa8f70cdaf7a898b4fc5e7b4ca02214342fad069bca13dca6c4fe208ea5`。legacyと実装bytes・Python/NumPy/SciPy/thread環境は一致、HEADは異なる。
- 固定vectorのfixture callbackであり最適化ではない。window100は search 20×70=1,400、selection 84、terminal 476、anytime 0、requested=completed **1,960**、reserved/unknown 0。旧診断630は別途既実施、両方で2,590 samples。window最初の100-forward・7,000 samplesの**先行予約**をatomic書込み後の実ファイルからreadback。今回の20件で100件境界へ到達したとは主張しない（99/100/101は既存mock検査）。最終worker checkpoint 14回、確定22 forward/1,960 samples。
- callback中央値 wall `0.0220966905 s`、CPU `0.0204003135 s`（同一vector・20件、計測器込み）。Job全体wall `9.1983 s`、CPU `8.1587 s`。IOは親3、worker14、summary1の計18回、`27,493,448` bytes書込みと同数bytes即時読戻し。他の入力読込やOS I/Oは含まない。速度目安 <=2秒を満たすが、これはPilot全体の実行時間を保証しない。
- 原本 `/home/user/issue372-evidence-20261109/window-001/`、report SHA `879386c6d0ec2b5f676d1b72bd15e6cb8a6dc206ef89efc99768fe155e6da119`、worker `1ebbf9189bf148afac77e4791d14187a03e4f6a43ee703465cf2c7ffda18f7b3`、親 `36059d2769f484d6cfd0a26abf860aec56e5dc7173ca254e7ad44f2af0355772`、summary `e3fdcd337c0572a8b46e3b880c69dbe88e9c651dfd1e5cb6a1892df7f09d4002`。旧原本・コピーと#361不確定予約は変更していない。

## Pilot実行と保存

新Pilot Plan SHA `0abfb03063e41d7cc428a054663d1d0f7a1aa34801c45b7a9ac796e0055f4f2f`、入力・格子・RF/S2P詳細は[元記録](README.md)。実行source HEAD `40d30665a2295484ee539732ed7df31afc885ac1`、source identity SHA `037bfe9d15cc509ddebdc2ac9dd3671bcb91e2f480f733b7d466488bc9c028fa`。診断から実行までRF実装bytes・環境は一致、全入力と `preflight.json` を先に保存した。Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、BLAS/OMP/MKL各1 thread。監視器は1つの `scripts/run_rf_search.py develop --storage-mode window100` プロセスを起動し、seed順に逐次、通常mode（debug historyなし）。自動resume/retryなし。

| seed | worker/solver | nfev / nit | requested = completed | reserved / unknown | 17点terminal IL / H2 / H3 (dB) | strict |
|---:|---|---:|---:|---:|---|---|
| 1001 | not_converged / evaluation_budget_exhausted | 3000 / 90 | 210,896 | 0 / 0 | 8.404197094 / 22.459800499 / 18.576962710 | FAIL |
| 1002 | not_converged / evaluation_budget_exhausted | 3000 / 80 | 210,896 | 0 / 0 | 7.649545629 / 21.873508788 / 19.555109576 | FAIL |

両方ともlocal runは1回で評価枠が尽きた（設定上のmax_restarts=1を実行したとは限らない）。それぞれ search `3,000×70=210,000`、anytime `3×84=252`、selection `2×84=168`、terminal `476`。各cap 250,000、各released 39,104。合計 requested=completed `421,792`、reserved/unknown 0、released 78,208、exit code **4**。これは探索開始・予算完走の事実でありsolver収束ではない。#361の旧unknown cap 250,000はこれと別に保留。

科学順位bestはsolver採用解と異なる。1001のsearch70 best SHA `849968346ca53109d8e0dc2aca93bf207db3cbc1ecedd07a99356fd65b49b1fc`、solver/terminal SHA `03a2ad33b118dc31d301f5eea349f803cd541070a6dfc8b67016ba276fc97214`。1002のbest SHA `a0b9442340e4e6712d9e387510536bf2ec5faa5ed1e6407b9330086dbd845b33`、solver/terminal SHA `cda21f793e87840dd938c9859170f6bb213445b49e7b8eb2aeeace1f1483a2d2`。bestはsolver確定解ではない。両者ともcomponent/6設定検査と全L行列SPD PASS、物理実装性の証明ではない。完全vector、solver値、progressとSHAは派生 [pilot-summary.json](pilot-summary.json) およびGit外rawに保存。

両worker checkpoint各70回、worker I/O各 `125,743,088` / `125,680,126` bytes（即時readbackも同byte数）。親・worker・summary合計atomic 146回、`259,475,196` bytes書込み・即時読戻し。範囲外の入力読込、metadata、OS syscallは含まない。監視器で測ったプロセスwall `243.710 s`、最終sample CPU `221.41 s`（下限）。1秒周期の親ledger観測に基づく概算は1001 wall/CPU `118.88/108.44 s`、1002 `121.78/111.15 s`。前後境界と最終終了処理を含まない概算であり正確なseed別CPU計測ではない。

Git外永続raw `/home/user/issue372-evidence-20261109/pilot-001/`：親 `run.json` SHA `e1980ab1de500efbb3b75a4de7f24b8272e56add6a1994fae2b6246af5b1a689`、1001 worker `08d8eb09c6f0eb945ae8aff5a36b049fd4476fc8834e788fcf1d171f4ea42f4c`、1002 worker `ee8fcfc6177172c8d35c90bc6b558565b49796eabba19463656ec2da193b1782`、summary `ff88dc1337b7e67fa1e08c52cfa4c4888002fccfec08e2077466750a2cbc204d`。最終親と両workerを厳格readback再実行・実byte SHAを照合。凍結入力とログは `/home/user/issue372-evidence-20261109/pilot-inputs-001/`、preflight SHA `063f415c3bb64c0cb248c945b4b7670b33192d7429d0a7c14a3d7118398a6f71`、monitor SHA `434df105e515ca3f96a6d683bf630c2e1f13dd140855a0dc9107ad65c19ffe5d`。GitHubは全rawを保持しておらず、このローカル領域の継続可用性・バックアップは別途管理が必要。

## 別枠read-only検証

[検証コード](validate_pilot.py) は原本を書換えず、開始前に4 forward / **1,498 samples**を別Planに凍結し、実requested=completed 1,498。EXP-062 checkpoint SHA `4fbd86e8b46ad7bcb550ba327672b0983e8b58e9ce4b2a9364f8c6557a812b4b` の完全vector、接続・型・coupling・位置を現行definition/manifestと照合し、同RF-T008、同外部参照面で再評価。旧参考値の流用ではない。

| 候補と格子 | 最悪IL dB | 最小H2 dB | 最小H3 dB | strict |
|---|---:|---:|---:|---|
| EXP-062 benchmark 70点 | 0.827841148 | 30.005000000 | 30.005000000 | PASS |
| EXP-062 benchmark 17点/区間 | 0.827841148 | 30.005000000 | 30.005000000 | PASS |
| 1001 science best 17点/区間 | 8.398599249 | 20.612898680 | 18.641216235 | FAIL |
| 1002 science best 17点/区間 | 7.649545510 | 21.873508479 | 19.555109657 | FAIL |

上記表のscience bestと、前表のsolver terminalは別vector。いずれのPilot候補もstrict不適合かつ未収束のため、benchmarkとのIL近似・同等以上を主張しない。benchmarkとbestの各全L SPD/値・接続検査はPASS。保存先 `/home/user/issue372-evidence-20261109/validation-001/`、plan byte SHA `69ffdbbc994ee4a7d491521d081e7c7aaf1aa879e5cf41e18090e87dd242b940`、summary SHA `4f3dc73d9eb1d0a24cc79b6e84fb2758ad445159249b1463cc46e01c3fda1901`。実装source HEAD `906e81f`。各operationは評価前にunknownを保存し完了後readback。

Pilot候補が粗格子・17点とも不適合のため、dense 1001点および独立MNA/受動性/電力はこの段階では **not_run**（別枠費用0）。有限格子の評価は連続帯域保証ではない。Q(f)、SRF、EM、layout、公差、実測も未検証。通常window100は全forward履歴を保存せず、予期せぬ中断では最大1 window分の未保存証拠が失われ得る。次は本結果・保存の独立レビューであり、Main/Extension等の実行は別判断。
