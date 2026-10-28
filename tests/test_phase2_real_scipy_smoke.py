"""Issue #198: opt-in, one-start wiring check; never scientific EXP evidence.

Run explicitly (stdout is a temporary verification record, not EXP storage)::

    LPF_REAL_SCIPY_SMOKE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
      uv run --frozen python -m unittest discover -s tests \
      -p 'test_phase2_real_scipy_smoke.py' -v

Default discovery skips the solver. No multistart, budget override, dense/MNA
validation, candidate promotion or production result persistence is provided.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import unittest

import numpy as np
import scipy
import scipy.optimize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from test_phase2_problem_seed import make, seed
from lpf.phase2_models.problem_seed import definition_fingerprint
from lpf.phase2_models.staged_optimization import (
    minimize, run_c1_staged, scipy_slsqp_stage,
)
from lpf.slsqp_budget import STANDARD_SLSQP_BUDGET


@unittest.skipUnless(os.environ.get("LPF_REAL_SCIPY_SMOKE") == "1",
                     "opt-in real SciPy smoke (Issue #198)")
class RealScipySmoke(unittest.TestCase):
    def test_one_existing_legal_start(self):
        # Same 3L fixture and nominal-zero correction as
        # ProblemSeedTests.test_box_seed_all_trials_and_topologies.
        problem, vector = make("RF-T005", 3)  # fixture opts into trial explicitly
        vector[6] = 0.0  # non-neighbor pair: nominal k must be zero
        self.assertTrue(problem.circuit.validate_components(vector)["component_policy_pass"])
        initial = seed(problem, vector)  # existing deterministic seed=23, no jitter
        self.assertEqual(initial["changes"], ())
        self.assertIs(minimize, scipy.optimize.minimize)  # no mock solver

        def git(*args):
            return subprocess.check_output(["git", *args], cwd=ROOT, text=True)

        # Capture tracked patch AND untracked inputs before any solver call.
        patch = git("diff", "HEAD", "--binary")
        untracked = git("ls-files", "--others", "--exclude-standard").splitlines()
        provenance = {
            "head": git("rev-parse", "HEAD").strip(),
            "status": git("status", "--porcelain"),
            "dirty_patch": patch,
            "dirty_patch_sha256": hashlib.sha256(patch.encode()).hexdigest(),
            "untracked_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                                 for p in untracked},
            "smoke_file_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        }
        preflight = {
            "purpose": "isolated_temporary_software_verification_not_EXP",
            "policy_id": problem.policy_id,
            "effective_constraint_sha256": problem.policy_fingerprint,
            "vector_source": "tests/test_phase2_problem_seed.py::make(RF-T005, 3); "
                             "nominal-zero correction from existing ProblemSeedTests",
            "definition_sha256": definition_fingerprint(problem.circuit.definition),
            "seed_record": initial,
            "starts": 1, "coarse_points_per_interval": 1, "fine_points_per_interval": 2,
            "iteration_policy_id": "slsqp-staged-v2",
            "budget": {**STANDARD_SLSQP_BUDGET.as_dict(), "policy_id": "slsqp-staged-v2"},
            "python": sys.version, "scipy": scipy.__version__, "numpy": np.__version__,
            "platform": platform.platform(), "source_provenance": provenance,
            "threads": {k: os.environ.get(k) for k in
                        ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")},
        }
        print("PREFLIGHT " + json.dumps(preflight, allow_nan=False), flush=True)
        real_calls = []

        def real_stage(p, x, maxiter, target):
            real_calls.append((p.points_per_interval, maxiter))
            return scipy_slsqp_stage(p, x, maxiter, target)

        result = run_c1_staged(problem.circuit, initial, coarse_points=1, fine_points=2,
                               optimize_stage=real_stage, source_provenance=provenance)
        print("RESULT " + json.dumps(result, allow_nan=False), flush=True)
        self.assertGreaterEqual(len(real_calls), 1)
        self.assertLessEqual(len(real_calls), 4)
        self.assertEqual(real_calls[0], (1, 240))
        self.assertEqual(result["policy_id"], "RF-T005")
        self.assertEqual(result["iteration_policy_id"], "slsqp-staged-v2")
        self.assertEqual(result["budget"], {**STANDARD_SLSQP_BUDGET.as_dict(),
                                             "policy_id": "slsqp-staged-v2"})
        self.assertEqual(result["grids"]["coarse"]["segment_count"], 28)
        self.assertEqual(result["grids"]["fine"]["sample_count"], 56)
        self.assertTrue(result["candidate_promotion_blocked"])
        self.assertFalse(result["rf_compliance_certified"])
        self.assertTrue(all(v == "not_run" for v in result["validation"].values()))
        # Nonconvergence is allowed; an evaluation/solver exception is not a
        # successful wiring check. The complete diagnostic was printed above.
        self.assertIn(result["numerical_state"], ("converged", "not_converged"))
        self.assertEqual(real_calls[1], (2, 120))
        for stage in result["stage_calls"]:
            self.assertIsNone(stage["exception"])
            self.assertGreater(stage["status"]["nfev"], 0)
            self.assertEqual(stage["observation"]["sampled_rf"]["state"], "observed")


if __name__ == "__main__":
    unittest.main()
