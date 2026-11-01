"""Small lossless L-match hypothesis, NOT a general coupled-LC synthesizer."""
import numpy as np


def impedance(abcd, termination):
    a, b, c, d = np.asarray(abcd).reshape(-1)
    return (a * termination + b) / (c * termination + d)


def design_candidates(problem, nominal):
    """Two endpoint-setting anchors; unsupported topology fails, never projects.

    Only a pure series L path with one port shunt IC pair is supported.
    Distributed parasitic/loss/coupling effects are intentionally left to the
    SAME external-port forward as Sobol. All six Cv remain independent later.
    Uses existing coarse-grid pass samples as representative frequencies, so
    no unmetered circuit forwards or new frequency interpolation are needed.
    """
    circuit, evaluator = problem.circuit, problem.evaluator
    definition, schema = circuit.definition, circuit.schema
    tree, caps = definition.inductor_tree, definition.capacitor_placement
    degree = [0] * tree.node_count
    for a, b in tree.edges:
        degree[a] += 1
        degree[b] += 1
    shunt = frozenset(caps.variable_edges[0]) if caps.variable_edges else frozenset()
    at_input = shunt == frozenset((tree.source_node, -1))
    if (degree[tree.source_node] != 1 or degree[tree.load_node] != 1 or
            any(degree[i] != 2 for i in range(tree.node_count)
                if i not in (tree.source_node, tree.load_node)) or
            schema.n_fixed != 0 or schema.n_variable != 1 or
            schema.n_ic_fixed != 1 or schema.constant_caps_pf or
            shunt not in (frozenset((tree.source_node, -1)),
                          frozenset((tree.load_node, -1)))):
        raise ValueError('Design prototype requires pure series L path and one port shunt IC pair')
    # Source killed at external input: reverse the input ABCD to look back.
    representatives = []
    for setting in range(6):
        indices = np.flatnonzero((evaluator.setting == setting) & (evaluator.role == 0))
        mean = np.mean(evaluator.f[indices])
        i = min(indices, key=lambda j: (abs(evaluator.f[j] - mean), evaluator.f[j]))
        pre = evaluator.pre[i]
        reverse = np.array([[pre[1, 1], pre[0, 1]], [pre[1, 0], pre[0, 0]]])
        zs = impedance(reverse, evaluator.source_ohms)
        zl = impedance(evaluator.post[i], evaluator.load_ohms)
        y = 1 / zl
        target_y = 1 / zs.conjugate()
        radicand = (zl.real / target_y.real - zl.real ** 2 if at_input
                    else y.real / zs.real - y.real ** 2)
        if min(zs.real, zl.real) <= 0 or radicand < 0:
            raise ValueError(f'Setting {setting}, {evaluator.f[i]:g} MHz: no real low-pass L-match; radicand={radicand:g}')
        if at_input:
            t = np.sqrt(radicand)
            x = t - zl.imag
            b = target_y.imag - (1 / complex(zl.real, t)).imag
        else:
            b = np.sqrt(radicand) - y.imag
            x = -zs.imag - (1 / (y + 1j * b)).imag
        if not np.isfinite(x + b) or min(x, b) <= 0:
            raise ValueError(f'Setting {setting}, {evaluator.f[i]:g} MHz: non-positive L/C hypothesis; X={x:g} ohm, B={b:g} S; no repair')
        representatives.append({'setting': setting, 'frequency_mhz': float(evaluator.f[i]),
            'source_ohms': [float(zs.real), float(zs.imag)],
            'load_ohms': [float(zl.real), float(zl.imag)],
            'series_x_ohms': float(x), 'shunt_b_siemens': float(b)})
    rows = []
    nl, nk = schema.n_inductors, schema.n_coupling
    fixed_index = nl + nk
    for anchor in (0, 5):
        ref = representatives[anchor]
        omega = 2e6 * np.pi * ref['frequency_mhz']
        total_l = ref['series_x_ohms'] / omega * 1e9
        total_c = ref['shunt_b_siemens'] / omega * 1e12
        vector = np.asarray(nominal, float).copy()
        # Equal electrical series reactance allocation, not an L upper bound.
        vector[:nl] = total_l / nl
        vector[nl:nl + nk] = 0.  # uncoupled initial hypothesis; full signed box retained
        vector[fixed_index] = problem.box.bounds[fixed_index][0]
        for setting, rep in enumerate(representatives):
            # Constant LC frequency-scaling hypothesis, NOT a transmission zero.
            target = total_c * (ref['frequency_mhz'] / rep['frequency_mhz']) ** 2
            vector[fixed_index + 1 + setting] = target - vector[fixed_index]
        resistance = omega * vector[:nl] * 1e-9 / np.asarray(evaluator.topology.inductor_q)
        diagnostics = []
        for rep in representatives:
            w = 2e6 * np.pi * rep['frequency_mhz']
            i = int(np.flatnonzero((evaluator.setting == rep['setting']) &
                                  (evaluator.f == rep['frequency_mhz']))[0])
            c_pf = vector[fixed_index] + vector[fixed_index + 1 + rep['setting']]
            series = np.array([[1, 1j * w * total_l * 1e-9], [0, 1]])
            parallel = np.array([[1, 0], [1j * w * c_pf * 1e-12, 1]])
            bare = parallel @ series if at_input else series @ parallel
            full = evaluator.pre[i] @ bare @ evaluator.post[i]
            zin = impedance(full, evaluator.load_ohms)
            a, b, c, d = full.reshape(-1)
            den = a * evaluator.load_ohms + b + evaluator.source_ohms * (c * evaluator.load_ohms + d)
            gt = 4 * evaluator.source_ohms.real * evaluator.load_ohms.real / abs(den) ** 2
            diagnostics.append({'setting': rep['setting'], 'frequency_mhz': rep['frequency_mhz'],
                'external_zin_ohms': [float(zin.real), float(zin.imag)],
                'external_gt': float(gt), 'model': 'lossless_uncoupled_lumped_hypothesis_not_forward'})
        rows.append({'vector': vector, 'design': {'anchor_setting': anchor,
            'shunt_port': 'input' if at_input else 'output', 'approximate_response': diagnostics,
            'representatives': representatives, 'total_series_L_nh': total_l,
            'anchor_total_C_pf': total_c,
            'series_loss_ohms_by_L': resistance.tolist(),
            'loss_note': 'secondary R=omega L/Q estimate, not an RF ranking or current-weighted loss'}})
    return rows
