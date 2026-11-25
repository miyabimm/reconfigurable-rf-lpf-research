#!/usr/bin/env python3
"""Diagnostic candidate FD for all columns and complex S at nine fixed vectors.

Only direct fixed-vector calls use generated functions; no Runner is patched.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np
import kernel
from numerics import HERE, SEEDS, THREADS, setup, wave_derivative
import lpf.rf_core.model as rf
from lpf.search.plan import grid_from_record
from lpf.search.storage import vector_sha


def main(out):
    assert all(os.environ.get(k) == '1' for k in THREADS)
    fixed = json.loads((HERE.parent/'issue519/vectors.json').read_text())
    methods = {'base': (kernel.ORIGINAL, hashlib.sha256(kernel.SOURCE.encode()).hexdigest())}
    methods.update({name: kernel.variant(c, 'D1') for name, c in [('D1', False), ('CD1', True)]})
    result = {'baseline': '7957fd60e685b6afb2f62fcdc1551ab8bdbfc43d',
              'sources': {k: v[1] for k, v in methods.items()}, 'rows': [],
              'steps': [1e-6, 3e-6, 1e-7, 3e-7], 'rtol': 1e-4, 'il_atol': 1e-5, 'complex_s_atol': 1e-7,
              'note': 'Additional smaller steps are diagnostic, not replacements for the required two steps.'}
    for seed in SEEDS:
        _, starts, _, plan, _, model = setup(seed)
        ev = model.evaluator(grid_from_record(plan.data['grids']['baseline/search']))
        z = np.array([ev.source_ohms, ev.load_ohms])
        assert np.array_equal(z, [50+0j, 60-40j])
        bounds = np.asarray(plan.data['search_bounds'])
        width = np.diff(bounds, axis=1).ravel()
        vectors = [('initial', starts[str(seed)]['baseline']['vector'])]
        vectors += [(k, v['vector']) for k, v in fixed.items() if k.startswith(str(seed)+'-')]
        for name, vector in vectors:
            x = np.asarray(vector)
            analytic = {}
            for mode, (fn, _) in methods.items():
                captures = []
                def observe(a, da, b, db):
                    value = cascade(a, da, b, db)
                    if db is None:  # second cascade: reconstruct the full S derivative
                        captures.append((rf._cascade(a, b), value.copy()))
                    return value
                cascade = rf._cascade_jacobian
                with patch.object(rf, '_cascade_jacobian', observe):
                    response, jac = fn(ev, x)
                assert len(captures) == 1
                full, dfull = captures[0]
                ds = wave_derivative(full, response.s, z, dfull, False if mode == 'base' else 'D1')
                expected_jac = -20/np.log(10)*np.real(ds[:, :, 1, 0]/response.s[:, None, 1, 0])
                np.testing.assert_allclose(jac, expected_jac, rtol=1e-12, atol=1e-12)
                variable_start = len(x)-6*model.schema.n_variable
                for setting in range(6):
                    columns = slice(variable_start+setting*model.schema.n_variable,
                                    variable_start+(setting+1)*model.schema.n_variable)
                    np.testing.assert_array_equal(ds[ev.grid.setting != setting, columns], 0)
                analytic[mode] = (jac*width[None, :], ds*width[None, :, None, None])
            errors = {mode: {'max_abs_il': 0., 'max_abs_s': [0., 0., 0.],
                             'max_scaled_il': 0., 'max_scaled_s': [0., 0., 0.], 'violations': []}
                      for mode in methods}
            base_response = ev.evaluate(x)
            for h in (1e-6, 3e-6, 1e-7, 3e-7):
                for j in range(len(x)):
                    if x[j]-h*width[j] < bounds[j, 0] or x[j]+h*width[j] > bounds[j, 1]:
                        sign = 1 if x[j]-h*width[j] < bounds[j, 0] else -1
                        x1, x2 = x.copy(), x.copy()
                        x1[j] += sign*h*width[j]; x2[j] += sign*2*h*width[j]
                        a, b = ev.evaluate(x1), ev.evaluate(x2)
                        fd_il = sign*(-3*base_response.il_db+4*a.il_db-b.il_db)/(2*h)
                        fd_s = sign*(-3*base_response.s+4*a.s-b.s)/(2*h)
                    else:
                        plus, minus = x.copy(), x.copy()
                        plus[j] += h*width[j]; minus[j] -= h*width[j]
                        a, b = ev.evaluate(plus), ev.evaluate(minus)
                        fd_il = (a.il_db-b.il_db)/(2*h)
                        fd_s = (a.s-b.s)/(2*h)
                    for mode, (jac, ds) in analytic.items():
                        e = errors[mode]
                        bad = np.flatnonzero(np.abs(jac[:, j]-fd_il) > 1e-5+1e-4*np.abs(fd_il))
                        for i in bad:
                            e['violations'].append({'h': h, 'column': j, 'sample': int(i), 'field': 'il',
                                                    'actual': float(jac[i, j]), 'fd': float(fd_il[i])})
                        diff = np.abs(jac[:, j]-fd_il)
                        e['max_abs_il'] = max(e['max_abs_il'], float(np.max(diff)))
                        e['max_scaled_il'] = max(e['max_scaled_il'], float(np.max(diff/(1e-5+1e-4*np.abs(fd_il)))))
                        for idx, (u, v) in enumerate(((0, 0), (1, 0), (1, 1))):
                            actual, expected = ds[:, j, u, v], fd_s[:, u, v]
                            bad = np.flatnonzero(np.abs(actual-expected) > 1e-7+1e-4*np.abs(expected))
                            for i in bad:
                                e['violations'].append({'h': h, 'column': j, 'sample': int(i),
                                    'field': f's{u+1}{v+1}', 'actual': [float(actual[i].real), float(actual[i].imag)],
                                    'fd': [float(expected[i].real), float(expected[i].imag)]})
                            diff = np.abs(actual-expected)
                            e['max_abs_s'][idx] = max(e['max_abs_s'][idx], float(np.max(diff)))
                            e['max_scaled_s'][idx] = max(e['max_scaled_s'][idx],
                                float(np.max(diff/(1e-7+1e-4*np.abs(expected)))))
            result['rows'].append({'seed': seed, 'vector': name, 'vector_sha256': vector_sha(x),
                                   'plan_sha256': plan.sha256, 'errors': errors})
            print(seed, name, {k: len(v['violations']) for k, v in errors.items()}, flush=True)
    out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    out = Path(sys.argv[1]); assert not out.exists(); main(out)
