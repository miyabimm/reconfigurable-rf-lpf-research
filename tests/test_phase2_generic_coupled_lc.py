"""Generic forward/schema safety contracts, independent of legacy evaluators."""
import unittest

import numpy as np

from test_issue323_dependencies import make
from lpf.rf_core import EvaluationGrid
from lpf.topology_management.circuit_layout import InductorTree
from lpf.rf_core.coupled_lc import CircuitValues, CoupledLCTopology, ParameterVectorSchema


class GenericCircuitEvaluationTests(unittest.TestCase):
    def test_typed_forward_rejects_setting_dependent_fixed_or_ic_values(self):
        grid = EvaluationGrid(np.array([810e6]), np.array([0]), np.array([0]))
        _, _, model, _, x = make('RF-T008')
        forward = model.evaluator(grid)
        original = model.schema.decode(x)
        np.testing.assert_allclose(forward.evaluate(original).il_db, forward.evaluate(x).il_db, atol=1e-12, rtol=0)
        for index in (0, model.schema.n_fixed + model.schema.n_variable):
            rows = list(original.capacitors_pf_by_setting)
            row = list(rows[3])
            row[index] += .01
            rows[3] = tuple(row)
            typed = CircuitValues(original.inductances_nh, original.coupling_k, tuple(rows))
            with self.subTest(capacitor_index=index):
                with self.assertRaisesRegex(ValueError, 'differ by setting'):
                    forward.evaluate(typed)
        _, _, model, _, x = make('RF-T007')
        forward = model.evaluator(grid)
        typed = model.schema.decode(x)
        rows = list(typed.capacitors_pf_by_setting)
        rows[4] = rows[4][:-1] + (.51,)
        with self.assertRaisesRegex(ValueError, 'differ by setting'):
            forward.evaluate(CircuitValues(typed.inductances_nh, typed.coupling_k, tuple(rows)))

    def test_schema_finite_shape_fixed_state_and_spd_guards(self):
        schema = ParameterVectorSchema(3, 1, 2, 1, 2, (0.5,))
        self.assertEqual(schema.vector_length, 3 + 1 + 2 + 1 + 12)
        with self.assertRaises(ValueError):
            schema.decode(np.zeros(schema.vector_length - 1))
        with self.assertRaises(ValueError):
            schema.decode(np.full(schema.vector_length, np.nan))
        x = np.r_[np.ones(3), .1, 0., 0., .5, np.zeros(12)]
        self.assertEqual(schema.encode(schema.decode(x)).tolist(), x.tolist())
        val = schema.decode(x)
        rows = list(val.capacitors_pf_by_setting)
        rows[1] = (0.2,) + rows[1][1:]
        with self.assertRaises(ValueError):
            schema.encode(CircuitValues(val.inductances_nh, val.coupling_k, tuple(rows)))
        with self.assertRaises(ValueError):
            CircuitValues((0., 1.), (0.1,), ((0.1,),) * 6)
        t = CoupledLCTopology(
            InductorTree(4, ((0, 1), (1, 2), (1, 3))),
            ((0, 1), (0, 2), (1, 2)), (25.,) * 3, ((0, 1),), (40.,))
        bad = CircuitValues((1., 1., 1.), (-0.9, -0.9, -0.9), ((0.1,),) * 6)
        with self.assertRaises(ValueError):
            t.matrices(bad)
        with self.assertRaises(ValueError):
            CoupledLCTopology(
                InductorTree(4, ((0, 1), (1, 2), (1, 3))),
                ((0, 1), (1, 0)), (25.,) * 3, ((0, 1),), (40.,))
        with self.assertRaises(ValueError):
            t.node_admittance(val, np.array([-1.]), np.array([0]))


if __name__ == '__main__':
    unittest.main()
