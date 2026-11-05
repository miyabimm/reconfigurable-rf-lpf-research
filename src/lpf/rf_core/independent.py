"""Limited independent branch-current MNA audit; no forward Schur/S cascade.

Two external Thevenin boundary conditions recover power waves. Available
power is also computed from output Thevenin voltage/impedance, not GT.
No call constitutes continuous-band or physical/EM certification.
"""
import numpy as np
from lpf.port_parasitics import get_two_port_s
from lpf.phase2_models.independent_rf import _s_admittance, evaluate_independent_sample
from lpf.phase2_models.branch_mna import solve_branch_mna
from lpf.phase2_models.coupled_lc import _fixed_port_impedance


def evaluate_independent_response(model, x, frequency_hz, setting):
    p = model.resolved_policy
    z = np.array([_fixed_port_impedance(p, 'source_ohms'),
                  _fixed_port_impedance(p, 'load_ohms')])
    pre = _s_admittance(get_two_port_s(p, 'input_parasitic', frequency_hz))
    post = _s_admittance(get_two_port_s(p, 'output_parasitic', frequency_hz))
    tree = model.topology.inductor_tree
    src, load, n = tree.source_node, tree.load_node, tree.node_count
    ds, dl = pre[0, 0]+1/z[0], post[1, 1]+1/z[1]
    term = np.zeros(n, complex)
    term[src] += pre[1, 1]-pre[1, 0]*pre[0, 1]/ds
    term[load] += post[0, 0]-post[0, 1]*post[1, 0]/dl
    waves, voltages, currents = [], [], []
    values = x if hasattr(x, 'inductances_nh') else model.decode(x)
    for drive in (np.array([1., 0.]), np.array([0., 1.])):
        injected = np.zeros(n, complex)
        injected[src] += -pre[1, 0]*drive[0]/(z[0]*ds)
        injected[load] += -post[0, 1]*drive[1]/(z[1]*dl)
        v, _ = solve_branch_mna(model, values, frequency_hz, setting,
            injected_currents_a=injected, termination_admittances_s=term)
        ext = np.array([(drive[0]/z[0]-pre[0, 1]*v[src])/ds,
                        (drive[1]/z[1]-post[1, 0]*v[load])/dl])
        current = (drive-ext)/z
        a = (ext+z*current)/(2*np.sqrt(z.real))
        b = (ext-z.conj()*current)/(2*np.sqrt(z.real))
        waves.append(b/a[np.argmax(drive)])
        voltages.append(ext)
        currents.append(current)
    s = np.column_stack(waves)
    zout = voltages[1][1]/currents[1][1]
    voc = voltages[0][1]*(1+zout/z[1])
    ga = abs(voc)**2*z[0].real/zout.real
    audit = evaluate_independent_sample(model, x, frequency_hz, setting)
    with np.errstate(divide='ignore'):
        audit.update(s=s, apl_db=float(-10*np.log10(ga)),
            in_rl_db=float(-20*np.log10(abs(s[0, 0]))),
            out_rl_db=float(-20*np.log10(abs(s[1, 1]))))
    numbers = [audit[k] for k in ('il_db', 'apl_db', 'in_rl_db', 'out_rl_db')]
    if not np.all(np.isfinite(s)) or any(np.isnan(numbers)) or not np.isfinite(ga) or ga <= 0:
        raise ValueError('Invalid independent power response')
    if np.linalg.eigvalsh(np.eye(2)-s.conj().T@s)[0] < -1e-10:
        raise ValueError('Non-passive external two-port')
    for key in ('inductor_loss_w', 'capacitor_loss_w', 'input_s2p_loss_w', 'output_s2p_loss_w'):
        if not np.isfinite(audit[key]) or audit[key] < -1e-12:
            raise ValueError('Non-passive/non-finite branch power')
    if not np.isfinite(audit['power_residual_w']) or abs(audit['power_residual_w']) > 1e-12:
        raise ValueError('Power balance failed')
    audit['independent_mna_checked'] = True
    return audit


def validate_response(model, x, response, *, atol=1e-9):
    """Recompute every requested sample. Raises on mismatch; no RF thresholds."""
    from lpf.phase2_models.role_audit import audit_variable_connection_roles
    if not np.isfinite(atol) or atol <= 0:
        raise ValueError('Expected finite positive audit tolerance')
    count = len(response.grid.frequency_hz)
    for key in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
        a = np.asarray(getattr(response, key))
        expected_shape = (count, 2, 2) if key == 's' else (count,)
        expected_dtype = np.complex128 if key == 's' else np.float64
        if a.shape != expected_shape or a.dtype != expected_dtype or np.any(np.isnan(a)):
            raise ValueError('Invalid response shape/dtype/NaN')
    if response.policy_id != model.policy_id or response.policy_fingerprint != model.policy_fingerprint:
        raise ValueError('Policy identity mismatch')
    d = model.definition
    if not audit_variable_connection_roles(d.inductor_tree, d.capacitor_placement.variable_edges,
            d.variable_roles).as_dict()['all_declared_roles_supported_by_l_tree']:
        raise ValueError('Unproven connection role')
    max_error = 0.
    for j, (f, setting) in enumerate(zip(response.grid.frequency_hz, response.grid.setting)):
        ref = evaluate_independent_response(model, x, float(f), int(setting))
        for key in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
            actual, expected = np.asarray(getattr(response, key)[j]), np.asarray(ref[key])
            if not np.allclose(actual, expected, rtol=0, atol=atol, equal_nan=False):
                raise ValueError(f'Independent MNA mismatch: {key} sample {j}')
            finite = np.isfinite(actual) & np.isfinite(expected)
            if np.any(finite):
                max_error = max(max_error, float(np.max(abs(actual[finite]-expected[finite]))))
    return {'independent_mna_checked': True, 'samples_checked': len(response.grid.frequency_hz),
            'max_abs_error': max_error, 'absolute_tolerance': atol,
            'rf_compliance_certified': False, 'continuous_band_proven': False}
