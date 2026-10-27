# Issue #163 / #168 — independent branch-current MNA core

PR-A introduces a **bare network** solver, not an RF acceptance gate. The
input is the Stage 1 `NominalCircuit` and its vector or `CircuitValues`;
`encode` enforces the six-setting schema including fixed and constant C.
The existing trial adapter supplies the separate T007 fixed shunt parasitic
and T008 fixed/variable C branches. Call `validate_components` separately;
this numerical solver does not authorize candidate promotion.

For hot-node voltages V and directed L currents I, with ground omitted and
incidence B, the matrix is `[Yc+Yterm, B; B.T, -Z]`, RHS `[J, 0]`.
`Z = ω(diag(L/Q)+jM)` and `Mij=kij sqrt(Li Lj)`. C branches are stamped
individually as `ωC/(1/Q-j)`. Reversing an L direction requires reversing
all associated signed k values. Explicit source-current and passive grounded
termination-admittance vectors are not resolved RF boundary models. Matrix
conditioning is assessed after 50-ohm row/current scaling; nonfinite,
non-SPD and scaled condition >=1e12 fail closed. This threshold is a
numerical guard, not an RF constraint or proof of physical infeasibility.
The solver does not call the forward nodal/Schur/ABCD machinery.

Synthetic tests cover 3L/4L matrix dimensions and agreement with the forward
nodal solution, including a branched 4L tree with hot-hot C and signed
non-leading coupling slots, with explicit KCL/KVL residual checks. They also
cover direction/sign reversal, OFF trial-specific branches, nonfinite mutual
matrix/eigenvalue classification, and invalid or singular inputs. No new experiment or optimization is run.
S2-01–03/08 remain subject to independent review and broader graph/edge-case
coverage. External S2P, resolved RF boundary, power balance, frozen EXP
parity, dense RF and promotion gates are **not implemented** here; PR-B must
supply separate evidence. No result here certifies RF compliance or physical
realizability. Phase 2 remains in effect.
