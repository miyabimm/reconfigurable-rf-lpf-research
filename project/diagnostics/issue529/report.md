# Issue #529 RF-T010 独立 Sobol 探索：40 → 8 → 1

## 結論

承認された 49 Job をすべて実施し、全 Job の親台帳・Plan・receipt・raw/checkpoint SHA・最終 vector・物理/SPD・Terminal の受動性／電力保存・指定独立 MNA を照合した。いずれも探索予算終了で **非収束**（各 Stage CLI exit 4）であり、収束やグローバル最適性を示さない。これは正式 EXP ではなく trial RF-T010 の開発 run である。

Stage 3 の 28,028 点候補は worst IL が参照より **0.0048645214141022075 dB 大きい**が、H2/H3 が共に 30 dB を僅かに下回るため、未丸め判定では **RF-T010 適合、参照同等以上、近い性能のいずれも不成立**。IL 差だけで「近い性能に成功」とは言えない。有限探索での不成功であり、不可能性を意味しない。

| 未丸め dB | 参照固定評価 | Stage 2 順位1（476点） | Stage 3 最終（28028点） |
|---|---:|---:|---:|
| seed | — | 2015 | 2015 |
| worst IL | 0.8278411484628502 | 0.8326794968436829 | 0.8327056698769524 |
| min H2 | 30.004999999866513 | 29.998567776428242 | 29.997028532925007 |
| min H3 | 30.004736913098142 | 29.981743847877702 | 29.9931040635146 |
| Terminal 最大 signed margin | — | 0.08267949684368292 | 0.08270566987695238 |
| Terminal 正違反二乗和 dB² | — | 0.18771547174253078 | 10.91226459677571 |

Terminal の二乗和は格子の点数に依存し、Stage 2 と Stage 3 は**異なる格子**なので直接改善量とみなさない。Stage 3 の Search 格子の正違反二乗和は 0.05628166283258132 dB²、1000 forward、局所 run 2 回／restart 1 回。Search と Terminal の最大 margin・目的値も異なるものである。Stage 3 最終 vector SHA `e242c79add6a4e627fef3ce29e32c1953da741dbd3bc26b2d737429a3ffb8a02`。

## 条件と実行経緯

- RF-T010 effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、base RF-T008、全6設定・28別区間、固定外部 S2P。定義 raw SHA `e8ac857c063e0b9d2eb8eaf629c2e4b700a694e9241f3bbc596d99f6374487f6`、canonical SHA `bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068`。完全 bounds／schema／band・S2P 指紋は `preflight-source.json`。
- 参照 vector は合法な box・完全回路を照合し、RF Core の 1001 点/区間、各区間先頭・中央・末尾の独立 MNA 84 点で事前評価。参照は探索開始点・選抜・bounds に使用していない。参照評価と全探索で source HEAD `58387ae6699480aeec28d2b8095c623d47ea932b`、source fingerprint `f97c8b3de5a9bc90a5db00f4ca04a82e8e89ee5313579732732c023beb1080fb` が一致。実行前 source tree clean、各種スレッド数1。
- Stage 1 の seed 2001..2040 は標準入力生成器による各1点の scrambled Sobol。再抽選・repairなし、40 vector 全件の物理・SPD を事前照合。Stage 1/2 は Search 70 点・Terminal 476 点、Stage 3 は Search 196 点・Terminal 28028 点。各 Stage は標準 `develop` CLI の plain 逐次 run、TRF・signed_margin_db/sum・ftol=1e-6・x_scale=1・restart_sigma=0.1、checkpoint 1000。既定 `lk` 指定のまま TRF の実効 cache off を raw で確認。
- 当初の checkout 内出力指定による実行前 exit 2 と **消費ゼロ**の記録は `STOP.md` に残した。その後ユーザーが再試行と `/home/user/src` の一時保存先を明示許可。参照と同じ source HEAD の worktree と、別の保存先で再試行。追加 seed・参照再評価・予算変更はない。

## 選抜と性能分布

Stage 1 完了 40 件から Terminal 最大 signed margin、正違反二乗和、seed の昇順で上位 8 seed `2008, 2009, 2031, 2015, 2025, 2038, 2001, 2037` を選抜。Stage 2 の順位は `2015, 2008, 2037, 2031, 2001, 2038, 2025, 2009`。各次段の明示 start と直前 Stage の保存済み最終 vector および SHA を照合した。全順位・各 Job の metrics・local runs・停止理由・checkpoint は `stage1-audit.json.gz`／`stage2-audit.json.gz`／`stage3-audit.json.gz`。全体分布と比較可能な対応差は `summary.json`。

476 点の Stage 1 全40件と、選抜条件付き Stage 2 全8件の RF-T010適合・参照同等以上・近い性能の到達数はいずれも 0。Stage 2 は選抜後の条件付き集団であり独立 seed 成功率ではない。

