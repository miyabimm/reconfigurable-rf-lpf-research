#!/usr/bin/env python3
"""Fixed-vector C/D derivative comparison; does not patch production or run a search."""
import hashlib
import json
import os
from pathlib import Path
import platform
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / 'issue517'))
from measure import setup, SEEDS, THREADS
from lpf.rf_core.model import _cascade, _cascade_jacobian, power_response
from lpf.minimax_profile import _margin_parameters
from lpf.search.plan import grid_from_record
from lpf.search.storage import vector_sha


def compare(a, b):
    diff = np.abs(a-b)
    return {'max_abs': float(np.max(diff)),
            'relative_to_max': float(np.max(diff)/max(float(np.max(np.abs(a))), 1e-300))}


def core_derivative(A, core, dR, candidate):
    eye = np.eye(2)
    if candidate:
        q = eye + core[:, None]
        return -25 * (q @ dR @ q)
    rhs = -50*dR @ (eye + core[:, None])
    n, p = rhs.shape[:2]
    packed = rhs.transpose(0, 2, 1, 3).reshape(n, 2, 2*p)
    return np.linalg.solve(A, packed).reshape(n, 2, p, 2).transpose(0, 2, 1, 3)


def wave_derivative(full, s, z, dfull, candidate):
    eye = np.eye(2)
    scale = 2*np.sqrt(z.real)
    if candidate:
        beta = (np.sqrt(50.) - z/np.sqrt(50.))/scale
        delta = (np.sqrt(50.) + z.conj()/np.sqrt(50.))/scale
        P = np.diag(delta) - s*beta[None, None, :]
        Q = np.diag(delta) - beta[None, :, None]*s
        if candidate == 'D2':
            W = P[:, None] @ dfull
            return np.stack([np.sum(W[:, :, i, :]*Q[:, None, :, j], axis=-1)
                             for i, j in ((0, 0), (1, 0), (1, 1))], axis=-1)
        return P[:, None] @ dfull @ Q[:, None]
    scale4 = scale[None, None, :, None]
    da = (np.sqrt(50.) - z[None, None, :, None]/np.sqrt(50.))*dfull/scale4
    db = (np.sqrt(50.) + z.conj()[None, None, :, None]/np.sqrt(50.))*dfull/scale4
    v = np.sqrt(50.)*(eye+full)
    i = (eye-full)/np.sqrt(50.)
    a = (v + z[None, :, None]*i)/scale[None, :, None]
    rhs = (db-s[:, None]@da).swapaxes(-1, -2)
    n, p = rhs.shape[:2]
    packed = rhs.transpose(0, 2, 1, 3).reshape(n, 2, 2*p)
    return np.linalg.solve(a.swapaxes(-1, -2), packed).reshape(n, 2, p, 2).transpose(0, 2, 3, 1)


def main(out):
    assert all(os.environ.get(k) == '1' for k in THREADS)
    fixed_path = HERE.parent/'issue519/vectors.json'
    fixed = json.loads(fixed_path.read_text())
    result = {'baseline': '7957fd60e685b6afb2f62fcdc1551ab8bdbfc43d',
              'model_sha256': hashlib.sha256((ROOT/'src/lpf/rf_core/model.py').read_bytes()).hexdigest(),
              'vectors_file_sha256': hashlib.sha256(fixed_path.read_bytes()).hexdigest(),
              'python': platform.python_version(), 'numpy': np.__version__,
              'threads': {k: os.environ[k] for k in THREADS}, 'rows': []}
    for seed in SEEDS:
        _, starts, _, plan, profile, model = setup(seed)
        width = np.diff(np.asarray(plan.data['search_bounds']), axis=1).ravel()
        ev = model.evaluator(grid_from_record(plan.data['grids']['baseline/search']))
        vectors = [('initial', starts[str(seed)]['baseline']['vector'])]
        for key, record in fixed.items():
            if key.startswith(str(seed)+'-'):
                assert vector_sha(record['vector']) == record['vector_sha256']
                vectors.append((key, record['vector']))
        assert len(vectors) == 3
        for name, x in vectors:
            top = model.topology
            values = model.decode(x)
            omega = 2*np.pi*ev.grid.frequency_hz
            Y, dY = top.node_admittance_with_jacobian(values, model.schema, omega, ev.grid.setting)
            ports = (top.inductor_tree.source_node, top.inductor_tree.load_node)
            order = np.asarray(ports + tuple(i for i in range(Y.shape[1]) if i not in ports))
            Y = Y[:, order[:, None], order]; dY = dY[:, :, order[:, None], order]
            U, V, E = Y[:, :2, 2:], Y[:, 2:, :2], Y[:, 2:, 2:]
            X = np.linalg.solve(E, V)
            R = Y[:, :2, :2]-U@X
            T = np.concatenate((np.broadcast_to(np.eye(2), (len(Y), 2, 2)), -X), axis=1)
            dR = T.swapaxes(-1, -2)[:, None] @ dY @ T[:, None]
            A = np.eye(2)+50*R
            core = np.linalg.solve(A, np.eye(2)-50*R)
            first = _cascade(ev.pre, core); full = _cascade(first, ev.post)
            data = power_response(full, ev.source_ohms, ev.load_ohms)
            response, jac = ev.evaluate_with_il_jacobian(x)
            for i, field in enumerate(('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db')):
                np.testing.assert_allclose(getattr(response, field), data[i], rtol=1e-12, atol=1e-12)
            z = np.asarray([ev.source_ohms, ev.load_ohms])
            threshold, direction = _margin_parameters(profile, ev.grid)
            active = direction*(data[1]-threshold) > 0
            derivatives = {}
            all_ds = {}
            for c in (False, True):
                dc = core_derivative(A, core, dR, c)
                df = _cascade_jacobian(ev.pre, None, core, dc)
                df = _cascade_jacobian(first, df, ev.post, None)
                for d in (False, 'D1', 'D2'):
                    ds = wave_derivative(full, data[0], z, df, d)
                    if d != 'D2':
                        all_ds[(c, d)] = ds
                        ds = ds[:, :, (0, 1, 1), (0, 0, 1)]
                    il = -20/np.log(10)*np.real(ds[:, :, 1]/data[0][:, None, 1, 0])
                    derivatives[(c, d)] = (dc, df, ds, il*width[None, :])
            ref = derivatives[(False, False)]
            np.testing.assert_allclose(ref[3], jac*width[None, :], rtol=1e-12, atol=1e-12)
            row = {'seed': seed, 'vector': name, 'vector_sha256': vector_sha(x),
                   'plan_sha256': plan.sha256,
                   'condition_A_max': float(np.max(np.linalg.cond(A))), 'variants': {}}
            for (c, d), actual in derivatives.items():
                key = ('C' if c else '') + (d or '') or 'base'
                errors = {k: compare(a, b) for k, a, b in zip(('dcore', 'dfull', 'ds_11_21_22', 'normalized_il'), ref, actual)}
                if d != 'D2':
                    errors['ds_all_four'] = compare(all_ds[(False, False)], all_ds[(c, d)])
                errors['normalized_residual'] = compare(np.sqrt(2)*active[:, None]*direction[:, None]*ref[3],
                                                       np.sqrt(2)*active[:, None]*direction[:, None]*actual[3])
                np.testing.assert_allclose(actual[3], ref[3], rtol=1e-4, atol=1e-5)
                row['variants'][key] = errors
            result['rows'].append(row)
    out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    path = Path(sys.argv[1]); assert not path.exists()
    main(path)
