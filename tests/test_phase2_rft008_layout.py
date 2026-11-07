"""Current T008 capacitor-layout bounds, Q and fixed/variable branches."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import numpy as np
from lpf.constraint_versions import load_constraint
from lpf.topology_management import CapacitorPlacement
from lpf.rf_core.rft008_layout import RFT008CapacitorLayout


class RFT008CapacitorLayoutTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_constraint('RF-T008', allow_trial=True)

    def test_policy_bounds_q_and_separate_fixed_admittance(self):
        var = ((4, -1), (1, 2))
        placement = CapacitorPlacement(5, ((0, 1), (4, -1), (1, 2), (0, 3)), var, var)
        spec = RFT008CapacitorLayout.for_policy(self.policy, placement, (0,), gjm_lower_pf=.1)
        self.assertEqual(spec.q, (80., 60., 40., 40., 35., 35., 60., 60.))
        self.assertEqual(spec.fixed_bounds_pf, ((.1, 100.), (.02, 1.), (.02, .2), (.02, .2)))
        self.assertEqual(spec.ic_fixed_bounds_pf, ((.5, 3.), (.2, 3.)))
        omega = np.array([2*np.pi*800e6])
        y = spec.sampled_admittance(omega, [.5, .3, .1, .08], [.5, .2], np.zeros((6, 2)), [0])
        self.assertEqual(y.shape, (1, 8))
        self.assertEqual(y[0, 4], 0); self.assertEqual(y[0, 5], 0)
        self.assertAlmostEqual(abs(y[0, 6] - omega[0]*.5e-12/(1/60-1j)), 0., places=16)
        self.assertTrue(spec.validate_values(self.policy, [.5, .3, .1, .08], [.5, .2], np.zeros((6, 2))))
        for fixed in ([.5, .01, .1, .1], [.5, 2., .1, .1], [0., .3, .1, .08]):
            with self.assertRaises(ValueError):
                spec.validate_values(self.policy, fixed, [.5, .2], np.zeros((6, 2)))
        with self.assertRaises(ValueError):
            spec.validate_values(self.policy, [.5, .3, .1, .08], [.5, .2], np.full((6, 2), 3.001))
        with self.assertRaises(ValueError):
            spec.sampled_admittance(omega, [.5]*4, [.5, .2], np.zeros((5, 2)), [0])
        study = RFT008CapacitorLayout.for_policy(self.policy, placement, (0,), gjm_lower_pf=.2)
        self.assertEqual(study.fixed_bounds_pf[0], (.2, 100.))
        with self.assertRaises(ValueError):
            study.validate_values(self.policy, [.1, .3, .1, .08], [.5, .2], np.zeros((6, 2)))
        with self.assertRaises(ValueError):
            RFT008CapacitorLayout.for_policy(self.policy, placement, (0,), gjm_lower_pf=.02)
        for bad in ((), (0, 0), (6,)):
            with self.assertRaises(ValueError):
                RFT008CapacitorLayout.for_policy(self.policy, placement, bad)
        with self.assertRaises(ValueError):
            RFT008CapacitorLayout.for_policy(load_constraint('RF-T007', allow_trial=True), placement, (0,))

    def test_zero_one_two_composites_and_series_role(self):
        for n in (0, 1, 2):
            var = ((3, -1), (0, 3))[:n]
            placement = CapacitorPlacement(5, ((0, 1), (4, -1), (1, 2)), var, var)
            spec = RFT008CapacitorLayout.for_policy(self.policy, placement)
            values = [lo for lo, _ in spec.ic_fixed_bounds_pf]
            self.assertTrue(spec.validate_values(self.policy, [.1, .5, .1], values, np.zeros((6, n))))
            self.assertEqual(spec.sampled_admittance(np.array([2*np.pi*800e6]), [.1, .5, .1],
                                                    values, np.zeros((6, n)), [0]).shape, (1, 3+2*n))
        var = ((0, 3), (1, 2))
        placement = CapacitorPlacement(5, ((0, 1), (4, -1), (1, 2), (0, 3)), var, var)
        spec = RFT008CapacitorLayout.for_policy(self.policy, placement, (0,), variable_roles=('series', 'bridge'))
        self.assertEqual(spec.variable_roles, ('series', 'bridge'))
        self.assertTrue(spec.validate_values(self.policy, [.5, .3, .1, .08], [.2, .2], np.zeros((6, 2))))
        var = ((3, -1), (0, 3), (1, 2))
        with self.assertRaises(ValueError):
            RFT008CapacitorLayout.for_policy(self.policy, CapacitorPlacement(5, (), var, var))
