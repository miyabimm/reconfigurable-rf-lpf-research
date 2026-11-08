"""Independent unit checks for the distinct full_lpf objective and constraints."""
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments" / "matching_limit"))

from full_lpf import FullLPFProblem, full_lpf_frequency_grid
from lpf.constraint_versions import load_constraint
from lpf.evaluate import CASES, load_bands
from lpf.circuit import solve
from p4_batch import settings_for


class FullLPFObjectiveTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_constraint("RF-F002")
        self.graph = (3, ((1, 2, "LQP02HV"),))
        self.layout = {"edges": ((1, 0), (2, 0)), "roles": (None, None)}

    def problem(self, *, points=2, coupling=None):
        return FullLPFProblem(
            self.graph, self.layout,
            np.eye(1) if coupling is None else coupling,
            constraint_id="RF-F002", passband_points=points, stopband_points=points,
            resolved_policy=self.policy)

    def test_seeded_epigraph_run_is_reproducible_and_independently_checked(self):
        outputs = []
        for _ in range(2):
            problem = self.problem(points=2)
            initial = problem.initial_vector(np.asarray([2.0] + [0.4] * 12))
            outputs.append(problem.optimize(initial, harmonic_targets=(30.0, 35.0),
                                            maxiter=1, ftol=1e-6))
        first, second = outputs
        self.assertEqual(first["continuation_stages"], second["continuation_stages"])
        np.testing.assert_allclose(first["component_values_internal_units"],
                                   second["component_values_internal_units"], atol=0, rtol=0)
        self.assertEqual(first["analysis_mode"], "full_lpf")
        self.assertEqual(first["solver_parameterization"],
                         "normalized_design_variables_minus1_to_plus1_epigraph_db")
        self.assertEqual(first["algorithm_version"],
                         "rf-f002-full-lpf-epigraph-v3-scaled-coordinate-ablation")
        self.assertEqual([stage["harmonic_target_db"] for stage in first["continuation_stages"]],
                         [30.0, 35.0])
        self.assertIn(first["best_found_category"],
                      {"nominal_35db", "mandatory_30_to_35db", "below_mandatory_30db"})
        self.assertTrue(first["independent_validation_by_case"]["B13+B14"]["frequency_count"] > 0)
        self.assertTrue(first["dense_grid_only_not_interval_proof"])

    def test_unscaled_coordinate_ablation_is_explicitly_reported(self):
        problem = self.problem(points=2)
        initial = problem.initial_vector(np.asarray([2.0] + [0.4] * 12))
        result = problem.optimize(initial, harmonic_targets=(30.0,), maxiter=1,
                                  scale_design_variables=False)
        self.assertEqual(result["solver_parameterization"],
                         "physical_design_variables_epigraph_db_unscaled")
        self.assertEqual(result["continuation_stages"][0]["solver_parameterization"],
                         "physical_design_variables_epigraph_db_unscaled")

    def test_segment_grid_keeps_b13_b14_ranges_disjoint(self):
        grid = full_lpf_frequency_grid(load_bands(), passband_points=2, stopband_points=2)
        uplink = {frequency / 1e6 for case, frequency in grid["passband"]
                  if case == "B13+B14"}
        self.assertIn(787.0, uplink)
        self.assertIn(788.0, uplink)
        self.assertNotIn(787.5, uplink)
        self.assertEqual(len(grid["passband"]), len(set(grid["passband"])))

    def test_actual_rf_f002_metrics_use_q50_caps_and_six_shared_settings(self):
        x = np.asarray([2.0] + [0.4] * 12)
        configs = settings_for(self.graph, x, np.eye(1), variable_layout=self.layout,
                               resolved_policy=self.policy, require_explicit_series=True)
        self.assertEqual(tuple(configs), CASES)
        self.assertIn("B13+B14", configs)
        for config in configs.values():
            self.assertEqual([c.q for c in config["capacitors"]], [50, 50])
            self.assertTrue(all(c.value == 0.4e-12 for c in config["capacitors"]))
        problem = self.problem()
        vector = problem.initial_vector(x)
        metrics = problem.metrics(vector)
        self.assertTrue(np.all(np.isfinite(metrics.passband_il)))
        self.assertTrue(np.all(np.isfinite(metrics.stopband_attenuation)))
        self.assertGreater(metrics.coupling_eigenvalue, 0)
        self.assertFalse(problem.is_feasible(vector, 35.0))

    def test_harmonic_violation_cannot_pass_full_lpf_feasibility(self):
        problem = self.problem()
        vector = problem.initial_vector(np.asarray([2.0] + [0.4] * 12))
        residuals = problem.inequality_residuals(vector, 35.0)
        pass_count = len(problem.passband_labels)
        stop_residuals = residuals[pass_count:pass_count + len(problem.stopband_labels)]
        self.assertLess(float(np.min(stop_residuals)), 0.0)
        self.assertFalse(problem.is_feasible(vector, 35.0))

    def test_formal_cap_bound_and_connection_validation_are_enforced(self):
        invalid = np.asarray([2.0] + [1.500001] * 12)
        with self.assertRaisesRegex(ValueError, "capacitance range"):
            settings_for(self.graph, invalid, np.eye(1), variable_layout=self.layout,
                         resolved_policy=self.policy, require_explicit_series=True)
        invalid_layout = {"edges": ((0, 0),), "roles": (None,)}
        with self.assertRaises(ValueError):
            settings_for(self.graph, np.asarray([2.0] + [0.5] * 6), np.eye(1),
                         variable_layout=invalid_layout, resolved_policy=self.policy,
                         require_explicit_series=True)

    def test_fixed_pcb_pattern_c_uses_pf_units_and_formal_bounds(self):
        graph = (3, ((1, 2, "LQP02HV"), (2, 0, "PCB_PATTERN_C")))
        layout = {"edges": ((1, 0), (2, 0)), "roles": (None, None)}
        problem = FullLPFProblem(graph, layout, np.eye(1), resolved_policy=self.policy,
                                 physical_order=(0,), passband_points=2,
                                 stopband_points=2)
        self.assertEqual(problem.base_bounds[1], (0.02, 0.2))
        configs = settings_for(
            graph, np.asarray([2.0, 0.1] + [0.0] * 12), np.eye(1),
            variable_layout=layout, resolved_policy=self.policy,
            require_explicit_series=True)
        for config in configs.values():
            self.assertAlmostEqual(config["capacitors"][0].value, 0.1e-12, delta=1e-24)
            self.assertEqual(config["capacitors"][0].q, 40)

    def test_zero_series_cap_is_an_open_branch_not_a_numerical_short(self):
        graph = (4, ((1, 3, "LQP02HV"),))
        layout = {"edges": ((3, 2), (1, 0)), "roles": ("series", None)}
        configs = settings_for(
            graph, np.asarray([2.0] + [0.0] * 12), np.eye(1),
            variable_layout=layout, resolved_policy=self.policy,
            require_explicit_series=True)
        for config in configs.values():
            with self.subTest(case=next(case for case in CASES if configs[case] is config)):
                result = solve(700e6, **config)
                self.assertEqual(result["gain"], 0.0)
                self.assertTrue(np.isinf(result["il_db"]))
                without_zero_series = dict(
                    config,
                    capacitors=tuple(cap for cap in config["capacitors"]
                                     if (cap.a, cap.b) not in ((3, 2), (1, 0))))
                reference = solve(700e6, **without_zero_series)
                self.assertEqual(result["gain"], reference["gain"])

    def test_invalid_physical_coupling_is_rejected_before_optimization(self):
        graph = (3, ((1, 2, "LQP02HV"), (1, 2, "LQP02HV")))
        with self.assertRaisesRegex(ValueError, "coupling|neighbor|allowed"):
            FullLPFProblem(graph, self.layout, np.asarray([[1.0, 0.2], [0.2, 1.0]]),
                           constraint_id="RF-F002", passband_points=2,
                           stopband_points=2, resolved_policy=self.policy)

    def test_epigraph_contract_reports_passband_residual_separately(self):
        problem = self.problem()
        x = np.asarray([2.0] + [0.4] * 12)
        vector = problem.initial_vector(x)
        metrics = problem.metrics(vector)
        residuals = problem.inequality_residuals(vector, 30.0)
        self.assertEqual(len(residuals), len(problem.passband_labels)
                         + len(problem.stopband_labels) + 1)
        np.testing.assert_allclose(
            residuals[:len(problem.passband_labels)],
            vector[-1] - metrics.passband_il, atol=1e-12)
        self.assertGreaterEqual(residuals[-1], 0.0)


if __name__ == "__main__":
    unittest.main()
