"""Regression tests for canonical terminal mapping of saved RF-F002 seeds."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments" / "matching_limit"))
sys.path.insert(0, str(ROOT / "scripts"))

from full_lpf import FullLPFProblem
from full_lpf_checkpoint_import import checkpoint_to_task
from lpf.constraint_versions import load_constraint


class FullLPFCheckpointImportTests(unittest.TestCase):
    CASES = (
        ("EXP-023", "experiments/chatgpt_topology_search/runs/EXP-023/"
         "RFF002-P2-4L-2C-35DB-01.json", 0.4601802953937566,
         35.01999999842035, 35.01999999744076),
        ("EXP-017", "experiments/chatgpt_topology_search/runs/EXP-017/"
         "EXP017-LQW2-H35.json", 0.37879791410736385,
         35.0299999996103, 35.02999999875094),
    )

    def test_saved_ports_are_remapped_and_checkpoint_metrics_reproduce(self):
        policy = load_constraint("RF-F002")
        for label, relative_path, expected_il, expected_h2, expected_h3 in self.CASES:
            with self.subTest(candidate=label):
                path = ROOT / relative_path
                saved = json.loads(path.read_text(encoding="utf-8"))
                task = checkpoint_to_task(path)
                self.assertEqual(task["canonical_terminal_map"]["source"], 1)
                self.assertEqual(task["canonical_terminal_map"]["load"], 2)
                self.assertEqual(task["canonical_terminal_map"]["ground"], 0)
                self.assertEqual(task["canonical_terminal_map"]["source_checkpoint_nodes"], {
                    "ground": saved["topology"]["ground_node"],
                    "source": saved["topology"]["input_node"],
                    "load": saved["topology"]["output_node"],
                })
                graph = (task["graph"][0], tuple(tuple(edge) for edge in task["graph"][1]))
                layout = {
                    "edges": tuple(tuple(edge) for edge in task["variable_layout"]["edges"]),
                    "roles": tuple(task["variable_layout"]["roles"]),
                }
                problem = FullLPFProblem(
                    graph, layout, task["initial_coupling"], physical_order=task["physical_order"],
                    passband_points=9, stopband_points=9, resolved_policy=policy)
                initial = problem.initial_vector(
                    task["initial_base_values"],
                    coupling_values=task["initial_coupling_values"])
                dense, _ = problem._verify_candidate(initial, 21)
                self.assertAlmostEqual(dense["worst_il_db"][0], expected_il, delta=1e-6)
                self.assertAlmostEqual(dense["min_h2_db"][0], expected_h2, delta=1e-6)
                self.assertAlmostEqual(dense["min_h3_db"][0], expected_h3, delta=1e-6)
                self.assertEqual(task["source_candidate_id"], saved["candidate_id"])

    def test_perturbations_are_reproducible_and_distinct(self):
        path = ROOT / self.CASES[0][1]
        first = checkpoint_to_task(path, perturb_fraction=0.005, perturbation_seed=20261014)
        second = checkpoint_to_task(path, perturb_fraction=0.005, perturbation_seed=20261014)
        baseline = checkpoint_to_task(path)
        self.assertEqual(first["initial_base_values"], second["initial_base_values"])
        self.assertNotEqual(first["initial_base_values"], baseline["initial_base_values"])
        self.assertEqual(first["initial_coupling"], baseline["initial_coupling"])
        self.assertEqual(first["variable_layout"], baseline["variable_layout"])

    def test_perturbation_requires_a_seed_and_trial_candidates_are_refused(self):
        path = ROOT / self.CASES[0][1]
        with self.assertRaisesRegex(ValueError, "deterministic perturbation_seed"):
            checkpoint_to_task(path, perturb_fraction=0.005)
        with self.assertRaisesRegex(ValueError, "RF-F002 full_lpf"):
            checkpoint_to_task(ROOT / "data/validation/rft003_20261012/target30_results.json")


if __name__ == "__main__":
    unittest.main()
