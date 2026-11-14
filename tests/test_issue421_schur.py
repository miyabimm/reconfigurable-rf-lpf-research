"""Schur port ordering, complex symmetry and numerical STOP boundaries."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts'), str(ROOT / 'tests'), str(ROOT / 'project/diagnostics')]
from issue421_benchmark import old_port
from lpf.rf_core.coupled_lc import CircuitValues, CoupledLCTopology
from lpf.rf_core.numerical_diagnostics import CircuitNumericalError
from lpf.topology_management import InductorTree


class SchurTests(unittest.TestCase):
    def topology(self, n, source, load):
        return CoupledLCTopology(InductorTree(n, tuple((i, i+1) for i in range(n-1)), source, load),
                                 (), (25.,)*(n-1), (), ())

    def test_reversed_nonadjacent_and_no_middle(self):
        rng = np.random.default_rng(421)
        for n, source, load in ((5, 4, 1), (5, 1, 4), (2, 1, 0)):
            t = self.topology(n, source, load)
            z = rng.normal(size=(3,n,n)) + 1j*rng.normal(size=(3,n,n))
            y = z + z.transpose(0,2,1) + 10*np.eye(n)
            before = y.copy()
            p = [source, load]
            m = [i for i in range(n) if i not in p]
            self.assertFalse(np.allclose(y, y.conj().transpose(0,2,1)))
            r = y[:, p, :][:, :, p]
            if m:
                u, v, e = y[:, p, :][:, :, m], y[:, m, :][:, :, p], y[:, m, :][:, :, m]
                self.assertFalse(np.allclose(e, e.conj().transpose(0,2,1)))
                r = r - u @ np.linalg.solve(e, v)
            with patch.object(CoupledLCTopology, 'node_admittance', return_value=y):
                actual = t.port_admittance(None, None, None)
            np.testing.assert_array_equal(actual, r)
            np.testing.assert_array_equal(y, before)

    def test_singular_and_nonfinite_stop(self):
        t = self.topology(4, 3, 0)
        y = np.broadcast_to(np.eye(4, dtype=complex), (3,4,4)).copy()
        y[1,1:3,1:3] = 0
        for method in (old_port, CoupledLCTopology.port_admittance):
            with patch.object(CoupledLCTopology, 'node_admittance', return_value=y):
                with self.assertRaises(CircuitNumericalError) as caught:
                    method(t, None, None, None)
            self.assertEqual((caught.exception.code, caught.exception.sample_index), ('schur_solve_failed', None))
        y[1,1:3,1:3] = np.eye(2)
        y[1,3,3] = np.nan
        for method in (old_port, CoupledLCTopology.port_admittance):
            with patch.object(CoupledLCTopology, 'node_admittance', return_value=y):
                with self.assertRaises(CircuitNumericalError) as caught:
                    method(t, None, None, None)
            self.assertEqual((caught.exception.code, caught.exception.sample_index), ('schur_nonfinite', 1))

    def test_real_tree_ground_parallel_different_q_zero_c(self):
        t = CoupledLCTopology(InductorTree(4, ((0,1),(1,2),(1,3)), 3, 0), (),
                              (25.,)*3, ((1,-1),(1,-1),(2,3)), (35.,60.,40.))
        values = CircuitValues((2.,3.,4.), (), ((0.,.5,.2),)*6)
        omega = 2*np.pi*np.array([.7e9, 1.4e9, 2.1e9])
        settings = np.array([0, 1, 5])
        y = t.node_admittance(values, omega, settings)
        p, m = (3, 0), (1, 2)
        expected = y[:,p,:][:,:,p] - y[:,p,:][:,:,m] @ np.linalg.solve(y[:,m,:][:,:,m], y[:,m,:][:,:,p])
        np.testing.assert_array_equal(t.port_admittance(values, omega, settings), expected)


if __name__ == '__main__':
    unittest.main()
