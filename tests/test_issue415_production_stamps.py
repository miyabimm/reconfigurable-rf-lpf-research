"""Production stamp storage and topology-only dependencies (Issue #415)."""
from dataclasses import FrozenInstanceError, replace
import unittest

import numpy as np
from test_issue410_c_assembly import fixture
from lpf.topology_management.circuit_layout import incidence_matrix
from lpf.rf_core.numerical_diagnostics import CircuitNumericalError


class ProductionStampTests(unittest.TestCase):
    def test_branchwise_immutable_and_rebuilt_on_replace(self):
        _, model, _, _ = fixture()
        t = model.topology
        n = t.inductor_tree.node_count
        b = incidence_matrix(t.capacitor_edges, n)
        stamps = t._capacitor_stamps_flat.reshape(-1, n, n)
        for j, q in enumerate(t.capacitor_q):
            np.testing.assert_allclose(stamps[j], 1e-12 / (1/q - 1j) *
                                       np.outer(b[:, j], b[:, j]), rtol=1e-15)
        with self.assertRaises(ValueError):
            t._capacitor_stamps_flat.setflags(write=True)
        with self.assertRaises(FrozenInstanceError):
            t._capacitor_stamps_flat = stamps
        changed = replace(t, capacitor_q=tuple(q * 2 for q in t.capacitor_q))
        self.assertFalse(np.array_equal(changed._capacitor_stamps_flat, t._capacitor_stamps_flat))

    def test_nonfinite_reports_first_bad_sample(self):
        _, model, _, x = fixture()
        values = model.decode(x)
        values = replace(values, capacitors_pf_by_setting=tuple(
            tuple(1e300 for _ in row) for row in values.capacitors_pf_by_setting))
        with np.errstate(over='ignore', invalid='ignore'):
            with self.assertRaises(CircuitNumericalError) as caught:
                model.topology.node_admittance(values, [1e9, 1e30, 1e31], [0, 1, 2])
        self.assertEqual((caught.exception.code, caught.exception.sample_index), ('node_nonfinite', 1))

    def test_empty_capacitor_branches(self):
        _, model, g, x = fixture()
        t = replace(model.topology, capacitor_edges=(), capacitor_q=())
        values = replace(model.decode(x), capacitors_pf_by_setting=((),) * 6)
        self.assertEqual(t._capacitor_stamps_flat.shape, (0, t.inductor_tree.node_count ** 2))
        y = t.node_admittance(values, 2*np.pi*g.frequency_hz, g.setting)
        self.assertTrue(np.all(np.isfinite(y)))


if __name__ == '__main__':
    unittest.main()
