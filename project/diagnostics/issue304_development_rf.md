# Issue #304 — 限定開発RF smoke（非EXP）

`development_rf`は明示opt-inの開発専用経路。`production`は引き続き無条件
`not_ready`、G0/G1/G2–G5未接続、候補昇格blocked。固定T008 rev3/full_lpf、既存
`tests/test_phase2_problem_seed.py:make(RF-T008,4)`の4L definition/vector、seed
ラベル23のみ。Sobol生成・再抽選・修復をしない。Planは1 arm/1 step、最大1600
requested samples、solver最大12 callbacks/2 iterations、restartなし、anytimeなしに
制限する。終端476は予約し、solver/選別の各full batchと終端は既存meterへ課金する。
ソルバーのcallback予算終了もsample予算終了と区別して`budget_exhausted`とし、
最後の合法観測とsolver結果を保持する。異常/中断/保存失敗では後続forwardを行わない。
fixture経路の4方式は人工ILのままであり、実RF結果と混同しない。

## 実施した1回の開発smoke

2026年の実験結果や正式EXPではなく、ローカル開発用一時raw。開始前に条件を固定。

- source `a07c2a6e3ac01e202eecc7ec5b0e92a460d015f8`（clean）、source provenance SHA `20c1bbb7a349c169444297036073ca4fa2523c1843fda44c07c24a15c8b278ef`
- RF-T008 effective SHA `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`、formal activeはRF-F003であり代用しない。
- definition canonical SHA `bef3173906b3674bbe116083782dede8ccdffb56e8fc906c613e2bde451cff2d`、vector SHA `368c7570084d2d849b7ff84bd4be6861e0687438ddc3957db9fd70b830316d82`、Plan SHA `30b7e9799da0b63f91fd3977f0086ce802de86e9bf048b37e85877f33b98a9f3`。
- SLSQP squared sum、1 iteration、最大4 callbacks、探索28区間×2点、選別×3点、終端×17点、step 560、job/trial 1036 samples上限（476予約）。
- 実行コマンド：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --frozen python scripts/run_rf_search.py run --mode development_rf --config project/experiments/rf_search_development_smoke.yaml --output results/issue304-development-rf-smoke
```

実施結果はrequested/completed **784/784**（coarse 4×56、選別84、終端476）、
failed forward 0、SciPy callback上限`evaluation_budget_exhausted`、未収束。
SciPyから成功・最終解は返っていない（`solver_success=null`）。汎用solverは上限時に
初期点を返し、当時のworkerはそれを選別した。実RF terminal17が完了したことは
本番17点認定を意味しない。rawの`job.status=not_converged`は実行当時の記録であり、
後続修正により現コードではこの終了を`budget_exhausted`と記録して選別せず終端へ進む。
この後続修正はmock回帰で検証し、実RF再実行はしていない。rawは改変しない。

ローカルraw（Git管理外、削除しない。別環境に自動保存される保証はない）：

- `results/issue304-development-rf-smoke/run.json` SHA256 `2fd43f545e601f07793de3aaf149c07220e34d20cd89a0f3febe3ca85681881f`
- `results/issue304-development-rf-smoke/seed23_slsqp/job.json` SHA256 `d337e000997811ee9a0c2fcecdb78f25559b853a556d6e227b43598dfc8cdb89`
- `results/issue304-development-rf-smoke/seed23_slsqp/step-0.json` SHA256 `14f6eb97a0f5b028b1c55468877eb3257805eb46ae2a794c5085c9e24f609424`

rawに完全JobSpec、設定、source/lock/env/bands/S2P fingerprint、全x、停止・費用を保存。
独立MNA・受動性/電力・独立SPD・dense1001は`not_run`。有限格子、SRF、Q(f)、
EM、公差、測定、実装可能性、大域最適性の保証はない。本番承認やG0/G1 PASSではない。
