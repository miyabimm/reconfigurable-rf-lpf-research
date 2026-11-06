"""Layer boundaries and bounded old/new physical-check equivalence (no EXP)."""
import ast
from dataclasses import asdict, fields, replace
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np

from test_issue307_constraints import make
from lpf.topology_management import CircuitDefinition, InductorTree, CapacitorPlacement
from lpf.phase2_models import api, circuit_layout, role_audit
from lpf.phase2_models.coupled_lc import CircuitValues
from lpf.phase2_models.nominal_inductors import check_nominal_inductors
from lpf.search.component_constraints import physical_bounds, validate_values


def prior_check(d, schema, x, p):
    """Pre-#323 value-check flow, retained only as a differential test oracle."""
    if not isinstance(x, CircuitValues) and np.asarray(x).dtype.kind not in 'fiu':
        raise ValueError('numeric values required')
    values = x if isinstance(x, CircuitValues) else schema.decode(x)
    vector = schema.encode(values)
    box = np.asarray(physical_bounds(d, schema, p))
    if not np.all(np.isfinite(vector)) or np.any(vector < box[:, 0]) or np.any(vector > box[:, 1]):
        raise ValueError('bounds')
    c = api.build_nominal_circuit(p, d)
    if c.schema != schema:
        raise ValueError('schema')
    roles = c.connection_role_audit()
    if not roles['all_declared_roles_supported_by_l_tree']:
        raise ValueError('role')
    coupling = check_nominal_inductors(p, c.topology, values, d.inductor_types, d.physical_order)
    return {'component_policy_pass': True, 'constraint_id': p['active_constraint_id'],
            'constraint_fingerprint': c.policy_fingerprint, 'checked_settings': 6,
            'installed_variable_c_branches': schema.n_variable,
            'installed_shunt_parasites': len(schema.constant_caps_pf),
            'min_L_eigenvalue_H': coupling['min_inductance_eigenvalue'],
            'connection_role_audit': roles, 'connection_role_evidence_incomplete': False,
            'candidate_promotion_blocked': True,
            'promotion_blockers': ('independent_mna_not_checked', 'dense_rf_not_checked'),
            'rf_performance_checked': False, 'independent_mna_checked': False,
            'physical_q_srf_em_checked': False}


class DependenciesTests(unittest.TestCase):
    def test_topology_identity_and_fields(self):
        self.assertIs(api.CircuitDefinition, CircuitDefinition)
        self.assertIs(circuit_layout.InductorTree, InductorTree)
        self.assertIs(circuit_layout.CapacitorPlacement, CapacitorPlacement)
        from lpf.topology_management import audit_variable_connection_roles
        self.assertIs(role_audit.audit_variable_connection_roles, audit_variable_connection_roles)
        self.assertEqual([f.name for f in fields(CircuitDefinition)], [
            'inductor_tree', 'inductor_types', 'physical_order', 'coupling_pairs',
            'capacitor_placement', 'fixed_c_types', 'variable_roles'])
        _, d, _, _, _ = make('RF-T008')
        self.assertEqual(asdict(d)['inductor_tree']['edges'], d.inductor_tree.edges)
        self.assertTrue(CircuitDefinition.__module__.startswith('lpf.topology_management'))

    def test_values_match_prior_without_legacy_builder_or_forward(self):
        for cid in ('RF-F003', 'RF-T005', 'RF-T006', 'RF-T007', 'RF-T008'):
            p, d, c, bounds, x = make(cid)
            cases = [x, x[:-1], np.full_like(x, np.nan), [True]*len(x)]
            for i, (lo, hi) in enumerate(bounds):
                for value in (lo, hi, np.nextafter(lo, -np.inf), np.nextafter(hi, np.inf)):
                    v = x.copy(); v[i] = value; cases.append(v)
            values = c.decode(x)
            rows = [list(row) for row in values.capacitors_pf_by_setting]
            rows[-1][0] += .1
            cases.append(replace(values, capacitors_pf_by_setting=tuple(map(tuple, rows))))
            for v in cases:
                with self.subTest(cid=cid):
                    try:
                        expected = prior_check(d, c.schema, v, p)
                    except ValueError:
                        with self.assertRaises(ValueError): validate_values(d, c.schema, v, p)
                    else:
                        with (patch('lpf.phase2_models.api.build_nominal_circuit', side_effect=AssertionError('legacy')),
                              patch('lpf.rf_core.model.RFEvaluator.evaluate', side_effect=AssertionError('forward'))):
                            self.assertEqual(validate_values(d, c.schema, v, p), expected)
            invalid = replace(d, variable_roles=('series', 'bridge'))
            for check in (prior_check, validate_values):
                with self.assertRaises(ValueError): check(invalid, c.schema, x, p)
            bad_policy = dict(p, active_constraint_id='RF-T999')
            for check in (prior_check, validate_values):
                with self.assertRaises(ValueError): check(d, c.schema, x, bad_policy)
