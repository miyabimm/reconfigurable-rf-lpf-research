# EXP-052 — RF-T007 4L additional electrical-connection topology exploration

**Phase 2 only; explicitly reserved on GitHub main:** EXP-052, RF-T007, request `rft007-fourl-topology-edges-20261019`. Research follows owner instruction to **search more four-inductor topologies only**. Improvement of harmonic attenuation *beyond mandatory H2/H3 ≥30dB* and physical realization studies of mutual chip-inductor coupling are **outside requested scope**. No variation of approved RF-T007 limits or Phase3 transition.

## Reference and conserved hardware resources

[EXP-051 best 4L one-shunt branch](../EXP-051/checkpoints/one_shunt_4l_plain_best.json): 4×LQP02HV/Q25; chip area5⅓ (GJM01×2); one fixed PCB-pattern C Cf1=0.02..0.2pF/Q40, two GJM Cf0 and Cp/Q80; three setting-specific 0..3pF IC DTC/Q35, with exactly one Cv0 to GND having a **distinct fixed 0.5pF/Q40** Cpar. Fixed external S2P, 50Ω source, 60−j40Ω load, six setting frequencies from `data/bands.csv`.

All nine variants use same L network **L0(0,1)–L1(1,2) with shunt path LsA(1,3)–LsB(3,4)** and prescribed single-row L order L0–LsA–LsB–L1, no k outside adjacent approved bounds. All fixed capacitors unchanged in placement: Cf0(0,1) GJM, Cf1(1,2) PCB, Cp(4,GND) GJM. **Topological search dimension is the electrical connection of the DTC branches**, not a repeat of EXP-051 constant connection tuning. It includes one novel grounding relocation of Cv0 (and its parasitic) to shunt-mid node3. All Cv1/Cv2 options are always non-GND.

## Enumerated electrical topologies

| Variant | Cv0 (grounded) | Cv1 | Cv2 | New degree of freedom |
|---|---|---|---|---|
| reference | (4,GND) | (0,1) | (1,2) | EXP-051 numerical control |
| cv2_input_output | (4,GND) | (0,1) | (0,2) | full series path feedback |
| cv2_input_tip | (4,GND) | (0,1) | (0,4) | input to resonator tip |
| cv2_output_tip | (4,GND) | (0,1) | (2,4) | output to resonator tip |
| cv2_shunt_bottom | (4,GND) | (0,1) | (3,4) | split shunt-L section tuning |
| cv1_input_output | (4,GND) | (0,2) | (1,2) | Cv1 bridges whole series path |
| cv1_input_tip | (4,GND) | (0,4) | (1,2) | Cv1 provides tip feedback |
| cv0_at_shunt_mid | (3,GND) | (0,1) | (1,2) | grounded tuning and fixed Q40 parasitic both moved to node3 |
| cv0_mid_output_tip | (3,GND) | (0,1) | (2,4) | grounded tuning relocated and Cv2 taps resonator |

The nine variants keep all passive branch loss Q values independently and do not combine the Q35 programmable C with the Q40 Cpar. The two end terminals of the port S2P are frozen. The independent MNA stamps the actual Cv and its same-node Cpar at the correct terminal for each topology.

## Numerical experiment (planned prior to CI)

- Reproduce EXP-051 frozen best vector under `reference`, with full pointwise IL difference ≤1e-8dB.
- Two deterministic SLSQP starts per topology; coarse=7 and fine=17 samples per each of 28 frequency segments; remaining locally tested design candidates checked on **28×1001** samples.
- Optimize worst-case insertion loss subject to **mandatory H2/H3≥30dB**. A 30.005dB *numerical internal guard* is used solely for robust finite-precision admission; no extra harmonic attenuation optimization objective.
- For each topology with a dense strictly compliant point, independently assemble explicit **9×9 coupled-inductor branch-current MNA**, sample 84 boundary/interior points, verify IL agreement and passive power balance.
- Preserve all trial convergence status and noncompliant results separately. Snapshot only selected strict candidates with complete L/C/k vector and six DTC triples in Git. Local optimum only.

**Baseline:** EXP-051 4L area5⅓ worst IL0.888992894804dB; old EXP-050 best 3L area4⅓ worst IL0.891827010963dB. Improved 4L designs must be compared at equal RF-T007 conditions, not against historical RF-T005 results.

**Unperformed at writing:** EXP-052 optimizer CI, numerical grid check and independent MNA. Physical coupling realizability and additional H2/H3 margin improvement are intentionally not studied in this experiment. Phase 3 is not authorized.
