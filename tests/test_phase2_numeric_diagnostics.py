"""Synthetic typed numeric failure and arbitrary-graph regressions."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import numpy as np
from lpf.rf_core import EvaluationGrid
from lpf.rf_core.coupled_lc import CircuitValues, CoupledLCTopology, ParameterVectorSchema
from lpf.rf_core.numerical_diagnostics import CircuitNumericalError
from lpf.topology_management import InductorTree, CapacitorPlacement
from test_issue323_dependencies import make


class Stage1NumericalFailureTests(unittest.TestCase):
    def test_mutual_spd_failure_has_stable_error_code(self):
        t = CoupledLCTopology(InductorTree(4, ((0, 1), (1, 2), (1, 3))),
                              ((0, 1), (0, 2), (1, 2)), (25.,)*3, ((0, 1),), (40.,))
        bad = CircuitValues((1., 1., 1.), (-.9, -.9, -.9), ((.1,),)*6)
        with self.assertRaises(CircuitNumericalError) as caught:
            t.matrices(bad)
        self.assertEqual(caught.exception.code, 'mutual_not_spd')
        self.assertIsNone(caught.exception.sample_index)

    def test_bad_frequency_setting_and_schema(self):
        _, _, model, _, x = make('RF-T007')
        val, t = model.decode(x), model.topology
        for omega, settings in (([0.], [0]), ([float('nan')], [0]), ([1.], [6]),
                                ([1.], [-1]), ([1.], [.5]), ([1.], [True]), ([1., 2.], [0])):
            with self.subTest(omega=omega, settings=settings), self.assertRaises(ValueError):
                t.node_admittance(val, omega, settings)
        ev = model.evaluator(EvaluationGrid([1e9], [0], [0]))
        for bad in (x[:-1], np.full_like(x, np.nan), np.full_like(x, np.inf)):
            with self.assertRaises(ValueError):
                ev.evaluate(bad)

    def test_graph_dimensions_and_synthetic_five_inductors(self):
        tree = InductorTree(6, ((0, 1), (1, 3), (3, 4), (4, 5), (5, 2)), 0, 2)
        self.assertEqual(tree.incidence().shape, (6, 5))
        topo = CoupledLCTopology(tree, (), (25.,)*5, ((0, -1), (5, -1), (2, -1)), (60.,)*3)
        schema = ParameterVectorSchema(5, 3, 0, 0, 0)
        x = np.array([2., 3., 4., 5., 6., .1, .1, .1])
        val = schema.decode(x)
        y = topo.node_admittance(val, np.array([2*np.pi*1e9]), np.array([0]))
        self.assertEqual(y.shape, (1, 6, 6))
        self.assertTrue(np.all(np.isfinite(y)))
        for kwargs in ({'source_node': 2, 'load_node': 2}, {'source_node': -1, 'load_node': 2},
                       {'source_node': 0, 'load_node': 6}):
            with self.assertRaises(ValueError):
                InductorTree(6, tree.edges, **kwargs)
        with self.assertRaises(ValueError):
            CapacitorPlacement(6, (), ((3, -1),), ((4, -1),))
