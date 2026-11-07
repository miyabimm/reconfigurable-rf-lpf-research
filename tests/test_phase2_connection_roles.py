"""Role evidence is separate from component policy and physical proof."""
import unittest
from dataclasses import replace
from test_issue323_dependencies import make
from lpf.rf_core import build_rf_model
from lpf.search.component_constraints import validate_values
from lpf.topology_management import InductorTree, audit_variable_connection_roles


class ConnectionRoleAuditTests(unittest.TestCase):
    def test_tree_proves_ground_and_chord_not_series(self):
        tree = InductorTree(5, ((0, 1), (1, 3), (1, 4), (1, 2)))
        edges = ((3, -1), (0, 3), (1, 2))
        audit = audit_variable_connection_roles(tree, edges, ('shunt_to_ground', 'bridge', 'series'))
        self.assertEqual(audit.unsupported_role_indices, (2,))
        self.assertEqual(audit.branches[0].evidence, 'verified_ground_endpoint')
        self.assertEqual(audit.branches[1].evidence, 'verified_L_path_between_terminals')
        self.assertEqual(audit.branches[2].evidence, 'series_path_not_provable_from_spanning_L_tree')
        self.assertFalse(audit.as_dict()['physical_layout_checked'])
        self.assertFalse(audit.all_declared_roles_supported_by_l_tree)
        for roles in (('bridge', 'bridge', 'bridge'), ('shunt_to_ground', 'shunt_to_ground', 'bridge'), ('shunt_to_ground',)):
            with self.subTest(roles=roles), self.assertRaises(ValueError):
                audit_variable_connection_roles(tree, edges, roles)
        self.assertTrue(audit_variable_connection_roles(tree, (), ()).all_declared_roles_supported_by_l_tree)
        with self.assertRaises(TypeError):
            audit_variable_connection_roles(None, (), ())

    def test_current_policy_rejects_unproved_series_and_does_not_claim_rf(self):
        policy, definition, model, _, x = make('RF-T007')
        result = validate_values(definition, model.schema, x, policy)
        self.assertTrue(result['component_policy_pass'])
        self.assertFalse(result['rf_performance_checked'])
        with self.assertRaisesRegex(ValueError, 'role not proven'):
            build_rf_model(replace(definition, variable_roles=('shunt_to_ground', 'series')), policy)
