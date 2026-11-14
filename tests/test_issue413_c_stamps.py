"""Reuse #410 full-response/STOP fixtures for the three #413 hypotheses."""
import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np
import test_issue410_c_assembly as previous

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('issue413_probe', ROOT/'project/diagnostics/issue413_probe.py')
probe = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)


class PrecomputedStampTests(previous.CAssemblyTests):
    probe = probe
    variants = probe.VARIANTS

    def test_stamps_are_branchwise_q_weighted_and_immutable(self):
        _, model, _, _ = previous.fixture()
        from lpf.topology_management.circuit_layout import incidence_matrix
        b = incidence_matrix(model.topology.capacitor_edges, model.topology.inductor_tree.node_count)
        for variant in self.variants:
            t = probe.probe_model(model, variant).topology
            for j, q in enumerate(t.capacitor_q):
                np.testing.assert_allclose(t.stamps[j], 1e-12/(1/q-1j)*np.outer(b[:, j], b[:, j]), rtol=1e-15)
            with self.assertRaises(ValueError):
                t.flat.setflags(write=True)
            self.assertTrue(any(a == c and q != r for i, (a, q) in enumerate(zip(t.capacitor_edges, t.capacitor_q))
                                for c, r in zip(t.capacitor_edges[i+1:], t.capacitor_q[i+1:])))


if __name__ == '__main__':
    unittest.main()
