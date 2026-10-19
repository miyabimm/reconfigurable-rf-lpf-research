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

**Pre-run status:** source and audit metadata prepared; no EXP-051 RF numerical result yet. Old EXP-050 results are reference only, not EXP-051 outputs. Model remains constant-Q; component-specific Q(f), SRF, EM, DTC parasitic variation, multi-inductor realizability and continuous-frequency extrema are all unverified. Avoid global-optimum/Phase3 claims.
