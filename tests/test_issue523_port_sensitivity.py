"""Direct port projection against the independently assembled nodal Jacobian."""
import unittest
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
        np.testing.assert_allclose(actual, expected, rtol=2e-12, atol=1e-13)


if __name__ == '__main__':
    unittest.main()
