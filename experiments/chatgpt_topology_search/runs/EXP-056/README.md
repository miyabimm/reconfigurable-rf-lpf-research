# EXP-056 — Extend RF-T007 SLSQP iteration budget for EXP-055 4L alternatives

**Phase 2 planned (pre-run), not a new RF design specification.** EXP-056 is reserved on main by commit 362da5165aba7d6d7c64e6490fac501051cbf346 before source/numbered execution. Formal RF-F003, trial RF-T007 and Phase3 status unchanged.

EXP-055 [Actions run 39341678211](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39341678211) completed SUCCESS (not time-limited). Its two second- and third-ranked RF-T007 area5+1/3 4L candidates had coarse SLSQP **Iteration limit reached**, not GitHub Actions timeout:

- Cv1(2,4), original selected IL0.849084050dB: coarse 160 iterations, fine 48 iterations successful, but combined status nonconverged.
- Cv1(0,1), original selected IL0.857268574dB: coarse 160 iterations and fine 80 iterations both hit their limits. Another seed reached coarse 160/fine 2 and had a successful fine stage; coarse still nonconverged.

For comparison, EXP-055 winning Cv1(0,3) circuit IL0.817365590dB converged already at coarse 109 and fine 13 iterations, and is not reoptimized here.

## Method

Keep source checkpoints, 4L electrical and physical chip-row graph, RF-T007 mandatory independent 0.5pF/Q40 permanent Cpar at Cv0(3,GND), DTC bounds 0–3pF/Q35, component Q and limits, original 2×fixed S2P, 50Ω source/60−j40Ω load, 6 RF settings and 28 separate frequency intervals **identical**. Do not introduce the extra RF-T006 3–6 GHz stopband. Do not study extra H2/H3 attenuation margin or physical k implementation.

Increase SLSQP **coarse 160→500 iterations and fine 80→280 iterations**. Warm-start the former dense-grid compliant saved 29-value vectors from EXP-055; use 3 deterministic starts per variant (2 variants, **6 starts**). Dense 1001 samples per frequency region; 84 independent explicit 9×9 coupled-L MNA probes and power conservation for selected strict mandatory H2/H3≥30dB candidates. Record all optimizer messages, coarse/fine iteration counts and **fully converged** strict-compliant best separately from the minimum-IL eligible but nonconverged best.

Comparison benchmark is EXP-055 winning IL0.817365589761dB at same chip area; previous alternative IL0.849084050/0.857268574dB. Increasing maximum iterations does **not** guarantee a better circuit or actual convergence. Runtime Actions ceiling is retained at 60 minutes because prior Actions did **not** exhaust it.

**Status: pre-registered and not yet executed as of source creation.** After Actions completes, record raw result artifact digest, convergence metrics, independent MNA, representative full circuit vectors, Git-only storage and updated manifest status. Never label unexecuted code as measured or passed.

## Exclusions

Nominal fixed-Q numerical Phase 2 only, neither global optimization nor continuous frequency guarantee, no Q(f), SRF, PCB EM, part tolerance, actual k implementation, source S2P measurement or Phase 3.
## Executed results — 2026-10-20 JST (Phase 2)

[GitHub Actions run 39344219070](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39344219070) **SUCCESS**: EXP-056 main reservation, preflight, source tests, numerical optimization and independent MNA all passed. Source execution SHA ba6fc7422115f45ef6d0be39929f37c0142a4caf. Artifact ID 12231005251, ZIP SHA256 ab548ebb5a76ea680b6dbd83e4ee411ed7444f5cc4d60a088dddef68283efa38, inner original longer_slsqp.json SHA256 35a38af9b9f1a0599252c9351a69e2032ab6e37ac40dd1410d652a2242f02ac2.

**6/6 SLSQP starts fully converged** after reoptimization with EXP-055 checkpoint warm starts and coarse maxiter500/fine maxiter280. Zero nonconverged, zero failed. Both selected circuits pass mandatory finite-grid H2/H3≥30dB on 28 separate intervals ×1001 points and independent 84-probe coupled-inductor 9×9 MNA with power balance.

| Third DTC Cv1 | EXP-055 worst IL (selected SLSQP) | EXP-056 worst IL (selected SLSQP) | Selected coarse/fine iteration counts | Independent MNA |
|---|---:|---:|---:|---|
| (2,4) | 0.849084050371 dB, nonconverged | **0.849084050391 dB, converged** | 24 / 25 | PASS |
| (0,1) | 0.857268573929 dB, nonconverged | **0.857268582225 dB, converged** | 48 / 1 | PASS |

All six individual coarse/fine SLSQP iteration counts: Cv1(2,4) [24/25, 47/27, 98/26]; Cv1(0,1) [4/1, 40/1, 48/1]. Every optimizer stage terminated successfully. Best EXP-055 Cv1(0,3) worst IL **0.817365589761dB** remains UNBEATEN. No new Pareto result; nominal 35dB and IL0.3dB targets remain unmet.

**Interpretation:** Prior iteration-limit termination was within SLSQP, **not** GitHub Actions job timeout. EXP-056 changed both warm starting from previously near-optimal EXP-055 vectors and maxiter, so it does not isolate iteration limit extension alone as the cause. Historically EXP-055 statuses stay nonconverged; new EXP-056 optimized vectors are separately fully converged. This supports convergence to an almost unchanged local basin, not proof of a global minimum.

Complete full 29 parameter vectors and six DTC settings: [converged Cv1(2,4)](checkpoints/cv1_output_shunt_tip_converged_best.json), [converged Cv1(0,1)](checkpoints/cv1_input_parallel_L0_converged_best.json), [all six run records](run_summary.json). Independent MNA records: [Cv1(2,4)](validation/cv1_output_shunt_tip_independent_mna.json) max IL error1.1795e−12dB, power residual1.0408e−17W, [Cv1(0,1)](validation/cv1_input_parallel_L0_independent_mna.json) max IL error6.4659e−13dB, power residual8.6736e−18W.

No physical k realizability, extra H2/H3 margin, continuous extrema, Q(f), SRF, PCB EM, tolerance, measurement or Phase3. **RF-F003 unchanged, Phase 2 active; Phase3 still requires explicit approval.**
