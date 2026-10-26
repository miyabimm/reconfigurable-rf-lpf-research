"""Vectorized nodal-admittance to external-port insertion loss.

This is a reusable *fast evaluator* component, not independent validation:
callers must build and independently verify their physical inductive/capacitive
admittances and the prescribed fixed external S2P chain separately. A sampled
frequency grid does not establish continuous-band RF compliance.
"""
from __future__ import annotations

import numpy as np


def external_port_il_db(
    nodal_y, input_twoport, output_twoport, *,
    port_nodes=(0, 2), source_ohms=50.0, load_ohms=60-40j,
    singular_threshold=1e-21,
):
    """Reduce internal nodes by Schur complement and compute transducer IL (dB).

    Arrays have shapes (frequency_samples, nodes, nodes) and
    (frequency_samples, 2, 2). Port nodes are zero-based internal-array
    indices. All other nodes are eliminated without changing their order.
    The two ABCD chains are the already verified fixed input and output S2P.
    """
    y = np.asarray(nodal_y, dtype=complex)
    pre = np.asarray(input_twoport, dtype=complex)
    post = np.asarray(output_twoport, dtype=complex)
    if (y.ndim != 3 or y.shape[1] != y.shape[2] or y.shape[0] < 1
            or pre.shape != (y.shape[0], 2, 2)
            or post.shape != (y.shape[0], 2, 2)):
        raise ValueError("Invalid nodal admittance or two-port array shapes")
    ports = tuple(port_nodes)
    if (len(ports) != 2 or len(set(ports)) != 2
            or any(type(i) is not int or not 0 <= i < y.shape[1] for i in ports)):
        raise ValueError("Expected two distinct in-range port indices")
    if (not np.isfinite(source_ohms) or source_ohms <= 0
            or not np.isfinite(load_ohms.real) or not np.isfinite(load_ohms.imag)
            or load_ohms.real <= 0 or singular_threshold <= 0):
        raise ValueError("Invalid termination or singularity tolerance")
    interior = tuple(i for i in range(y.shape[1]) if i not in ports)
    reduced = y[:, ports, :][:, :, ports]
    if interior:
        cross = y[:, ports, :][:, :, interior]
        lower = y[:, interior, :][:, :, ports]
        inner = y[:, interior, :][:, :, interior]
        reduced = reduced - cross @ np.linalg.solve(inner, lower)
    a, b, c, d = (
        reduced[:, 0, 0], reduced[:, 0, 1],
        reduced[:, 1, 0], reduced[:, 1, 1],
    )
    if np.any(np.abs(c) < singular_threshold):
        raise ValueError("Singular two-port transfer admittance")
    transfer = np.empty((y.shape[0], 2, 2), dtype=complex)
    transfer[:, 0, 0] = -d / c
    transfer[:, 0, 1] = -1 / c
    transfer[:, 1, 0] = -(a*d - b*c) / c
    transfer[:, 1, 1] = -a / c
    complete = pre @ transfer @ post
    denominator = (
        complete[:, 0, 0] * load_ohms + complete[:, 0, 1]
        + source_ohms
        * (complete[:, 1, 0] * load_ohms + complete[:, 1, 1])
    )
    transducer_gain = 4 * source_ohms * load_ohms.real / np.abs(denominator)**2
    return -10 * np.log10(np.maximum(transducer_gain, 1e-300))
