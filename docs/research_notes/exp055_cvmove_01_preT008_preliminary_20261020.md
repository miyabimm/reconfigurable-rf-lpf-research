# Preliminary Cv1 relocation from Node0–Node3 to Node0–Node1 (2026-10-20)

**Phase 2 only; locally executed unregistered screening; NOT an official EXP-NNN and NOT a formal RF-T008 performance result.** User asks for a "pre-T008" comparison after the prior grounded PCB-C 1pF/Q40 trial.

## Precisely evaluated network

- Original four L branches: L0(0,1), L1(1,3), L2(1,4), L3(1,2); all LQP02HV/Q25 in physical row L0–L1–L3–L2; 3 signed physically-adjacent k and all other nominal k=0.
- GJM01/Q80 fixed Cf0(0,1), Cf1(4,GND). PCB_PATTERN_C Q40 Cf2(1,2), optional Cp(0,3), added Cg(3,GND).
- IC DTC/Q35 Cv1 **moves from (0,3) to (0,1)**, Cv2 stays (1,2). Neither DTC is grounded; therefore RF-T007 special grounded-DTC 0.5pF/Q40 parasite is ABSENT.
- Cg(3,GND) alone is allowed 0.02–1.0pF/Q40 (special **pre-RF-T008** user-approved comparison); original Cf2 and optional Cp each **retain 0.02–0.2pF/Q40**. Neither Q60 nor RF-T008's general all-grounded C allowance is used. Fixed PCB-C count with Cp is 3; without Cp is 2.
- Frozen external input/output RF-F003 S2P, source 50Ω, load 60−j40Ω, all six LTE settings, 28 official UL/DL + H2/H3 intervals, minimum H2 and H3 30dB, nominal 35dB and IL0.3dB targets.

## Results: 40 local SLSQP starts

16 free-Cg starts (8 with Cp, 8 without Cp), **16/16 final SLSQP converged**, then 24 starts at eight fixed Cg values (0.02, 0.06, 0.10, 0.20, 0.35, 0.50, 0.75, 1.00pF) × 3 restarts (23/24 converged; one non-convergence retained in local raw run file, not presented as success). Coarse 7-point/240-iteration and fine 17-point/120-iteration with conditional rescue up to 500/280 only when SLSQP iteration limit is reached; dense checks at **28×1,001** and **28×7,001** points agree to printed precision. MNA 84 independent 9×9 coupled-L nodal+branch-current frequencies PASS and passive power balance PASS for both retained/deleted-Cp winners.

| Network | six-setting worst IL | min H2 | min H3 | Cg(3,GND) | Cp(0,3) |
|---|---:|---:|---:|---:|---:|
| New relocated Cv1(0,1)+Cv2(1,2), **Cp retained (best)** | **0.8473818496173434dB** | 30.004999999369875dB | 30.004999999939358dB | 0.0968102448112363pF | 0.2000000000000000pF |
| Same, Cp deleted | 0.8741688866089524dB | 30.004999999754162dB | 30.004999999986847dB | 0.24528699414522434pF | absent |
| Previous old Cv1(0,3)+Cv2(1,2), **Cg present Q40** | **0.8310463563827374dB** | ~30.005dB | ~30.005dB | 0.37701981046731264pF | 0.020pF |
| Original old Cv1(0,3)+Cv2(1,2), no Cg | 0.8497272635469568dB | ~30.005dB | ~30.005dB | absent | 0.020pF |

**Interpretation:** relocation is **0.016335493234606dB worse** than previous best (but improves 0.002345414dB over the older no-Cg baseline). Retaining Cp saves ~0.026787dB relative to deleting it. **New winning Cg=0.096810pF fits even unmodified RF-T007's 0.2pF maximum**; that is a numerical eligibility observation, not a verified official RF-T007 EXP result. Opposite-position old best Cg≈0.377pF needs the special pre-T008 ground-cap extension.

## New best fixed values, all settings identical

L0(0,1)=2.5178884913672057nH; L1(1,3)=**27.0nH**; L2(1,4)=5.580918390140731nH; L3(1,2)=7.049194423359532nH (all HV/Q25).
Cf0 GJM01/Q80(0,1)=1.6906959597872546pF; Cf1 GJM01/Q80(4,GND)=1.0438974600355875pF.
Cf2 PCB/Q40(1,2)=0.19999999999999973pF; Cp PCB/Q40(0,3)=0.2pF; **Cg PCB/Q40(3,GND)=0.0968102448112363pF**.
k(L0,L1)=+0.03476632079938425; k(L1,L3)=+0.0539916111110477; k(L3,L2)=−0.0854609407760301. Positive-definite 4×4 L matrix min eigenvalue **2.5145153805753293nH**.

| Setting | Cv1(0,1) pF | Cv2(1,2) pF | worst IL dB |
|---|---:|---:|---:|
| B71 | 2.4734304767758735 | 1.8036976446849287 | 0.7993096869286982 |
| B12 | 2.4939074115634488 | 1.5093467968492174 | 0.8194655027894382 |
| B28 | 2.9999999999999942 | 1.0942762542650721 | 0.8473818496173434 |
| B13+B14 | 0 | 1.2721875079908687 | 0.8275701822303383 |
| B26 | 1.4132891528546614 | 0.5146837754649823 | 0.844602777254259 |
| B8 | ~0 | 0.22316139580233915 | 0.8396148605643514 |

Worst IL B28 **803MHz**; min H2 B71 **1326MHz** and H3 B71 **1989MHz**. MNA 84-point worst IL difference **1.0444978215673473e-12 dB**, largest passive balance residual **1.214306433183765e-17 W**, PASS.

## Limitations and critical high-frequency implementation risk

**L1 hits 27nH upper bound** for LQP02HV; require actual part-specific SRF and loss review before considering physical design. Both fixed hot-hot PCB-Cs hit their 0.2pF max; B28 Cv1 reaches its 3pF ceiling. H2/H3 minimum only ~30.005dB, far below 35dB nominal target, insertion loss far above 0.3dB target. 1pF and Q60 assumptions are NOT needed for new winner. No continuous frequency extrema, Q(f), SRF, PCB EM, real coupling placement, manufacturing tolerance or measured S2P. Local fixed S2P waves were regenerated from RF-F003 source RLC on 1MHz grid, interpolated in complex S, checked against archived 800MHz and prior 2-DTC checkpoints; **canonical GitHub .s2p bytes/hash not independently loaded**. No global optimum claim, no official new EXP reservation.

Numerical full-precision vector of both Cp variants, six settings, and check metrics in companion `docs/research_notes/exp055_cvmove_01_preT008_checkpoint_20261020.json`. Full local scripts and 40 run vectors remain conversation artifacts; this note is curated Phase2 research preservation on draft PR #139, NOT merged into main.
