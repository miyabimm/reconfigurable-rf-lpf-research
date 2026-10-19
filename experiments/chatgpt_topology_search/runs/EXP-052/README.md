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

**Original pre-run note (superseded by completed runs below):** EXP-052 optimizer CI, numerical grid check and independent MNA. Physical coupling realizability and additional H2/H3 margin improvement are intentionally not studied in this experiment. Phase 3 is not authorized.


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

**Original preregistered second-study plan (executed below):** systematic fixed-edge optimizer has been committed but not yet executed. It uses the *same* minimum H2/H3≥30dB and 30.005dB numerical guard, two SLSQP starts per variant, 28×1001 dense checks for selected strict compliant points, and independent 84-point 9×9 MNA. No improvement of harmonic rejection margin or physical coupling studies are included.


## Executed Phase 2 results — 19 variant evaluations (2026-10-19)

Two independent GitHub Actions numerical sweeps both completed successfully under the fixed RF-T007 model:

- **DTC graph positions:** [run 39276693843](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39276693843), 9 graph variants, 18 SLSQP starts, **18 converged**. Raw JSON SHA256 `8edf68e4d11152e89f699dc0f7d1c76b0742a780ebf5ad9a3da7f3fdf756b237`; ZIP SHA256 `5499283af9ee5ce1a8fc906bef3d2a4607fb7e3aedb205b686744d890bfd4558`.
- **Fixed C graph positions:** [run 39277687593](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39277687593), 10 variants, 20 SLSQP starts, **19 converged, one nonconverged** (`cf0_output_tip` start1). Raw JSON SHA256 `15ff02edb5fe7d6edff1b23da82b207050d01182b53b20ffb9677928ea954542`; ZIP SHA256 `7ff748e8c86fb5fd41cfb6ff0aa50f4802291fd948ec88cb1151be9f7cccd4ec`.

The reference graph was included in both, so **19 variant evaluations represent 18 distinct four-L graph topologies** (17 novel ones plus reference). A strictly compliant local candidate was found for every variant and independently 9×9 MNA-verified at 84 points. Complete 29-element L/C/k + six setting-specific DTC vectors were retained for the best observed design, retuned reference, and novel grounded-Cv0-mid design; all 19 scored results and convergence counts are in [run_summary.json](run_summary.json).

| RF-T007 4L connection | Chip area | worst UL/DL IL | H2 min / H3 min | Relative to same-guard reference |
|---|---:|---:|---|---|
| **Cf1 PCB bridges input↔output (0,2)** | **5⅓** | **0.885189326 dB** | 30.005/30.005 dB | **−0.003601575 dB** |
| Original Cf1 PCB parallel output L1(1,2) | 5⅓ | 0.888790901 dB | 30.005/30.005 dB | reference |
| Cv0 fixed+variable grounded at shunt midpoint(3,GND) | 5⅓ | 0.889513621 dB | 30.005/30.005 dB | +0.000723 dB |
| Cf1 PCB relocated to LsB(3,4) | 5⅓ | 0.889847814 dB | 30.005/30.005 dB | +0.001057 dB |
| Cp GJM grounded at shunt midpoint(3,GND) | 5⅓ | 0.891534870 dB | 30.005/30.005 dB | +0.002744 dB |
| Other novel DTC/fixed C connections | 5⅓ | 0.912011–3.548991 dB | H2/H3 ≥30 dB | worse in locally searched designs |

### Selected novel best 4L circuit

LQP02HV/Q25: L0(0,1)=**2.026102nH**, L1(1,2)=**7.902511nH**, LsA(1,3)=**2.280010nH**, LsB(3,4)=**1.409679nH**. Fixed Q80 GJM Cf0(0,1)=**4.047632pF**, Cp(4,GND)=**0.773346pF**. PCB-C/Q40 **Cf1(0,2)=0.084617pF**. DTC/Q35 Cv0(4,GND), Cv1(0,1), Cv2(1,2), each 0–3pF per band setting. Permanent and separate Cv0 Cpar=(4,GND)=**0.5pF/Q40** even at OFF. The **physical L count4, GJM2, PCB-C1 and 3 DTC resources** are unchanged from EXP-051; chip area remains **5⅓**. Full detailed topology/capacitance values are in [selected best checkpoint](checkpoints/cf1_input_output_best.json).

- Independent explicit coupled-inductor **9×9 MNA 84-point PASS**, maximum IL discrepancy `1.5987e−13dB`, power-balance residual `9.5410e−18W`. See [best MNA verification](validation/cf1_input_output_independent_mna.json).
- The two alternate retained topology points: [retuned unchanged reference](checkpoints/reference_best.json) and [Cv0-at-midpoint](checkpoints/cv0_at_shunt_mid_best.json). Independent MNA overlays under `validation/`.
- The prior EXP-051 same schematic used a stricter **internal 30.02dB** guard and achieved IL0.888992895dB. EXP-052 uses **internal 30.005dB**, with RF-T007 mandatory minimum unchanged at **30dB**. To isolate a topological change from the guard change, the **fair same-guard** comparison is 0.885189326 vs 0.888790901dB, showing about **0.003602dB** nominal topology benefit. Comparing to EXP-051 published checkpoint directly would show about 0.003804dB but conflates internal guard conditions.
- The **new PCB-C bridge** is a new circuit branch connection, not a new extra component or a relaxation of the PCB-C ceiling. Existing T007 formal base RF-F003 unchanged.

**Scope:** This completes a nominal constant-Q, finite 28×1001-point, local 4L topology study and 84-point independent-MNA check. The owner explicitly declined additional harmonic attenuation margin optimization and physical mutual coupling realism work; neither was researched. Arithmetic positive definiteness/|k| bound checks remain part of the unchanged RF numerical validity. Phase3 is still not authorized. The small nominal IL difference is not a statement of global optimality or production hardware performance.

