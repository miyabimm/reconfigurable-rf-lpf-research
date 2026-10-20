# Exploratory Node3–GND PCB-C added to reduced EXP-055 2-DTC circuit (2026-10-20 JST)

**Preliminary local Phase 2 numerical finding only.** Not a reserved EXP-NNN, not a GitHub Actions verified run, not a revision to RF-F003 or RF-T007, and not Phase 3.

## User-scoped sole trial deviation

Add **one fixed PCB-pattern capacitor Cg(3,GND), Q40, range 0.02–1.00 pF**. Existing two PCB-pattern capacitors **Cf2(1,2) and Cp(0,3) each remain strictly 0.02–0.20 pF, Q40**. Existing two GJM01/Q80 and four LQP02HV/Q25 and all signed coupling constraints remain unchanged; PCB-pattern C count becomes three, still within the count policy. The two remaining IC variable capacitors are Cv1(0,3), Cv2(1,2), 0–3pF/Q35. Cv0 grounded DTC is absent, so its special permanent RF-T007 0.5pF/Q40 parasite is also absent.

## Observed local numerical results

- Baseline EXP-055-derived unregistered 2-DTC winner (no Cg): six-setting worst IL **0.8497272635469568 dB**.
- With Cg(3,GND), added PCB-C upper bound only for this third new component relaxed to 1pF: new local best worst IL **0.8310463563827374 dB**.
- Improvement over previous 2-DTC baseline: **0.01868090716421944 dB**.
- Original EXP-055 3-DTC winner with T007 grounded parasite stays **0.8173655897607699 dB**, ahead of this new 2-DTC trial by **0.013680766621967488 dB**.
- Minimum H2 **30.004999999383507 dB**; minimum H3 **30.00499999969219 dB**. Only the mandatory nominal 30dB, not 35dB, target met; 0.3dB IL target fails.
- One extra capacitor **Cg=0.37701981046731264 pF** (within the user-authorized sole expansion).
- Full 28 sections × 1001 frequency grid, independent explicit 9×9 coupled-L MNA on 84 frequencies PASS; maximum comparison error **4.34e-13 dB**, maximum passive power residual **1.39e-17 W**, minimum L matrix eigenvalue **2.314507964 nH** > 0.
- 52 local SLSQP trials: initially 8 free-Cg multistarts (trapped at 0.02pF, ~0.850758dB), then eight fixed Cg values × 3 starts, finally 20 free-Cg multistarts warm-starting from fixed 0.35pF basin. Standard 240/120 iteration policy with explicit iteration-limit-only rescue.

## Winning electrical graph and 6 modes

L0(0,1)=2.3214753184281522nH; L1(1,3)=10.093384309414038nH; L2(1,4)=12.683711135351153nH; L3(1,2)=7.602528565554669nH, all HV/Q25, physical one-row L0–L1–L3–L2. Adjacent signed k(L0,L1)=0.04803037031638732; k(L1,L3)=0.037440577694462976; k(L3,L2)=−0.08555976113893447; all others zero.

Cf0 GJM/Q80(0,1)=2.973123536096817pF, Cf1 GJM/Q80(4,GND)=0.5920162032695191pF, Cf2 PCB/Q40(1,2)=0.1999999999999992pF, Cp PCB/Q40(0,3)=0.02pF, **Cg PCB/Q40(3,GND)=0.37701981046731264pF**.

| Setting | Cv1(0,3) pF | Cv2(1,2) pF | Worst IL dB |
|---|---:|---:|---:|
| B71 | 0.7466977724851817 | 1.2538105662071155 | 0.761313882112785 |
| B12 | 0.5983973083889226 | 1.1696970435682423 | 0.7878505023411165 |
| B28 | 0.5971795968196382 | 0.9994081947587842 | 0.8299036640705436 |
| B13+B14 | 0.38887769771131303 | 0.5326612500722977 | 0.7711296024589775 |
| B26 | 0.2592636694423319 | 0.39211098191581173 | 0.82321922477294 |
| B8 | 0 | 0.12746127311389624 | 0.8310463563827374 |

Full-precision 30-vector is in adjacent JSON. File is supplied as curated numerical evidence; the local Python optimizer and 52 raw trial vectors reside in the conversation's generated artifacts and are not yet promoted as immutable official EXP evidence.

## Source and gates

Locally the two external frozen S2P networks were regenerated from the known RF-F003 original RLC circuits on the 0–6GHz / 1MHz grid and RI-interpolated; tested sample S values at 800MHz and both earlier 2-DTC/3-DTC checkpoint worst IL reproduced to numerical precision. **Byte-level original Touchstone SHA hash was NOT checked on this local runtime**. The officially archived original .s2p arrays must be used in a newly and properly pre-reserved EXP run before a verified candidate is promoted.

No proof of global optimum or continuous band extrema; **0.005dB** harmonic margin is fragile; third PCB pattern C 0.377pF is a new physical layout/tolerance/EM unknown. No Q(f), SRF, physical k realization, process tolerance, measured S2P, or Phase 3 check. Formal approved constraints unchanged.