# Issue #529 — Stage 1 開始前 STOP（未完了）

## 状態と原因

固定参照評価後、Stage 1 の標準 CLI を 2026-11-27 10:13:21 UTC に起動したが、exit 2。担当者が `--output` に checkout 内の `project/diagnostics/issue529/raw-stage1` を誤指定した。CLI は `STOP: Fresh temporary output outside repository required` と出力し、raw ディレクトリ作成前に停止した。`src/lpf/search/_development_runner.py:179-190` の output チェックは Plan 凍結・Runner 実行より前であり、探索 forward および MNA の消費はゼロ。Issue の exit 2 時 STOP／無断 retry 禁止に従い、修正実行していない。Stage 1 全40件、Stage 2 全8件、Stage 3 全1件は未実行であり、探索結果・順位・成功判定はない。

標準 CLI は `tempfile.gettempdir()` 配下で checkout や他の Git repository の外、かつ未存在の出力先を要求する。Issue は raw/checkpoint が再起動後も消えない保存場所を要求するため、デフォルト `/tmp` がその条件を満たすとは仮定できない。永続的な checkout 外の作業ディレクトリにはユーザーの事前承認が必要。exit 2 後の再実行を許可するか、恒久保存場所をどこにするか判断が必要。

## 参照評価（探索ではない）

- 評価時 source HEAD `58387ae6699480aeec28d2b8095c623d47ea932b`、source SHA `f97c8b3de5a9bc90a5db00f4ca04a82e8e89ee5313579732732c023beb1080fb`、実行前の tracked/untracked 状態は clean。正確な source・環境等は `preflight-source.json` と `reference_started.json`。
- 試験 RF-T010 effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`。28区間×1001点の格子 SHA `7d077ee49a1664e5df701cf3fe4766454fac1d8d6bc0bfc5c5ae6d13eba92e3e`。参照 vector SHA `4131fa4e677afd364c8e448325d2971f05214284047c349bf2f794585668313c`。
- 物理・box・6設定・SPD、端子応答の受動性・電力保存、84点独立 MNA と RF Core の照合を PASS。未丸め worst IL 0.8278411484628502 dB、min H2 30.004999999866513 dB、min H3 30.004736913098142 dB。正式適合ではない。SRF・Q(f)・EM・公差・実測・連続周波数保証は未検証。
- 参照実消費 1 RF forward／28,028 RF samples／84 MNA samples（約9.56秒）。`reference-compact.json` に84点の証拠、全指標とフル証拠の SHA を保存。全応答を含む `reference.json` はこの checkout 内に保持する未追跡ファイルで、18,495,105 bytes、SHA-256 `2d03ec10d95f39398e566d01cf9ebaa9949cf8898a98f18937f1d1bea5c52b10`。Git に含まないため、この checkout 以外での取得・永続性は未保証。削除しないこと。
- Stage 1 の40開始 vector は標準生成器で seed 2001..2040 を使い再抽選・修復なしで生成、物理と SPD を preflight で検査済み。初期値は `stage1-inputs/starts.json`、全25座標の bounds は `stage1-inputs/bounds.json`。全 Stage の事前予約と grid は `preflight-grid-budget.json`。Stage 2/3 の Plan は未生成。

## 証拠・検査

起動コマンド・開始時刻・終了状態・エラーは `stage1-started.txt`、`stage1-finished.txt`、`stage1-console.log` に保存。計画総上限（参照込み）は881,050 forwards／61,874,904 samples／264 MNA、実験消費は上記参照分のみ。Stage 1 の `plan.json`／親台帳／receipt／checkpoint は作られていない。

`test_issue503_trf_runner.py` 8件、`test_issue507_trf_options.py` 3件、`test_issue509_trf_restart.py` 20件 PASS（後者は import による再実行を含む）。`git diff --check` 実施。CI・独立レビュー・科学的成功判定は未実施。中間停止であり Issue の DoD を満たしていない。
