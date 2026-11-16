#!/usr/bin/env python3
"""Freeze Issue #439's 20 legal-or-invalid full-physical-range Sobol starts.

This preparation is deterministic for the pinned main/source and seeds. It does
not call an RF evaluator or launch a solver. All starts are generated and
validated before any search job is allowed to start.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np
import scipy
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from lpf.constraint_versions import constraint_fingerprint, load_constraint, rf_input_file
from lpf.rf_core import build_rf_model
from lpf.search._development_runner import _weighted_plan
from lpf.search._job_evaluation import source_identity
from lpf.search.component_constraints import physical_bounds, validate_values
from lpf.search.performance import build_evaluation_grid, compile_requirements
from lpf.search.proposals import definition_from_data
from lpf.search.starts import IllegalStart, generate_for_definition
from lpf.search.storage import sha, vector_sha

OUT = Path(__file__).resolve().parent
SEEDS = list(range(1001, 1021))
MAIN = "79789f2f3a4b8a9feece9a4cc9a212b4c086f1ed"
RF_SHA = "e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532"
DEFINITION_BYTE_SHA = "e8ac857c063e0b9d2eb8eaf629c2e4b700a694e9241f3bbc596d99f6374487f6"
DEFINITION_CANONICAL_SHA = "bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068"
CHECKPOINT_BYTE_SHA = "4fbd86e8b46ad7bcb550ba327672b0983e8b58e9ce4b2a9364f8c6557a812b4b"
BANDS_SHA = "1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe"


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def main() -> None:
    head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    ancestor = subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", MAIN, "HEAD"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    source_diff = subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", MAIN, "HEAD", "--",
                                  "src", "pyproject.toml", "uv.lock", "scripts/run_rf_search.py"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if ancestor.returncode != 0 or source_diff.returncode != 0:
        raise SystemExit(f"STOP: source tree is not identical to pinned main {MAIN}")
    status = subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain=v1", "--", "src", "pyproject.toml", "uv.lock", "scripts/run_rf_search.py"], text=True)
    if status:
        raise SystemExit(f"STOP: source files are dirty: {status}")
    if {k: os.environ.get(k) for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")} != {
        "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"
    }:
        raise SystemExit("STOP: numerical thread counts must all be one")

    definition_path = ROOT / "project/diagnostics/issue361/definition.json"
    checkpoint_path = ROOT / "experiments/chatgpt_topology_search/runs/EXP-062/checkpoints/a6_best.json"
    base_config_path = ROOT / "project/diagnostics/issue433/hybrid.json"
    bands_path = ROOT / "rf/bands.csv"
    definition_data = json.loads(definition_path.read_bytes())
    checkpoint = json.loads(checkpoint_path.read_bytes())
    if file_sha(definition_path) != DEFINITION_BYTE_SHA or sha(definition_data) != DEFINITION_CANONICAL_SHA:
        raise SystemExit("STOP: definition fingerprint mismatch")
    if file_sha(checkpoint_path) != CHECKPOINT_BYTE_SHA:
        raise SystemExit("STOP: EXP-062 checkpoint fingerprint mismatch")
    if file_sha(bands_path) != BANDS_SHA:
        raise SystemExit("STOP: bands fingerprint mismatch")
    if checkpoint.get("candidate_id") != "EXP062-A6-grounded-best" or vector_sha(checkpoint["vector"]) != "4131fa4e677afd364c8e448325d2971f05214284047c349bf2f794585668313c":
        raise SystemExit("STOP: reference checkpoint identity mismatch")

    policy = load_constraint("RF-T008", root=ROOT, allow_trial=True)
    if constraint_fingerprint(policy) != RF_SHA:
        raise SystemExit("STOP: RF-T008 effective SHA mismatch")
    definition = definition_from_data(definition_data)
    model = build_rf_model(definition, policy)
    requirements = compile_requirements(policy, rf_input_file(ROOT, policy["bands_file"]), "full_lpf")
    if len(requirements.intervals) != 28 or len({row.case for row in requirements.intervals}) != 6:
        raise SystemExit("STOP: expected all 6 settings / 28 intervals")
    hard = np.asarray(physical_bounds(model.definition, model.schema, policy))
    if hard.shape != (25, 2) or not np.all(hard[:, 1] > hard[:, 0]):
        raise SystemExit("STOP: expected 25 freely sampled physical coordinates")

    with base_config_path.open() as stream:
        base = yaml.safe_load(stream)
    if (base.get("rf") != {"constraint_id": "RF-T008", "allow_trial": True}
            or base.get("objective") != "full_lpf"
            or base["arms"][0]["steps"][0]["solver"] != "hybrid"
            or base["arms"][0]["steps"][0]["aggregation"] != "sum"):
        raise SystemExit("STOP: base config does not match frozen Trial/full_lpf Hybrid contract")

    rf_input_fingerprints = {}
    for name in ("bands_file",):
        path = rf_input_file(ROOT, policy[name])
        rf_input_fingerprints[str(path.relative_to(ROOT))] = file_sha(path)
    parasitics = policy["external_port_parasitics"]
    for name in ("input_parasitic", "output_parasitic"):
        item = parasitics[name]
        path = rf_input_file(ROOT, item["path"])
        digest = file_sha(path)
        if digest != item["sha256"]:
            raise SystemExit(f"STOP: fixed S2P hash mismatch: {name}")
        rf_input_fingerprints[str(path.relative_to(ROOT))] = digest

    source = source_identity(ROOT)
    source["head"] = MAIN
    plan_rows, starts = {}, []
    for seed in SEEDS:
        config = copy.deepcopy(base)
        config["seeds"] = [seed]
        config_path = OUT / "inputs" / f"seed-{seed}.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True))

        generated_path = OUT / "generated" / f"seed-{seed}.json"
        try:
            record = generate_for_definition(definition, policy, seed)
        except IllegalStart as exc:
            record = exc.record
        record["status"] = record.get("status", "illegal")
        if record["status"] == "legal":
            if record["method"] != "scrambled_sobol_single_point" or record["sobol_index"] != 0:
                raise SystemExit(f"STOP: unexpected generator metadata at seed {seed}")
            check = validate_values(model.definition, model.schema, record["vector"], policy, frozen_model=model)
            if not check["component_policy_pass"] or check["connection_role_evidence_incomplete"]:
                raise SystemExit(f"STOP: physical/SPD/role check failed at seed {seed}")
            record["physical"] = check
            start_input = {str(seed): {"vector": record["vector"], "vector_sha256": record["vector_sha256"]}}
            write_json(OUT / "inputs" / f"seed-{seed}-starts.json", start_input)
        else:
            record["status"] = "illegal_start_not_run"
            (OUT / "inputs" / f"seed-{seed}-starts.json").unlink(missing_ok=True)
        write_json(generated_path, record)

        plan = _weighted_plan(config_path, ROOT, "hybrid", 150000)
        stage = plan.data["config"]["arms"][0]["steps"][0]
        costs = plan.data["costs"]["jobs"]["hybrid"]
        if (stage["options"]["max_evaluations"] != 150000 or stage["options"]["maxiter"] != 150000
                or stage["max_requested_samples"] != 10_500_000
                or costs["selection_upper_reservation"] != 84
                or costs["terminal_fixed_reservation"] != 476
                or costs["total_upper_reservation"] != 10_500_560):
            raise SystemExit(f"STOP: static plan/cost contract mismatch at seed {seed}")
        plan_rows[str(seed)] = dict(
            config_path=str(config_path.relative_to(ROOT)),
            config_sha256=file_sha(config_path),
            starts_path=str((OUT / "inputs" / f"seed-{seed}-starts.json").relative_to(ROOT)),
            starts_sha256=(file_sha(OUT / "inputs" / f"seed-{seed}-starts.json")
                           if record["status"] == "legal" else None),
            generated_path=str(generated_path.relative_to(ROOT)),
            generated_sha256=file_sha(generated_path),
            status=record["status"], vector=record.get("vector"),
            vector_sha256=record.get("vector_sha256"), reason=record.get("reason"),
            method=record.get("method"), sobol_index=record.get("sobol_index"),
            plan_sha256=plan.sha256, static_costs=costs)
        starts.append(dict(seed=seed, status=record["status"], vector=record.get("vector"),
                           vector_sha256=record.get("vector_sha256"), reason=record.get("reason"),
                           method=record.get("method"), sobol_index=record.get("sobol_index"),
                           physical=record.get("physical")))

    if len(starts) != 20 or [r["seed"] for r in starts] != SEEDS:
        raise SystemExit("STOP: incomplete seed preflight")
    legal = [r for r in starts if r["status"] == "legal"]
    legal_sha = [r["vector_sha256"] for r in legal]
    if len(set(legal_sha)) != len(legal_sha):
        raise SystemExit("STOP: duplicate Sobol vectors")

    # Issue's maximum full-scope arithmetic; the solver consumes less on convergence.
    max_primary = 20 * 10_500_560 + 20 * 70 + 5 * (28_028 + 84)
    if max_primary != 210_153_160 or max_primary > 211_000_000:
        raise SystemExit("STOP: total primary RF sample budget arithmetic mismatch")
    preflight = dict(
        issue=439, purpose="development_limited_random_start_weighted_hybrid",
        source_head=MAIN, preparation_head=head,
        preparation_script_sha256=file_sha(OUT / "prepare.py"),
        source_identity=source, source_identity_sha256=sha(source),
        environment=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__,
                         threads={k: os.environ.get(k) for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")},
                         uv_lock_sha256=file_sha(ROOT / "uv.lock")),
        rf=dict(constraint_id="RF-T008", allow_trial=True, objective="full_lpf",
                effective_sha256=constraint_fingerprint(policy), bands_sha256=file_sha(bands_path),
                fixed_s2p_sha256=rf_input_fingerprints),
        definition=dict(path=str(definition_path.relative_to(ROOT)), byte_sha256=file_sha(definition_path),
                        canonical_sha256=sha(definition_data), vector_length=25,
                        vector_layout=dict(L_nH=[0, 4], fixed_C_pf=[4, 8], signed_k=[8, 11],
                                           IC_fixed_C_pf=[11, 13], variable_C_by_setting_pf=[13, 25],
                                           variable_setting_order=["B71", "B12", "B28", "B13+B14", "B26", "B8"]),
                        topology="4L2C / same as EXP-062 A6"),
        physical_model=dict(units_by_slice=dict(L_nH=[0, 4], fixed_C_pf=[4, 8], signed_k=[8, 11],
                                                IC_fixed_C_pf=[11, 13], variable_C_by_setting_pf=[13, 25]),
                            complete_hard_bounds=hard.tolist(),
                            hard_bounds_sha256=sha(hard.tolist()),
                            variable_schema=dict(n_inductors=model.schema.n_inductors,
                                                 n_fixed=model.schema.n_fixed, n_coupling=model.schema.n_coupling,
                                                 n_ic_fixed=model.schema.n_ic_fixed, n_variable=model.schema.n_variable,
                                                 constant_caps_pf=list(model.schema.constant_caps_pf))),
        base_config=dict(path=str(base_config_path.relative_to(ROOT)), byte_sha256=file_sha(base_config_path)),
        frozen_solver=dict(mode="weighted_violation", formula="max(0, worst_pass_IL-0.30)^2 + 100*mean(max(0,30.01-H2/H3)^2)",
                           strict_harmonic_db=30.0, margin_db=30.01, IL_weight=1, H_weight=100,
                           solver="Hybrid", aggregation="sum", maxiter=150000, max_evaluations=150000,
                           max_restarts=0, restart_sigma=0.1, search_points_per_interval=2,
                           stop_points_per_interval=3, search_samples_per_forward=70,
                           selection_samples=84, terminal_points_per_interval=17, terminal_samples=476,
                           selection_top_k=1, checkpoint_interval=100, terminal_spot_indices=[0, 111]),
        seed_range=SEEDS, generation_rule="starts.generate_for_definition; scrambled Sobol; one point; index 0; entire 25-coordinate physical hard box; no repair/retry/clip",
        starts=starts, per_seed=plan_rows,
        totals=dict(proposed=20, legal=len(legal), illegal=len(starts)-len(legal),
                    search_forward_cap=3_000_000, per_job_search_forward_cap=150_000,
                    max_primary_samples=max_primary, authorized_primary_samples_cap=211_000_000,
                    maximum_independent_mna_samples=460,
                    dense_validation_candidates_max=5, dense_points_per_interval=1001,
                    primary_samples_per_dense_candidate=28_028, primary_mna_comparison_samples_per_candidate=84))
    write_json(OUT / "preflight.json", preflight)
    print(json.dumps(dict(preflight_path=str(OUT / "preflight.json"),
                          preflight_sha256=file_sha(OUT / "preflight.json"),
                          legal=len(legal), illegal=len(starts)-len(legal),
                          max_primary_samples=max_primary, seeds=[dict(seed=r["seed"], status=r["status"],
                          vector_sha256=r.get("vector_sha256"), reason=r.get("reason")) for r in starts]),
                     indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
