#!/usr/bin/env python3
"""Reproduce old nonfinite / D1 finite at the current fixed references."""
import json
from pathlib import Path
import sys
import numpy as np
from numerics import wave_derivative
from lpf.rf_core.model import power_response


def complex_data(a):
    return {'real': a.real.tolist(), 'imag': a.imag.tolist()}


def main(out):
    rng = np.random.default_rng(521)
    full = .2*(rng.normal(size=(1, 2, 2))+1j*rng.normal(size=(1, 2, 2)))
    direction = rng.normal(size=(1, 1, 2, 2))+1j*rng.normal(size=(1, 1, 2, 2))
    z = np.array([50, 60-40j], complex)
    s, il, apl, in_rl, out_rl = power_response(full, *z, check_power=True)
    rows = []
    with np.errstate(all='ignore'):
        for factor in (.5, .8, .9, 1., 1.05, 1.1, 1.15):
            df = direction*(factor*1e307)
            assert np.isfinite(df).all()
            row = {'factor': factor, 'variants': {}}
            for name, mode in [('base', False), ('D1', 'D1'), ('D2', 'D2')]:
                ds = wave_derivative(full, s, z, df, mode)
                ds21 = ds[:, :, 1] if mode == 'D2' else ds[:, :, 1, 0]
                jac = -20/np.log(10)*np.real(ds21/s[:, None, 1, 0])
                row['variants'][name] = {'jac': str(jac[0, 0]), 'stop': not bool(np.isfinite(jac).all()),
                                          'ds21_real': str(ds21[0, 0].real), 'ds21_imag': str(ds21[0, 0].imag)}
            rows.append(row)
    assert rows[3]['variants']['base']['stop'] and not rows[3]['variants']['D1']['stop']
    result = {'seed': 521, 'z': ['50+0j', '60-40j'], 'full': complex_data(full),
              'direction_before_1e307_scaling': complex_data(direction),
              'forward_s': complex_data(s), 'forward_db': {'il': il.tolist(), 'apl': apl.tolist(),
              'in_rl': in_rl.tolist(), 'out_rl': out_rl.tolist()},
              'forward_loss_eigenvalues': np.linalg.eigvalsh(np.eye(2)-full.conj().transpose(0, 2, 1)@full).tolist(),
              'power_response_check_power': 'pass', 'rows': rows,
              'scope': 'synthetic wave inputs; circuit reachability unverified'}
    out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    out = Path(sys.argv[1]); assert not out.exists(); main(out)
