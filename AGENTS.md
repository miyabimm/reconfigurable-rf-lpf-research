# Reconfigurable RF-LPF Research — Agent Instructions

## Purpose and sources of truth

Research a passive reconfigurable RF low-pass filter for six LTE settings, balancing worst-case insertion loss, harmonic suppression, chip-area cost, physical feasibility, and reproducibility. Combine circuit-topology invention with bounded numerical search; never present best-found results as proven global optima.

Read only the **documents relevant to the task**, using the latest available `main` version for material scientific or development decisions:

- **Operating authority and approvals:** [`project/instructions.md`](project/instructions.md).
- **Formal RF numbers:** the immutable JSON selected by `active_formal_id` in [`rf/constraints/registry.json`](rf/constraints/registry.json); trial constraints require explicit opt-in. **Bands:** [`rf/bands.csv`](rf/bands.csv). **Fixed S2P:** files and hashes specified by the active constraint.
- **Scientific interpretation:** [`project/specification.md`](project/specification.md) (not a separate numeric authority). **Current work and gates:** [`project/roadmap.md`](project/roadmap.md), Issues, and PRs.
- **Experiment evidence:** [`data/experiment_index.csv`](data/experiment_index.csv) and `experiments/.../EXP-NNN/`. **For new EXP:** [`project/experiment_storage_policy.md`](project/experiment_storage_policy.md). **For staged SLSQP:** [`project/slsqp_iteration_policy.md`](project/slsqp_iteration_policy.md).

Do not duplicate changing RF limits, results, or Stage status here. If source access fails, report what remains unverified. A roadmap item is not an implemented API or available runner.

## Authority: proceed or stop

- **Owner:** decides material RF/scientific-contract changes, new experiments and large production runs, important research-data changes, and research-phase transitions.
- **ChatGPT:** research PM / RF technical lead; proposes topology and search directions, manages scope, and independently reviews pushed diffs and evidence.
- **Codex / Pi Code:** implement, self-test, and prepare a review branch or Draft PR within the delegated scope. Do not assume an unimplemented Pi Code local-search runner exists.
- **Proceed autonomously** on ordinary engineering, limited theoretical calculations, and bounded checks already within approved scope.
- **Stop for owner approval** before changing RF constraints or model/metric meaning, materially changing search budgets or fairness, launching an unapproved scientific EXP or major computation, or modifying/deleting important saved results and checkpoints.

Research stays in **Phase 2** until the owner explicitly authorizes Phase 3. Software-development Stages are separate; completion requires the roadmap's actual gates.

## Implementation and review

For substantial changes use **Issue with scope/acceptance criteria → focused implementation and verification → Draft PR → ChatGPT independent review → fix/re-review → merge within delegated scope → check `main`**. Reuse an existing Issue for small related fixes.

Prefer the smallest correct change (KISS/YAGNI), existing code, and risk-based regression checks. Add a RED test when it demonstrates a relevant defect or contract, then make the minimum GREEN change. Do not create speculative frameworks, blanket test suites, or unrelated refactors. Review the actual pushed diff and check outputs: self-tests, CI PASS, design approval, permission to run, and scientific acceptance are different decisions.

## Scientific invariants

- Use **all six settings and all 28 separate UL/DL/H2/H3 intervals** from `rf/bands.csv`: worst-case passband IL and minimum stopband attenuation; do not bridge frequency gaps.
- Respect the active condition's source/load, complete fixed-S2P external-port cascade and hashes, component/Q/layout limits, variable-C settings, couplings, and area objective. Do not silently reuse legacy limits.
- Validate full inductance-matrix **SPD**, circuit connectivity, passivity, power balance, and independent **MNA** at the validation level required by the task. Distinguish a bare-LPF result from external-port system performance.
- Compare only like-for-like constraint ID/effective SHA, reference planes, evaluation grids, and validation depth. Keep formal/trial/historical and `matching_only`/`full_lpf` results separate.
- Explicitly label finite-grid limits, nonconvergence, model assumptions, and unverified SRF, Q(f), EM, tolerance, or measurements. Never infer physical feasibility or continuous-frequency guarantees from a simulation alone.

## Experiments and evidence

New scientific EXPs require **separate owner approval plus an EXP number reserved and verified on `main` before execution**. Routine deterministic software tests are not new scientific EXPs. Follow the applicable storage policy; do not retrospectively rewrite historical manifests, vectors, findings, or validation status.

Preserve reproducibility: constraint ID/SHA, bands/S2P fingerprints, commit/dirty patch, environment and seed, complete circuit and all six variable-C settings, search budget/grid, termination state, and independent-validation evidence. Distinguish planned, run, converged, nonconverged, failed, unverified, and preserved states. Never delete or migrate historical research evidence as routine cleanup.

## Pi sparse workspace

Pi Code's normal working tree excludes `docs/`, `data/` and `experiments/`. Read `project/README.md` and use the `project/` and `rf/` inputs. Immutable RF snapshots contain historical logical `data/...` paths; the RF loader resolves them to the byte-identical `rf/` files and must fail rather than fall back to missing legacy files. Full historical EXP audits, source recovery and EXP-number reservation require a separately obtained complete evidence checkout; do not label an incomplete sparse audit as PASS. This repository migration remains Draft/unfinished until the owner-approved cutover.

## Environment and handoff

Python **3.12**, `pyproject.toml`, and `uv.lock` govern the environment. Use commands already supported by current CI; for example:

```bash
uv sync --frozen
uv run --frozen python -m unittest discover -s tests -p 'test_phase2_branch_mna.py' -v
uv run --frozen python scripts/audit_new_experiment_storage.py audit
```

Select checks appropriate to the change; do not claim unexecuted checks passed. At meaningful handoff, provide the Issue/scope, branch and HEAD SHA, PR URL if any, RF condition ID/effective SHA when applicable, actual checks/results, limitations, and approvals still needed. Write review and research reports primarily in Japanese.
