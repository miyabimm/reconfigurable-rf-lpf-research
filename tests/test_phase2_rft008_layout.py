"""RF-T008 v3 explicit capacitor-layout injection; archived-vector regressions.

Only frozen candidate vectors and derived test fixtures are evaluated.
No optimization, physical feasibility or new EXP result is claimed.
"""
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lpf.constraint_versions import load_constraint
from lpf.phase2_models.circuit_layout import CapacitorPlacement
from lpf.phase2_models.rft008_layout import RFT008CapacitorLayout
from lpf.phase2_models import exp058_area3, exp058_area4, exp058_area4l_gjm

SNAP = ROOT / "data/pareto_snapshots"


class RFT008CapacitorLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_constraint("RF-T008", allow_trial=True)

    def mixed_layout(self, variable_edges=((0, 3), (1, 2)),
                     fixed_edges=exp058_area4l_gjm.ALL_FIXED):
        return CapacitorPlacement(5, fixed_edges, variable_edges, variable_edges)

    def test_policy_derived_q_bounds_and_separate_dtc_admittance(self):
        layout = self.mixed_layout(variable_edges=((4, -1), (1, 2)))
        spec = RFT008CapacitorLayout.for_policy(
            self.policy, layout, (0,), gjm_lower_pf=0.02
        )
        self.assertEqual(spec.q, (80., 60., 40., 40., 35., 35., 60., 60.))
        self.assertEqual(spec.fixed_bounds_pf,
                         ((0.02, 100.), (0.02, 1.), (0.02, 0.2), (0.02, 0.2)))
        self.assertEqual(spec.ic_fixed_bounds_pf, ((0.5, 3.), (0.2, 3.)))
        self.assertEqual(spec.variable_bounds_pf, (0., 3.))
        # One IC fixed C is present even when the variable C is OFF.
        var = np.zeros((6, 2))
        omega = np.array([2 * np.pi * 800e6])
        y = spec.sampled_admittance(
            omega, [0.5, 0.3, 0.1, 0.08], [0.5, 0.2], var, np.array([0])
        )
        self.assertEqual(y.shape, (1, 8))
        self.assertEqual(y[0, 4], 0)
        self.assertEqual(y[0, 5], 0)
        self.assertNotEqual(y[0, 6], 0)
        self.assertNotEqual(y[0, 7], 0)
        self.assertAlmostEqual(
            abs(y[0, 6] - omega[0]*.5e-12/(1/60-1j)), 0., places=16
        )
        self.assertTrue(spec.validate_values(
            self.policy, [.5, .3, .1, .08], [.5, .2], var
        ))

    def test_policy_allows_zero_one_or_two_composite_branches(self):
        # The authorized RF-T008 v3 branch count is an upper bound, not a
        # requirement that two DTCs must always be installed.
        for n in (0, 1, 2):
            var = ((3, -1), (0, 3))[:n]
            placement = CapacitorPlacement(
                5, fixed_edges=((0, 1), (4, -1), (1, 2)),
                variable_edges=var, ic_fixed_edges=var
            )
            layout = RFT008CapacitorLayout.for_policy(self.policy, placement)
            values = [low for low, _ in layout.ic_fixed_bounds_pf]
            self.assertTrue(layout.validate_values(
                self.policy, [.1, .5, .1], values, np.zeros((6, n))
            ))
            adm = layout.sampled_admittance(
                np.array([2*np.pi*800e6]), [.1, .5, .1], values,
                np.zeros((6, n)), [0]
            )
            self.assertEqual(adm.shape, (1, 3 + 2*n))
        with self.assertRaises(ValueError):
            var = ((3, -1), (0, 3), (1, 2))
            RFT008CapacitorLayout.for_policy(
                self.policy, CapacitorPlacement(5, (), var, var)
            )

    def test_explicit_series_role_survives_value_validation(self):
        placement = self.mixed_layout()
        layout = RFT008CapacitorLayout.for_policy(
            self.policy, placement, (0,),
            variable_roles=("series", "bridge")
        )
        self.assertEqual(layout.variable_roles, ("series", "bridge"))
        self.assertTrue(layout.validate_values(
            self.policy, [.5, .3, .1, .08], [.2, .2], np.zeros((6, 2))
        ))

    def test_formal_gjm_cap_limit_not_replaced_by_study_search_floor(self):
        placement = self.mixed_layout()
        legal = RFT008CapacitorLayout.for_policy(self.policy, placement, (0,))
        study = RFT008CapacitorLayout.for_policy(
            self.policy, placement, (0,), gjm_lower_pf=0.02
        )
        self.assertEqual(legal.fixed_bounds_pf[0], (0.0, 100.0))
        self.assertEqual(study.fixed_bounds_pf[0], (0.02, 100.0))
        c = [0.001, 0.4, 0.1, 0.1]
        fixed_ic = [0.2, 0.2]
        variable = np.zeros((6, 2))
        self.assertTrue(legal.validate_values(self.policy, c, fixed_ic, variable))
        with self.assertRaises(ValueError):
            study.validate_values(self.policy, c, fixed_ic, variable)
        c[0] = 0.
        with self.assertRaises(ValueError):
            legal.validate_values(self.policy, c, fixed_ic, variable)

    def test_invalid_composite_or_pcb_layout_rejected(self):
        p = self.policy
        with self.assertRaises(ValueError):
            RFT008CapacitorLayout.for_policy(
                p, CapacitorPlacement(5, self.mixed_layout().fixed_edges,
                                      ((0, 1), (1, 2), (3, -1)),
                                      ((0, 1), (1, 2), (3, -1))), (0,)
            )
        with self.assertRaises(ValueError):
            RFT008CapacitorLayout.for_policy(p, self.mixed_layout(), ())
        with self.assertRaises(ValueError):
            RFT008CapacitorLayout.for_policy(p, self.mixed_layout(), (0, 0))
        with self.assertRaises(ValueError):
            RFT008CapacitorLayout.for_policy(p, self.mixed_layout(), (6,))
        with self.assertRaises(ValueError):
            CapacitorPlacement(5, ((0, 1),), ((3, -1),), ((1, 2),))
        with self.assertRaises(ValueError):
            RFT008CapacitorLayout.for_policy(
                load_constraint("RF-T007", allow_trial=True),
                self.mixed_layout(), (0,)
            )
        spec = RFT008CapacitorLayout.for_policy(p, self.mixed_layout(), (0,))
        for bad_fixed in ([0.5, 0.01, 0.1, 0.1],
                          [0.5, 2., 0.1, 0.1]):
            with self.subTest(bad_fixed=bad_fixed), self.assertRaises(ValueError):
                spec.validate_values(p, bad_fixed, [0.2, 0.2], np.zeros((6, 2)))
        with self.assertRaises(ValueError):
            spec.validate_values(p, [0.5, 0.3, 0.1, 0.08],
                                 [0.2, 0.2], np.full((6, 2), 3.001))
        with self.assertRaises(ValueError):
            spec.sampled_admittance(np.array([1.0]), [0.5]*4,
                                    [0.2, 0.2], np.zeros((5, 2)), [0])

    def test_3l_custom_var_and_fixed_placement_matches_7x7_mna(self):
        row = json.loads((SNAP / "rf_t008_exp058_area3_to_3p667_20261020.json").read_text())[
            "observed_nondominated"
        ][0]
        x = np.asarray(row["vector"], float)
        layout = CapacitorPlacement(
            4,
            fixed_edges=((0, 1), (1, 2), (2, -1)),
            variable_edges=((3, -1), (0, 1)),
            ic_fixed_edges=((3, -1), (0, 1)),
        )
        baseline = exp058_area3.Evaluator(self.policy, "shunt_output", 3)
        changed = exp058_area3.Evaluator(
            self.policy, "shunt_output", 3, capacitor_placement=layout
        )
        candidate = np.clip(x, changed.bounds[:, 0], changed.bounds[:, 1])
        self.assertTrue(changed.capacitor_layout.validate_values(
            self.policy, candidate[3:6], candidate[8:10],
            candidate[10:].reshape(6, 2)
        ))
        reference = baseline.il(candidate).copy()
        test = changed.il(candidate)
        self.assertGreater(float(np.max(np.abs(test-reference))), 1e-6)
        np.testing.assert_array_equal(baseline.il(candidate), reference)
        check = exp058_area3.independent_mna(
            changed, candidate, self.policy, "shunt_output"
        )
        self.assertTrue(check["pass"], check)

    def test_4l_zero_gjm_3pcb_connection_injection(self):
        x = np.asarray(json.loads(
            (SNAP / "rf_t008_exp058_area4_20261020.json").read_text()
        )["best_cost_cell"]["vector"], float)
        layout = CapacitorPlacement(
            5,
            fixed_edges=((0, 1), (4, -1), (2, -1)),
            variable_edges=((3, -1), (0, 3)),
            ic_fixed_edges=((3, -1), (0, 3)),
        )
        baseline = exp058_area4.Evaluator(self.policy, "shunt_output", "cp", 3)
        changed = exp058_area4.Evaluator(
            self.policy, "shunt_output", "cp", 3, capacitor_placement=layout
        )
        x = np.clip(x, changed.bounds[:, 0], changed.bounds[:, 1])
        original = baseline.il(x).copy()
        other = changed.il(x)
        self.assertGreater(float(np.max(np.abs(original-other))), 1e-6)
        np.testing.assert_array_equal(baseline.il(x), original)
        mna = exp058_area4.independent_mna(
            self.policy, "shunt_output", "cp", x, capacitor_placement=layout
        )
        self.assertTrue(mna["pass"], mna)

    def test_4l_gjm_custom_ground_var_matches_independent_9x9_mna(self):
        x = np.asarray(json.loads(
            (SNAP / "rf_t008_exp058_area4p667_20261020.json").read_text()
        )["best"]["vector"], float)
        layout = self.mixed_layout(variable_edges=((4, -1), (0, 3)))
        baseline = exp058_area4l_gjm.Evaluator(
            self.policy, "input_output", ("cf0",), 3
        )
        changed = exp058_area4l_gjm.Evaluator(
            self.policy, "input_output", ("cf0",), 3,
            capacitor_placement=layout
        )
        x = np.clip(x, changed.bounds[:, 0], changed.bounds[:, 1])
        self.assertTrue(changed.capacitor_layout.validate_values(
            self.policy, x[4:8], x[11:13], x[13:].reshape(6, 2)
        ))
        original = baseline.il(x).copy()
        other = changed.il(x)
        self.assertGreater(float(np.max(np.abs(original-other))), 1e-6)
        np.testing.assert_array_equal(baseline.il(x), original)
        proof = exp058_area4l_gjm.independent_mna(
            self.policy, "input_output", ("cf0",), x,
            capacitor_placement=layout
        )
        self.assertTrue(proof["pass"], proof)


if __name__ == "__main__":
    unittest.main()
