"""Direct RF Core SPD threshold regression retained from Issue #394."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from lpf.rf_core.coupled_lc import CircuitValues, CoupledLCTopology
from lpf.rf_core.numerical_diagnostics import CircuitNumericalError
from lpf.topology_management import InductorTree


class PhysicalPathTests(unittest.TestCase):
    def test_direct_core_spd_threshold_without_search(self):
        topology = CoupledLCTopology(InductorTree(3, ((0, 1), (1, 2))),
                                     ((0, 1),), (30., 30.), (), ())
        def values(k):
            return CircuitValues((1., 1.), (k,), ((),)*6)
        topology.matrices(values(1. - 3e-12))
        for k in (1. - 1e-12, 1., 1.01):
            with self.subTest(k=k), self.assertRaises(CircuitNumericalError) as raised:
                topology.matrices(values(k))
            self.assertEqual(raised.exception.code, 'mutual_not_spd')


if __name__ == '__main__':
    unittest.main()
