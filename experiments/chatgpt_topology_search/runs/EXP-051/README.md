# EXP-051: RF-T007 one-grounded-DTC 4L redesign (Phase 2)

**Owner task 2026-10-19:** improve 4L after EXP-050 found area4⅓ 3L = worst IL0.891827dB, whereas adapted original 4L points (areas4⅔,5⅓,6) were dominated. **Main reservation:** EXP-051, request `rft007-single-shunt-fourL-phase2-20261019`, verified before running. RF-T007 trial explicitly enabled; formal RF-F003 unchanged; Phase 3 forbidden without owner approval.

## Controlled 4L topology (one grounded DTC, two non-ground DTC)

Reference source [EXP-050 area4⅓ 3L T007 best](../EXP-050/checkpoints/area4p333_rft007_best.json), area4⅓, one unavoidable shunt 0.5pF/Q40. Split original shunt Ls(1,3) into LsA(1,3) and LsB(3,4) with same series current and Q25. Keep L0(0,1), L1(1,2), Cf0 GJM Q80 (0,1), Cf1 PCB Q40 (1,2), Cp GJM Q80 (4,GND); variable Cv0(4,GND), Cv1(0,1), Cv2(1,2), each Q35/0..3pF. **Only Cv0 is grounded:** add permanent fixed 0.5pF/Q40 at (4,GND), present even with programmed Cv0=0. Non-ground DTCs Cv1/Cv2 receive no parasitic. Optional new PCB-Ctrap Q40 is across split inductor LsB(3,4) for harmonic-mode manipulation; PCB-C count remains 1 (plain) or 2 (trap), both within RF-T007 max 3. Added package is one LQP02HV (Q25/0.4..27nH), so both variants have chip area **5⅓**.

Physical single-row chip order: **L0–LsA–LsB–L1**. Adjacent mutuals are only (L0,LsA), (LsA,LsB), (LsB,L1), each |k|≤0.10, nonadjacent nominal zero. All fixed values, placements, couplings are common across six settings.

**Exact seed control:** LsA=LsB=Ls/2, k(L0,LsA)=k_old(L0,Ls)√2, k(LsA,LsB)=0, k(LsB,L1)=k_old(Ls,L1)√2. Since loss resistance is proportional to L/Q25 and both split elements carry the same series current, the four-inductor circuit has the same internal multiport nodal behavior as the baseline three-inductor circuit when no Ctrap is fitted. Program enforces max 28-band pointwise IL difference ≤1e−8dB. This is a topology baseline, not proof of 4L intrinsic superiority: same IL at greater chip cost is still dominated by the 3L baseline.

## Planned experimental matrix (strictly limited RF-T007)

| Variant | Ctrap (3,4) | PCB-C count | 4L chip area | Purpose |
|---|---|---:|---:|---|
| plain | not installed, electrically zero | 1 | 5⅓ | exact 3L→4L equivalence, then vary 4L physical neighbors and split ratios |
| trap | 0.02..0.2pF/Q40 | 2 | 5⅓ | test added trap resonance between LsA and LsB without second grounded DTC |

Fixed and variable values reoptimized together, 3 SLSQP starts/variant, coarse 7 points, fine 17 points, dense **28×1001** finite-band evaluation, target H2/H3≥30.02dB internally, hard H2/H3≥30dB. Each selected compliant variant checked by independently assembled **9×9 branch-current coupled-inductor MNA** (28×3 probes), non-negative element losses and power balance. Full fixed input/output port S2P and 50Ω source/60−j40Ω load. S2P sha, resolved constraint fingerprint and EXP id are maintained in the manifest. Ctrap in plain case is **absent**, not a physically zero-valued PCB component.

## Executed numerical results (2026-10-19)

[Actions run 39273237407](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39273237407) **SUCCESS**, including 2 split-control unit tests, two 3-start SLSQP searches and independent coupled-inductor MNA for both selected outputs. Original full raw JSON artifact `exp051-rft007-one-shunt-4l`, ID `12196760628`, raw JSON SHA256 `21e5c4533bf9f0709cbe065b7a185f23c5dfb030cf714239759a13c410e5365d`, artifact ZIP SHA256 `e31395f600334826ac9b1e1d0933bbdc184507f4c065fb5c4bdbe21caa409fbb`, source execution commit `c50cd56ca222b5b5dd25dd835beff437a8e6977d`.

**Exact model split seed:** the baseline three-inductor area4⅓ RF-T007 original worst IL0.891827010963dB reproduced by area5⅓ four-inductor plain model to a maximum pointwise difference of `6.39488462184e−14dB` across 28×1001 samples (no extra PCB trap). This does not improve chip-area Pareto because it adds a chip L. It supplies a fully feasible starting point.

| 4L candidate | Chip area | PCB-C pieces | Shunt fixed parasitics | Worst IL dB | Min H2 dB | Min H3 dB | SLSQP (3 starts) | Independent MNA |
|---|---:|---:|---:|---:|---:|---:|---|---|
| **plain (best)** | **5⅓** | 1 | 1×0.5pF/Q40 | **0.888992895** | 30.020000 | 30.020000 | 3/3 converged | 9×9, 84 samples PASS |
| trap PCB (3,4) | 5⅓ | 2 | 1×0.5pF/Q40 | 0.889175564 | 30.020000 | 30.020000 | 3/3 converged | 9×9, 84 samples PASS |

Full 29-element vectors plus all 6 programmed Cv triples:
[plain checkpoint](checkpoints/one_shunt_4l_plain_best.json) and [trap checkpoint](checkpoints/one_shunt_4l_trap_best.json). Independent explicit [plain MNA](validation/plain_independent_9x9_mna.json) and [trap MNA](validation/trap_independent_9x9_mna.json).

- Plain: max independent-vs-fast IL discrepancy `3.340e−13dB`, max power-balance residual `6.939e−18W`, actual 4×4 L matrix min eigenvalue **1.688872nH**.
- Trap: max discrepancy `1.634e−13dB`, power residual `6.072e−18W`, min eigenvalue **1.585781nH**. Optimized trap C converges to its lower bound **0.020pF**. This placement gave no IL advantage over the plain circuit in the tested local starts.
- The plain 4L at area5⅓ improved over EXP-050's best **historical two-shunt 4L at the same area** from IL1.054412 to IL0.888993, a 0.165419dB reduction. Compared with EXP-050's area4⅓ 3L (IL0.891827), the plain new 4L improves IL by **0.002834dB**, but at chip cost +1. This is a marginal nominal trade-off rather than a tolerance-robust dominance claim.
- The constrained coupling `k(LsA,LsB)=+0.10` is at the approved magnitude limit; simultaneous physical magnetic coupling realizability, SRF and Q(f) remain unverified.
- Required harmonic attenuation is achieved on a finite 28×1001 mesh, with just ~0.02dB margin. Global extrema, source S2P physical measurements, DTC fixed-C tolerance and PCB EM were not performed. Phase2 trial only; formal RF-F003 and Phase3 unchanged.

The **prior first-run artifact** (run 39272748894) reported an incorrect `L_matrix_min_eig_nH` because a 3L inherited summary function was invoked; optimization IL/H2/H3 were unaffected. After adding an explicit 4L eigensolver override and regression test, run 39273237407 fully succeeded with correct values above. Retain this diagnostic history to avoid treating the prior invalid eigenvalue as evidence.

