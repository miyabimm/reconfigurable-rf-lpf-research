"""Direct port projection against the independently assembled nodal Jacobian."""
import unittest
from dataclasses import replace
import numpy as np

from test_issue307_constraints import make


class PortSensitivityTests(unittest.TestCase):
    def test_direct_projection_matches_nodal_with_arbitrary_lift(self):
        _, _, model, _, x = make('RF-T008')
        top, schema = model.topology, model.schema
        x[10], x[13] = .03, -.04
        values = model.decode(x)
        omega = 2*np.pi*np.array([1e9, 2e9, 1.3e9, 3e9])
        setting = np.array([5, 0, 5, 2])
        rng = np.random.default_rng(523)
        T = rng.normal(size=(len(omega), top.inductor_tree.node_count, 2)) + 1j*rng.normal(size=(len(omega), top.inductor_tree.node_count, 2))
        matrices = top.matrices(values)
        _, dy = top.node_admittance_with_jacobian(values, schema, omega, setting, matrices=matrices)
        expected = T.swapaxes(-1, -2)[:, None] @ dy @ T[:, None]
        actual = top.port_admittance_jacobian(values, schema, omega, setting, T, matrices=matrices)
        shared = schema.vector_length - 6 * schema.n_variable
        cols = shared + setting[:, None]*schema.n_variable + np.arange(schema.n_variable)
        compact = np.concatenate((expected[:, :shared], expected[np.arange(len(omega))[:, None], cols]), axis=1)
        np.testing.assert_allclose(actual, compact, rtol=2e-12, atol=1e-13)

    def test_no_variable_branches_and_reversed_ports(self):
        from lpf.rf_core import build_rf_model
        from test_issue309_rf_core import grid
        policy, definition, _, _, _ = make('RF-T008')
        placement = replace(definition.capacitor_placement, variable_edges=(), ic_fixed_edges=())
        model = build_rf_model(replace(definition, capacitor_placement=placement, variable_roles=()), policy)
        tree = model.topology.inductor_tree
        reversed_tree = replace(tree, source_node=tree.load_node, load_node=tree.source_node)
        model = replace(model, topology=replace(model.topology, inductor_tree=reversed_tree))
        x = np.array([3.]*7 + [.1, .1, .1] + [0.]*4)
        ev = model.evaluator(grid(model.resolved_policy))
        response, jac = ev.evaluate_with_il_jacobian(x)
        np.testing.assert_allclose(response.s, ev.evaluate(x).s, rtol=1e-12, atol=1e-12)
        self.assertEqual(model.schema.n_variable, 0)
        for j in range(len(x)):
            h = 1e-5
            plus, minus = x.copy(), x.copy()
            plus[j] += h; minus[j] -= h
            fd = (ev.evaluate(plus).il_db-ev.evaluate(minus).il_db)/(2*h)
            np.testing.assert_allclose(jac[:, j], fd, rtol=1e-4, atol=1e-5)


if __name__ == '__main__':
    unittest.main()
