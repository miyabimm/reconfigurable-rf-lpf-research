"""Frozen EXP-042/055/058 numerical parity with reusable Phase-2 evaluators.

These tests make no new optimization or physical-compliance claims.  At three
samples per interval, they compare legacy and shared transfer calculations.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lpf.constraint_versions import load_constraint
from lpf.phase2_models import exp042, exp055, exp058_area3, exp058_area4, exp058_area4l_gjm

RUNS = ROOT / "experiments/chatgpt_topology_search/runs"
SNAP = ROOT / "data/pareto_snapshots"


def frozen(script, name):
    spec = importlib.util.spec_from_file_location(
        "frozen_eval_" + name, RUNS / script
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to locate frozen experiment module: " + script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def data(path):
    return json.loads(path.read_text(encoding="utf-8"))


class Phase2SharedEvaluatorParityTests(unittest.TestCase):
    def compare_models(self, historical, shared, vector):
        left = historical.il(vector)
        right = shared.il(vector)
        self.assertEqual(left.shape, (28 * 3,))
        np.testing.assert_allclose(right, left, atol=1e-9, rtol=0)
        self.assertEqual(historical.role.tolist(), shared.role.tolist())
        self.assertEqual(historical.setting.tolist(), shared.setting.tolist())
        self.assertEqual(historical.segment.tolist(), shared.segment.tolist())
        for name in ("pre", "post"):
            np.testing.assert_allclose(
                getattr(historical, name), getattr(shared, name), atol=1e-12, rtol=0
            )

    def test_exp042_rf_t005_full_s2p(self):
        old = frozen("EXP-042/optimize.py", "exp042")
        policy, vector = old.policy_and_seed()
        a = old.Evaluator(policy, 3)
        b = exp042.Evaluator(policy, 3)
        self.compare_models(a, b, vector)
        self.assertEqual(a.summary(vector), b.summary(vector))

    def test_exp055_rf_t007_shunt_parasitic(self):
        old = frozen("EXP-055/adapt_f003_4l.py", "exp055")
        policy = load_constraint("RF-T007", allow_trial=True)
        checkpoint = data(RUNS / "EXP-055/checkpoints/cv1_input_tip_best.json")
        vector = np.asarray(checkpoint["vector"], float)
        for name, parasitic in (("cv1_input_tip", True), ("two_dtc", False)):
            with self.subTest(name=name, parasitic=parasitic):
                a = old.Evaluator(policy, 3, name, parasitic)
                b = exp055.Evaluator(policy, 3, name, parasitic)
                self.compare_models(a, b, vector)
                self.assertEqual(a.summary(vector), b.summary(vector))
        result = exp055.independent_mna(policy, vector, "cv1_input_tip", 3)
        self.assertTrue(result["pass"], result)

    def test_exp058_3l_rft008_composite(self):
        old = frozen("EXP-058/sweep_area3.py", "exp058_area3")
        policy = load_constraint("RF-T008", allow_trial=True)
        snapshot = data(SNAP / "rf_t008_exp058_area3_to_3p667_20261020.json")
        for row in snapshot["observed_nondominated"]:
            gjm = 0 if row["GJM_count"] else None
            vector = np.asarray(row["vector"], float)
            with self.subTest(gjm=gjm):
                a = old.Evaluator(policy, "shunt_output", 3, gjm)
                b = exp058_area3.Evaluator(policy, "shunt_output", 3, gjm)
                self.compare_models(a, b, vector)
                self.assertEqual(a.summary(vector), b.summary(vector))
        chk = exp058_area3.independent_mna(
            exp058_area3.Evaluator(policy, "shunt_output", 3),
            np.asarray(snapshot["observed_nondominated"][0]["vector"], float),
            policy, "shunt_output",
        )
        self.assertTrue(chk["pass"], chk)

    def test_exp058_4l_zero_gjm(self):
        old = frozen("EXP-058/sweep_area4.py", "exp058_area4")
        policy = load_constraint("RF-T008", allow_trial=True)
        row = data(SNAP / "rf_t008_exp058_area4_20261020.json")["best_cost_cell"]
        vector = np.asarray(row["vector"], float)
        a = old.Evaluator(policy, "shunt_output", "cp", 3)
        b = exp058_area4.Evaluator(policy, "shunt_output", "cp", 3)
        self.compare_models(a, b, vector)
        self.assertEqual(a.summary(vector), b.summary(vector))
        self.assertTrue(exp058_area4.independent_mna(
            policy, "shunt_output", "cp", vector
        )["pass"])

    def test_exp058_4l_mixed_gjm_pcb(self):
        old = frozen("EXP-058/sweep_area4l_gjm.py", "exp058_area4l_gjm")
        policy = load_constraint("RF-T008", allow_trial=True)
        row = data(SNAP / "rf_t008_exp058_area4p667_20261020.json")["best"]
        vector = np.asarray(row["vector"], float)
        a = old.Evaluator(policy, "input_output", ("cf0",), 3)
        b = exp058_area4l_gjm.Evaluator(policy, "input_output", ("cf0",), 3)
        self.compare_models(a, b, vector)
        self.assertEqual(a.summary(vector), b.summary(vector))
        self.assertTrue(exp058_area4l_gjm.independent_mna(
            policy, "input_output", ("cf0",), vector
        )["pass"])

    def test_shared_library_import_boundary_and_new_exp_guard(self):
        import re
        library = ROOT / "src/lpf/phase2_models"
        for source_file in library.glob("*.py"):
            source = source_file.read_text(encoding="utf-8")
            with self.subTest(source=source_file.name):
                self.assertNotIn("sys.path.insert(", source)
                self.assertNotRegex(
                    source,
                    r"(?m)^\\s*(?:import|from)\\s+"
                    r"(?:adapt_f003_4l|sweep_area3|sweep_area4|"
                    r"sweep_area4l_gjm|optimize)\\b",
                )
        # All legacy EXP-050–068 source files are immutable research evidence.
        # Audit only NEW scripts (not their archived copies) for reintroduced
        # direct dependencies on frozen evaluators.
        for run_dir in RUNS.glob("EXP-*"):
            if not run_dir.name[4:].isdigit() or int(run_dir.name[4:]) <= 68:
                continue
            for script in run_dir.glob("*.py"):
                source = script.read_text(encoding="utf-8")
                with self.subTest(future_script=str(script.relative_to(ROOT))):
                    self.assertNotRegex(
                        source, r"sys\\.path\\.[^\\n]*EXP-(?:042|055|058)"
                    )
                    self.assertNotRegex(
                        source,
                        r"(?m)^\\s*(?:import\\s+"
                        r"(?:optimize|adapt_f003_4l|sweep_area[34]\\w*)\\b|"
                        r"from\\s+(?:optimize|adapt_f003_4l|sweep_area[34]\\w*)\\s+import\\b)",
                    )


if __name__ == "__main__":
    unittest.main()
