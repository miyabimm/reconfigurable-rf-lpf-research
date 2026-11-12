"""Frozen incidence stamping matches fresh orientation-preserving incidence."""
import unittest
from unittest.mock import patch

import numpy as np
from test_issue307_constraints import make
from lpf.topology_management.circuit_layout import incidence_matrix


class CapacitorIncidenceTests(unittest.TestCase):
    def test_cached_stamp_all_models_settings_and_immutable(self):
        for cid in ('RF-F003', 'RF-T005', 'RF-T006', 'RF-T007', 'RF-T008'):
            with self.subTest(cid=cid):
                _, _, model, _, vector = make(cid)
                topology = model.topology
                values = model.decode(vector)
                freq = np.linspace(1e9, 2e9, 6)
                omega = 2 * np.pi * freq
                setting = np.arange(6)
                fresh = incidence_matrix(topology.capacitor_edges, topology.inductor_tree.node_count)
                np.testing.assert_array_equal(topology._capacitor_incidence, fresh)
                with self.assertRaises(ValueError):
                    topology._capacitor_incidence.setflags(write=True)
                K, _ = topology.matrices(values)
                expected = np.broadcast_to(K, (6, topology.inductor_tree.node_count,
                                                topology.inductor_tree.node_count)).copy() / (omega[:, None, None] * 1e-9)
                C = np.asarray(values.capacitors_pf_by_setting)[setting]
                yc = omega[:, None] * 1e-12 * C / (1 / np.asarray(topology.capacitor_q)[None, :] - 1j)
                expected += np.einsum('fb,ib,jb->fij', yc, fresh, fresh, optimize=True)
                with patch('lpf.rf_core.coupled_lc.incidence_matrix', side_effect=AssertionError('rebuilt C incidence')):
                    actual = topology.node_admittance(values, omega, setting)
                np.testing.assert_array_equal(actual, expected)


if __name__ == '__main__':
    unittest.main()
