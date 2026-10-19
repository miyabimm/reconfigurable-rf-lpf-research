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