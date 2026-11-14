"""Reuse #410 full-response/STOP fixtures for the three #413 hypotheses."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

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

    def test_schur_and_power_failure_propagate_through_plain_solver(self):
        from lpf.rf_core.model import power_response
        from lpf.rf_core.numerical_diagnostics import CircuitNumericalError
        from lpf.search._worker_next import MinimalWorker
        from lpf.search.plan import load_preflight
        from lpf.search.storage import vector_sha
        p, model, g, x = previous.fixture()
        plan = load_preflight(ROOT/'project/diagnostics/issue377/baseline.yaml')
        for variant in ('baseline', *self.variants):
            m = probe.probe_model(model, variant)
            node = np.zeros((len(g.setting), m.topology.inductor_tree.node_count,
                             m.topology.inductor_tree.node_count), complex)
            with patch.object(type(m.topology), 'node_admittance', return_value=node):
                with self.assertRaises(CircuitNumericalError) as caught:
                    m.evaluator(g).evaluate(x)
                self.assertEqual(caught.exception.code, 'schur_solve_failed')
            worker = MinimalWorker(plan, model.definition, p, 'hybrid', 1002, x, vector_sha(x), root=ROOT)
            worker.model = m
            worker.evaluator = m.evaluator(worker.grid)
            bad = np.zeros((len(g.setting), 2, 2), complex)
            bad[:, 1, 1] = 2.  # undefined available power, not a valid passive S
            with patch('lpf.rf_core.model._cascade', return_value=bad):
                with self.assertRaises(CircuitNumericalError) as caught:
                    worker.solve()
                self.assertEqual(caught.exception.code, 'available_gain_undefined')
            # Inject at the wave solve only, after the unchanged L/Schur/Y->S
            # solves; exercise the real conversion's typed failure boundary.
            for code in ('wave_singular', 'wave_nonfinite'):
                def fail_wave(*args, **kwargs):
                    options = ({'side_effect': np.linalg.LinAlgError('synthetic wave failure')}
                               if code == 'wave_singular' else
                               {'return_value': np.full((len(g.setting), 2, 2), np.nan, complex)})
                    with patch('numpy.linalg.solve', **options):
                        return power_response(*args, **kwargs)
                with patch('lpf.rf_core.model.power_response', side_effect=fail_wave):
                    with self.assertRaises(CircuitNumericalError) as caught:
                        worker.solve()
                    self.assertEqual(caught.exception.code, code)
            nonfinite = np.full_like(node, np.nan)
            with patch.object(type(m.topology), 'node_admittance', return_value=nonfinite):
                with self.assertRaises(CircuitNumericalError) as caught:
                    m.evaluator(g).evaluate(x)
                self.assertEqual(caught.exception.code, 'schur_nonfinite')
                self.assertEqual(caught.exception.sample_index, 0)

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
