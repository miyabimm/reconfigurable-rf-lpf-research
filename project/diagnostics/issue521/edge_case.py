#!/usr/bin/env python3
"""Reproduce D wave sensitivity cancellation; real Decimal reference at 450 digits.

Synthetic wave-level input, not a claim that this occurs under RF-T010 bounds.
"""
from decimal import Decimal, localcontext
import json
import sys
from pathlib import Path
import numpy as np
from numerics import wave_derivative
from lpf.rf_core.model import power_response


def matmul(a, b):
    return [[sum(a[i][k]*b[k][j] for k in range(2)) for j in range(2)] for i in range(2)]


def inverse(a):
    det = a[0][0]*a[1][1]-a[0][1]*a[1][0]
    return [[a[1][1]/det, -a[0][1]/det], [-a[1][0]/det, a[0][0]/det]]


def decimal_reference():
    with localcontext() as ctx:
        ctx.prec = 450
        D = Decimal
        f = [[D('.8'), D('.1')], [D('.1'), D('.2')]]
        z = D('1e-200'); root50 = D(50).sqrt(); scale = 2*z.sqrt()
        alpha = (root50+z/root50)/scale
        beta = (root50-z/root50)/scale
        gamma = (root50-z/root50)/scale
        delta = (root50+z/root50)/scale
        a = [[(alpha if i == j else 0)+beta*f[i][j] for j in range(2)] for i in range(2)]
        b = [[(gamma if i == j else 0)+delta*f[i][j] for j in range(2)] for i in range(2)]
        inva = inverse(a); s = matmul(b, inva)
        # Independent implicit derivative: (delta I - S beta) dF inv(a).
        left = [[(delta if i == j else 0)-s[i][j]*beta for j in range(2)] for i in range(2)]
        df = [[D('1e125')]*2 for _ in range(2)]
        ds = matmul(matmul(left, df), inva)
        return {'s21': str(+s[1][0]), 'ds21': str(+ds[1][0]),
                'relative_ds21': str(+(ds[1][0]/s[1][0])), 'precision_digits': ctx.prec}


def main(out):
    full = np.array([[[.8, .1], [.1, .2]]], dtype=complex)
    z = np.array([1e-200, 1e-200], dtype=complex)
    df = np.ones((1, 1, 2, 2), dtype=complex)*1e125
    with np.errstate(all='ignore'):
        s, il, apl, irl, orl = power_response(full, *z)
        variants = {}
        for name, candidate in (('base', False), ('D1', 'D1'), ('D2', 'D2')):
            ds = wave_derivative(full, s, z, df, candidate)
            ds21 = ds[:, :, 1] if candidate == 'D2' else ds[:, :, 1, 0]
            jac = -20/np.log(10)*np.real(ds21/s[:, None, 1, 0])
            variants[name] = {'ds21_real': str(ds21[0, 0].real), 'ds21_imag': str(ds21[0, 0].imag),
                              'jac': str(jac[0, 0]), 'existing_il_finiteness_stop': not bool(np.isfinite(jac).all())}
    result = {'case': {'full': [[.8, .1], [.1, .2]], 'z_both': '1e-200', 'dfull_all': '1e125',
                       'synthetic_not_rf_t010_reachability': True},
              'forward_s_real': s.real.tolist(), 'forward_il': il.tolist(),
              'forward_apl': apl.tolist(), 'forward_in_rl': irl.tolist(), 'forward_out_rl': orl.tolist(),
              'variants': variants, 'decimal_reference': decimal_reference(),
              'condition_a': float(np.linalg.cond(np.eye(2)+full[0]))}
    out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    out = Path(sys.argv[1]); assert not out.exists(); main(out)