| 476点統計（最小 / Q1 / 中央 / Q3 / 最大） | Stage 1（40） | Stage 2（8） |
|---|---|---|
| worst IL dB | 1.046384 / 1.065046 / 3.053760 / 4.755498 / 5.345287 | 0.832679 / 0.840208 / 0.843843 / 0.848998 / 0.923301 |
| min H2 dB | 25.331440 / 25.337096 / 26.415604 / 29.977995 / 29.993171 | 29.996936 / 29.997841 / 29.998355 / 29.998644 / 29.999224 |
| min H3 dB | 25.010609 / 28.674225 / 28.683261 / 29.986381 / 29.993231 | 29.966838 / 29.985307 / 29.997546 / 29.998315 / 29.998879 |
| 最大 signed margin dB | 0.296384 / 0.315046 / 3.584396 / 4.663300 / 4.989391 | 0.082679 / 0.090208 / 0.093843 / 0.098998 / 0.173301 |
| Terminal 正違反二乗和 dB² | 3.437838 / 4.255064 / 483.123147 / 1016.885081 / 2764.198587 | 0.187715 / 0.208678 / 0.240540 / 0.309982 / 1.113631 |

各列の最小値は必ずしも同一候補ではない。選抜された8件を同じ 476 点上で前後比較すると、全8件で最大 signed margin が低下（差 −0.127569〜−0.222101 dB）、全8件で worst IL が低下した。H2 最小値は全8件で上昇した一方、H3 最小値は2件で低下した。各 seed の差と vector SHA は `summary.json` の `stage1_to_stage2`。早期 Stage 1 選抜により長期的に有望な seed を除外し得る。

全25座標の値・正規化 box 位置の最小／四分位／中央値／最大と境界1%以内の件数、全 L/C/k と6設定 Cv、参照と最終 vector の全差は `summary.json`。例として Stage 2 では GJM2 が下限1%以内 5/8、ICfix1 が 7/8、B8 の Cv0・Cv1 がそれぞれ 4/8・6/8。Stage 3 最終は GJM2、ICfix1、B8 Cv0/Cv1 が下限1%以内。これは実装可能性の証明ではない。

## 消費・計時・証拠

| 実消費 | Stage 1 | Stage 2 | Stage 3 | 参照別枠 | 合計 |
|---|---:|---:|---:|---:|---:|
| RF forward（Terminal含む） | 200040 | 680008 | 1001 | 1 | 881050 |
| RF samples | 14019040 | 47603808 | 224028 | 28028 | 61874904 |
| 独立 MNA samples | 80 | 16 | 84 | 84 | 264 |
| CLI wall 秒 | 530 | 1710 | 21 | 約9.56 | — |

全 Job が Search 上限まで実施。個別 local run の wall、近似 input→receipt ファイル時刻差、checkpoint 件数は `summary.json`／各 audit。後者は厳密な計時器による Job wall ではない。周期 checkpoint は瞬間観測であり真の累積 best 曲線ではない。標準 Search raw は Search 最大 signed margin および Search IL/H2/H3 を保存していないため、追加 RF 評価をせず「未記録」とする。

- raw/checkpoint 保管：ユーザー許可の `/home/user/src/issue529-persistent-raw/`。全 1089 対象ファイルの相対 path・byte 数・SHA は `summary.json` の `raw_files`。同所に各 Stage の開始・終了時刻、CLI command、console log がある。再起動で自動削除される `/tmp` は使用していないが、ストレージ障害・手動削除への保護や別機でのアクセスは保証しない。
- 永続レビュー証拠：`artifacts/` に各 Stage best の完全 result・input・receipt、実効 Plan、親台帳、参照全応答を格納。`.json.gz` は復号後の SHA が原 raw と一致することを検証済み。Stage 3 result は 28028点の全応答・signed margins と84点 MNA 証拠を含む。各圧縮物と原本の SHA・byte 数は `summary.json`。49 Job のコンパクト結果は `compact-results.json`、詳細は各 audit、入力と manifest は `stage*-inputs/`、実行ログの複製は `execution/`。
- 再試行用 worktree `/home/user/src/issue529-retry-source` は source を固定する目的で作成し、実験中維持。現況・後処理は handoff を参照。参照全応答の未追跡原本は元 checkout の `reference.json`（SHA `2d03ec10d95f39398e566d01cf9ebaa9949cf8898a98f18937f1d1bea5c52b10`）にも残す。

## 限界と検証

計算は有限格子・モデル上であり、連続周波数保証ではない。仮定した Q と固定 S2P のもとでの external-port 性能であり、SRF、Q(f)、実際の結合、EM、製造公差、実測、物理実装は未検証。Phase 3 や正式 RF 条件への昇格はない。CI PASS と独立レビュー、科学的採否は別判断。

参照・49 Job の取得済み証拠は `select.py`／`summarize.py` で RF forward を追加せず照合。原 raw 1089 ファイルのサイズ・SHA を再読込し、`compact.py` による再集計結果の一致を確認。実行前の TRF 関連 unittest（8 + 3 + 20件、重複含む）、実行後の `test_issue458_profile.py`（5件）と `test_issue527_plan_inputs.py`（4件）は PASS。`test_generate_develop_inputs.py` の名前では 0 件であり PASS として数えない。CI・PR 状態は handoff に記載する。
