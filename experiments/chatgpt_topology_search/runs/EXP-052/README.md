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


## Second topology sweep: moving physical fixed C connections (pre-run)

The first 9-topology DTC-edge sweep was executed in Actions run [39276693843](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39276693843). All nine had at least one mandatory-30dB compliant 4L point and independent MNA PASS; the best **alternative** was moving grounded Cv0 and Cpar to shunt-mid (IL0.889513621dB), while the unchanged DTC electrical graph reoptimized to IL0.888790901dB under an internal numerical 30.005dB guard (compared with EXP-051 IL0.888992895dB under 30.02dB internal guard). No novel DTC electrical-connection variant beat the unchanged graph at the *same* guard. This does not justify a general no-better-topology claim.

A second controlled set uses 4L/one-grounded-Cv0 baseline DTC wiring but **moves exactly one of the three fixed capacitor connections**, preserving two GJM01/Q80 and one PCB-pattern/Q40 and chip area5⅓. Ten graphs:

| Variant | GJM Cf0 (Q80) | PCB Cf1 (Q40) | GJM Cp (Q80) |
|---|---|---|---|
| reference | (0,1) | (1,2) | (4,GND) |
| cf0_input_output | (0,2) | (1,2) | (4,GND) |
| cf0_input_tip | (0,4) | (1,2) | (4,GND) |
| cf0_shunt_bottom | (3,4) | (1,2) | (4,GND) |
| cf0_output_tip | (2,4) | (1,2) | (4,GND) |
| cf1_input_output | (0,1) | (0,2) | (4,GND) |
| cf1_shunt_bottom | (0,1) | (3,4) | (4,GND) |
| cp_shunt_mid | (0,1) | (1,2) | (3,GND) |
| cp_junction_ground | (0,1) | (1,2) | (1,GND) |
| cp_output_ground | (0,1) | (1,2) | (2,GND) |

**Pre-run status for second set:** systematic fixed-edge optimizer has been committed but not yet executed. It uses the *same* minimum H2/H3≥30dB and 30.005dB numerical guard, two SLSQP starts per variant, 28×1001 dense checks for selected strict compliant points, and independent 84-point 9×9 MNA. No improvement of harmonic rejection margin or physical coupling studies are included.
