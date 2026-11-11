"""JSON-owned closed physical bounds and complete six-setting validation.

Units follow ParameterVectorSchema: nH, pF, dimensionless signed k. A box
endpoint is not a guarantee of joint SPD or legal connectivity. No repair.
"""
import numpy as np


from lpf.policy_schema import interval


def physical_bounds(definition, schema, policy):
    """Return exactly one closed interval per complete vector coordinate."""
    d, s, p = definition, schema, policy
    from lpf.rf_core.nominal_inductors import nominal_inductor_series
    bounds = [nominal_inductor_series(p, kind)[1:] for kind in d.inductor_types]
    for kind, edge in zip(d.fixed_c_types, d.capacitor_placement.fixed_edges):
        if kind not in ('GJM01', 'PCB_PATTERN_C'):
            raise ValueError('Unsupported fixed capacitor type')
        spec = p['components'][kind]
        if kind == 'PCB_PATTERN_C' and 'trial_pcb_pattern_c_by_connection' in p:
            spec = p['trial_pcb_pattern_c_by_connection']['grounded' if -1 in edge else 'non_ground']
        bounds.append(interval(spec, 'pF'))
    adjacent = {frozenset(pair) for pair in zip(d.physical_order, d.physical_order[1:])}
    for a, b in d.coupling_pairs:
        if (type(a) is not int or type(b) is not int or a == b or
                min(a, b) < 0 or max(a, b) >= len(d.inductor_types)):
            raise ValueError('Invalid coupling slot')
        ta, tb = d.inductor_types[a], d.inductor_types[b]
        key = ('pcb_pcb' if ta == tb == 'PCB_L' else 'chip_pcb' if 'PCB_L' in (ta, tb)
               else 'chip_neighbor' if frozenset((a, b)) in adjacent else 'chip_nonstrong_nominal')
        bounds.append(interval({'bounds': p['coupling_limits']['bounds'][key]}, '1'))
    for edge in d.capacitor_placement.ic_fixed_edges:
        spec = p.get('trial_ic_fixed_c_by_connection')
        if spec is None:
            raise ValueError('IC fixed C requires explicit physical model')
        bounds.append(interval(spec['grounded' if -1 in edge else 'non_ground'], 'pF'))
    bounds.extend([interval(p['components']['IC_VARIABLE_C'], 'pF')] * (6 * s.n_variable))
    dims = (len(d.inductor_types), len(d.fixed_c_types), len(d.coupling_pairs),
            len(d.capacitor_placement.ic_fixed_edges), len(d.capacitor_placement.variable_edges))
    if dims != (s.n_inductors, s.n_fixed, s.n_coupling, s.n_ic_fixed, s.n_variable) or len(bounds) != s.vector_length:
        raise ValueError('Definition/schema/physical bounds disagree')
    return tuple(bounds)


def validate_values(definition, schema, x, policy, *, frozen_model=None):
    """Check complete values, structural/Q/layout model, all-L SPD; not RF PASS."""
    return _validate_values_with_bounds(definition, schema, x, policy,
                                        physical_bounds(definition, schema, policy),
                                        frozen_model=frozen_model)


def _validate_values_with_bounds(definition, schema, x, policy, box, *, frozen_model=None):
    """Internal boundary check with bounds just constructed from this policy."""
    from lpf.rf_core import build_rf_model
    from lpf.topology_management import audit_variable_connection_roles
    from lpf.rf_core.coupled_lc import CircuitValues
    from lpf.rf_core.nominal_inductors import check_nominal_inductors
    if not isinstance(x, CircuitValues) and np.asarray(x).dtype.kind not in 'fiu':
        raise ValueError('Expected numeric component values, not boolean/string coercion')
    values = x if isinstance(x, CircuitValues) else schema.decode(x)
    vector = schema.encode(values)  # fixed/IC/constant invariance and six settings
    box = np.asarray(box)
    if not np.all(np.isfinite(vector)) or np.any(vector < box[:, 0]) or np.any(vector > box[:, 1]):
        raise ValueError('Component value outside closed physical bounds')
    # Frozen common model owns counts/Q/layout/constants and policy approval.
    # Construction only: no evaluator or RF forward is invoked.
    if frozen_model is None:
        circuit = build_rf_model(definition, policy)
    else:
        # Explicit opt-in: the model was approved and frozen at the boundary.
        # Candidate box, role, coupling and complete SPD checks still run below.
        from lpf.rf_core.model import RFModel
        from lpf.constraint_versions import constraint_fingerprint
        circuit = frozen_model
        if (not isinstance(circuit, RFModel) or circuit.definition != definition or
                circuit.policy_fingerprint != constraint_fingerprint(policy)):
            raise ValueError('Frozen model/definition/policy mismatch')
    if circuit.schema != schema:
        raise ValueError('Schema does not match physical model (including constants)')
    roles = audit_variable_connection_roles(
        definition.inductor_tree, definition.capacitor_placement.variable_edges,
        definition.variable_roles).as_dict()
    if not roles['all_declared_roles_supported_by_l_tree']:
        raise ValueError('Connection role not proven by L tree')
    coupling = check_nominal_inductors(policy, circuit.topology, values,
                                     definition.inductor_types, definition.physical_order)
    return {'component_policy_pass': True, 'constraint_id': policy['active_constraint_id'],
            'constraint_fingerprint': circuit.policy_fingerprint,
            'checked_settings': 6, 'installed_variable_c_branches': schema.n_variable,
            'installed_shunt_parasites': len(schema.constant_caps_pf),
            'min_L_eigenvalue_H': coupling['min_inductance_eigenvalue'],
            'connection_role_audit': roles, 'connection_role_evidence_incomplete': False,
            'candidate_promotion_blocked': True,
            'promotion_blockers': ('independent_mna_not_checked', 'dense_rf_not_checked'),
            'rf_performance_checked': False, 'independent_mna_checked': False,
            'physical_q_srf_em_checked': False}


def _check_vector_box(vector, bounds):
    """Check an external flat vector against a previously frozen physical box."""
    x, box = np.asarray(vector), np.asarray(bounds)
    if (x.dtype.kind not in 'fiu' or x.shape != (len(box),) or
            not np.all(np.isfinite(x)) or np.any(x < box[:, 0]) or np.any(x > box[:, 1])):
        raise ValueError('Expected finite numeric vector within closed physical bounds')
    return x


def validate_search_box(bounds, physical):
    box, hard = np.asarray(bounds, float), np.asarray(physical, float)
    if (box.shape != hard.shape or not np.all(np.isfinite(box)) or
            np.any(box[:, 0] < hard[:, 0]) or np.any(box[:, 1] > hard[:, 1]) or
            np.any(box[:, 0] > box[:, 1])):
        raise ValueError('Search box must be a closed physical sub-box')
    return box
