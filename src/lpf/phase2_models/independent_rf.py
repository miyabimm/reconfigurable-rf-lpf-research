"""Independent single-sample external-port MNA and peak-phasor power audit.

The fixed S networks are converted directly to port admittances; no forward
LPF nodal, Schur or ABCD matrix is used. A sample is not RF certification.
"""
import numpy as np

from lpf.port_parasitics import get_two_port_s
from .branch_mna import solve_branch_mna
from .circuit_layout import incidence_matrix
from .coupled_lc import _fixed_port_impedance


def _s_admittance(s):
    eye = np.eye(2, dtype=complex)
    a = eye + s
    if not np.all(np.isfinite(a)) or np.linalg.cond(a) >= 1e12:
        raise ValueError("Ill-conditioned S-to-admittance conversion")
    return np.linalg.solve(a.T, (eye - s).T).T / 50


def evaluate_independent_sample(circuit, vector, frequency_hz, setting):
    """Evaluate one policy-bound sample; power quantities are in watts.

    A 1 V peak Thevenin source is assumed. The source resistor loss is
    excluded from input power; external network losses are reported separately.
    """
    policy = circuit._adapter.policy
    zs = _fixed_port_impedance(policy, "source_ohms")
    zl = _fixed_port_impedance(policy, "load_ohms")
    f = float(frequency_hz)
    if not np.isfinite(f) or f <= 0:
        raise ValueError("Invalid frequency")
    values = circuit.decode(vector) if not hasattr(vector, "inductances_nh") else vector
    circuit.encode(values)
    pre = _s_admittance(get_two_port_s(policy, "input_parasitic", f))
    post = _s_admittance(get_two_port_s(policy, "output_parasitic", f))
    # Port order is external, core for pre; core, external for post.
    ds, dl = pre[0, 0] + 1/zs, post[1, 1] + 1/zl
    if abs(ds) < 1e-14 or abs(dl) < 1e-14:
        raise ValueError("Singular external termination")
    n = circuit.topology.inductor_tree.node_count
    src, load = circuit.topology.inductor_tree.source_node, circuit.topology.inductor_tree.load_node
    term = np.zeros(n, complex)
    injected = np.zeros(n, complex)
    term[src] += pre[1, 1] - pre[1, 0] * pre[0, 1] / ds
    term[load] += post[0, 0] - post[0, 1] * post[1, 0] / dl
    injected[src] = -pre[1, 0] / (zs * ds)
    voltage, current = solve_branch_mna(circuit, values, f, setting,
        injected_currents_a=injected, termination_admittances_s=term)
    vin = (1/zs - pre[0, 1] * voltage[src]) / ds
    vout = -post[1, 0] * voltage[load] / dl
    vp = np.array([vin, voltage[src]])
    vq = np.array([voltage[load], vout])
    ip, iq = pre @ vp, post @ vq
    power = lambda v, i: float(.5 * np.real(v * np.conj(i)))
    input_power = power(vin, ip[0])
    pre_loss = sum(power(v, i) for v, i in zip(vp, ip))
    post_loss = sum(power(v, i) for v, i in zip(vq, iq))
    load_power = .5 * abs(vout)**2 * (1/zl).real
    omega = 2*np.pi*f
    topology = circuit.topology
    l_loss = .5 * np.sum(abs(current)**2 * omega * np.asarray(values.inductances_nh)*1e-9 / np.asarray(topology.inductor_q))
    bc = incidence_matrix(topology.capacitor_edges, n)
    cap = np.asarray(values.capacitors_pf_by_setting[setting]) * 1e-12
    yc = omega * cap / (1/np.asarray(topology.capacitor_q) - 1j)
    c_loss = .5 * np.sum(abs(bc.T @ voltage)**2 * yc.real)
    available = 1/(8*zs.real)
    gain = float(load_power/available)
    if not np.isfinite(gain) or gain <= 0:
        raise ValueError("Invalid transducer gain")
    return {"gain": gain, "il_db": float(-10*np.log10(gain)),
            "input_power_w": input_power, "load_power_w": float(load_power),
            "inductor_loss_w": float(l_loss), "capacitor_loss_w": float(c_loss),
            "input_s2p_loss_w": float(pre_loss), "output_s2p_loss_w": float(post_loss),
            "power_residual_w": float(input_power-load_power-l_loss-c_loss-pre_loss-post_loss),
            "rf_compliance_certified": False, "candidate_promotion_blocked": True}
