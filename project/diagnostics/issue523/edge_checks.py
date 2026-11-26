#!/usr/bin/env python3
"""Bounded diagnostic: sample intermediate magnitudes and inject remaining solve failures."""
import json
from pathlib import Path
import sys
from unittest.mock import patch
import numpy as np

root, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
assert not out.exists()
sys.path[:0] = [str(root/'src'), str(root/'project/diagnostics/issue517')]
from measure import setup, SEEDS
from lpf.search.plan import grid_from_record
from lpf.rf_core.coupled_lc import CoupledLCTopology
from lpf.rf_core.numerical_diagnostics import CircuitNumericalError

fixed = json.loads((root/'project/diagnostics/issue519/vectors.json').read_text())
rows = []
for seed in SEEDS:
    _, starts, _, plan, _, model = setup(seed)
    ev = model.evaluator(grid_from_record(plan.data['grids']['baseline/search']))
    vectors = [('initial', starts[str(seed)]['baseline']['vector'])]
    vectors += [(k, v['vector']) for k, v in fixed.items() if k.startswith(str(seed)+'-')]
    for name, x in vectors:
        top = model.topology; values = model.decode(x); omega = 2*np.pi*ev.grid.frequency_hz
        K, M = top.matrices(values); Y = top.node_admittance(values, omega, ev.grid.setting, matrices=(K, M))
        n = top.inductor_tree.node_count
        ports = (top.inductor_tree.source_node, top.inductor_tree.load_node)
        order = np.array(ports + tuple(i for i in range(n) if i not in ports))
        ordered = Y[:, order[:, None], order]
        T = np.empty((len(Y), n, 2), complex); T[:, order[:2]] = np.eye(2)
        T[:, order[2:]] = -np.linalg.solve(ordered[:, 2:, 2:], ordered[:, 2:, :2])
        L = np.asarray(values.inductances_nh); k = np.asarray(values.coupling_k); ni = len(L)
        dH = np.zeros((ni+len(k), ni, ni), complex)
        for i in range(ni): dH[i, i, i] = 1/top.inductor_q[i]+1j
        for j, (a,b) in enumerate(top.coupling_pairs):
            dH[a,a,b]=dH[a,b,a]=1j*M[a,b]/(2*L[a])
            dH[b,a,b]=dH[b,b,a]=1j*M[a,b]/(2*L[b])
            dH[ni+j,a,b]=dH[ni+j,b,a]=1j*np.sqrt(L[a]*L[b])
        H = np.diag(L/np.asarray(top.inductor_q))+1j*M; B=top.inductor_tree.incidence()
        X = np.linalg.solve(H, B.T); dK=-B@np.linalg.solve(H, dH@X)
        product = T.swapaxes(-1,-2)[:,None]@dK[None]@T[:,None]
        rows.append(dict(seed=seed, vector=name, min_omega=float(omega.min()), max_omega=float(omega.max()),
                         max_T=float(np.abs(T).max()), max_dK=float(np.abs(dK).max()),
                         max_unscaled_projection=float(np.abs(product).max()), min_scale=float((omega*1e-9).min())))
# Inject only the remaining X solve, after all forward solves have completed.
active = False
original = CoupledLCTopology.port_admittance_jacobian
solve = np.linalg.solve
results = {}
for behavior in ('raise', 'nan'):
    def marked(self, *args, **kwargs):
        global active
        active = True
        try: return original(self, *args, **kwargs)
        finally: active = False
    def injected(a, b):
        if active and a.ndim == 2 and b.ndim == 2:
            if behavior == 'raise': raise np.linalg.LinAlgError('injected remaining X solve')
            return np.full_like(solve(a, b), np.nan)
        return solve(a, b)
    with patch.object(CoupledLCTopology, 'port_admittance_jacobian', marked), patch('numpy.linalg.solve', injected):
        try: ev.evaluate_with_il_jacobian(x)
        except CircuitNumericalError as exc: results[behavior] = exc.code
        else: raise AssertionError('nonfinite/failed solve accepted')
assert results == {'raise': 'sensitivity_inductor_solve_failed', 'nan': 'sensitivity_node_nonfinite'}
# Scale-before-projection versus projection-before-scale; synthetic, not a circuit.
dk = np.full((1,1), 1e300+0j); lift = np.full((1,1), 1e5+0j); scale = 1e10
with np.errstate(all='ignore'):
    old = lift.T @ (dk / scale) @ lift
    new = (lift.T @ dk @ lift) / scale
assert np.isfinite(old).all() and not np.isfinite(new).all()
out.write_text(json.dumps(dict(rows=rows, injected=results,
    synthetic=dict(dK='1e300', T='1e5', scale='1e10', old=str(old[0,0]), new=str(new[0,0]))), indent=2)+'\n')
