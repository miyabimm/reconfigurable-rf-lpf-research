#!/usr/bin/env python3
"""Compare compact port sensitivities to independently assembled nodal derivatives."""
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'project/diagnostics/issue517'), str(ROOT/'project/diagnostics/issue521')]
from measure import setup, SEEDS
from numerics import wave_derivative
from lpf.rf_core.model import _cascade, _cascade_jacobian, power_response
from lpf.minimax_profile import least_squares_residual_and_jacobian
from lpf.search.plan import grid_from_record
from lpf.search.storage import vector_sha


def main(out):
    assert not out.exists()
    fixed = json.loads((ROOT/'project/diagnostics/issue519/vectors.json').read_text())
    records = []
    for seed in SEEDS:
        _, starts, _, plan, profile, model = setup(seed)
        ev = model.evaluator(grid_from_record(plan.data['grids']['baseline/search']))
        vectors = [('initial', starts[str(seed)]['baseline']['vector'])]
        vectors += [(k, v['vector']) for k, v in fixed.items() if k.startswith(str(seed)+'-')]
        for name, x in vectors:
            top, schema, g = model.topology, model.schema, ev.grid
            values = model.decode(x); omega = 2*np.pi*g.frequency_hz
            matrices = top.matrices(values)
            Y, dY = top.node_admittance_with_jacobian(values, schema, omega, g.setting, matrices=matrices)
            ports = (top.inductor_tree.source_node, top.inductor_tree.load_node)
            order = np.array(ports + tuple(i for i in range(Y.shape[1]) if i not in ports))
            ordered = Y[:, order[:, None], order]
            internal = np.linalg.solve(ordered[:, 2:, 2:], ordered[:, 2:, :2])
            R = ordered[:, :2, :2] - ordered[:, :2, 2:] @ internal
            T = np.empty((len(Y), Y.shape[1], 2), complex)
            T[:, order[:2]] = np.eye(2); T[:, order[2:]] = -internal
            ref = T.swapaxes(-1, -2)[:, None] @ dY @ T[:, None]
            compact = top.port_admittance_jacobian(values, schema, omega, g.setting, T, matrices=matrices)
            shared = schema.vector_length - len(values.capacitors_pf_by_setting)*schema.n_variable
            cols = shared + g.setting[:, None]*schema.n_variable + np.arange(schema.n_variable)
            actual = np.zeros_like(ref)
            actual[:, :shared] = compact[:, :shared]
            actual[np.arange(len(Y))[:, None], cols] = compact[:, shared:]
            eye = np.eye(2); A = eye + 50*R
            core = np.linalg.solve(A, eye-50*R)
            first = _cascade(ev.pre, core); full = _cascade(first, ev.post)
            data = power_response(full, ev.source_ohms, ev.load_ohms)
            response, jac = ev.evaluate_with_il_jacobian(x)
            errors = {}
            for field, expected in zip(('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'), data):
                np.testing.assert_allclose(getattr(response, field), expected, rtol=1e-12, atol=1e-12)
            def chain(dR):
                Q = eye+core[:, None]; dc = -25*(Q@dR@Q)
                df = _cascade_jacobian(first, _cascade_jacobian(ev.pre, None, core, dc), ev.post, None)
                ds = wave_derivative(full, data[0], np.array([ev.source_ohms, ev.load_ohms]), df, 'D1')
                il = -20/np.log(10)*np.real(ds[:, :, 1, 0]/data[0][:, None, 1, 0])
                return dc, df, ds, il
            old, new = chain(ref), chain(actual)
            width = np.diff(np.asarray(plan.data['search_bounds']), axis=1).ravel()
            for label, a, b in [('dR', ref, actual)] + list(zip(('dcore', 'dfull', 'ds_all4', 'physical_il'), old, new)):
                np.testing.assert_allclose(a, b, rtol=1e-11, atol=1e-11)
                errors[label] = float(np.max(np.abs(a-b)))
            np.testing.assert_allclose(jac, old[-1], rtol=1e-11, atol=1e-11)
            _, rj1 = least_squares_residual_and_jacobian(profile, response, jac)
            _, rj0 = least_squares_residual_and_jacobian(profile, response, old[-1])
            errors['normalized_il'] = float(np.max(np.abs((old[-1]-jac)*width)))
            errors['normalized_residual'] = float(np.max(np.abs((rj0-rj1)*width)))
            records.append(dict(seed=seed, vector=name, vector_sha256=vector_sha(x), plan_sha256=plan.sha256, max_abs=errors))
    out.write_text(json.dumps(records, indent=2, allow_nan=False)+'\n')

if __name__ == '__main__':
    main(Path(sys.argv[1]))
