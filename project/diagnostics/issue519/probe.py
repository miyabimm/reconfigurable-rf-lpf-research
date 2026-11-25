#!/usr/bin/env python3
"""Issue 519 experimental A/B switches; never installed in the production path.

Run: OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    uv run --frozen python project/diagnostics/issue519/probe.py kernel /tmp/issue519-kernel.json
Inputs are #517 initial and retained checkpoint vectors; this is not an EXP.
"""
import hashlib
import inspect
import json
import os
from pathlib import Path
import statistics
import sys
import textwrap
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'issue517'))
from measure import ROOT, SEEDS, THREADS, setup
import numpy as np
import lpf.rf_core.model as rf
from lpf.minimax_profile import least_squares_residual_and_jacobian
from lpf.search.plan import grid_from_record
from lpf.search.storage import vector_sha

ORIGINAL = rf.RFEvaluator.evaluate_with_il_jacobian
OLD_CASCADE = rf._cascade_jacobian
SOURCE = textwrap.dedent(inspect.getsource(ORIGINAL))
OLD_SCHUR = '''        dU, dV, dE = dY[:, :, :2, 2:], dY[:, :, 2:, :2], dY[:, :, 2:, 2:]
        rhs = dV - dE @ internal[:, None]  # [samples, directions, internal, 2]
        samples, directions, internal_nodes, _ = rhs.shape
        packed = rhs.transpose(0, 2, 1, 3).reshape(samples, internal_nodes, directions * 2)
        dX = np.linalg.solve(E, packed).reshape(samples, internal_nodes, directions, 2).transpose(0, 2, 1, 3)
        dR = dR - dU @ internal[:, None] - U[:, None] @ dX'''
NEW_SCHUR = '''        T = np.concatenate((np.broadcast_to(eye, (Y.shape[0], 2, 2)), -internal), axis=1)
        dR = T.swapaxes(-1, -2)[:, None] @ dY @ T[:, None]'''


def cascade_one_side(a, da, b, db):
    q = 1 / (1 - a[:, 1, 1] * b[:, 0, 0])
    q2 = q*q
    a12, a21, a22 = a[:, 0, 1], a[:, 1, 0], a[:, 1, 1]
    b11, b12, b21 = b[:, 0, 0], b[:, 0, 1], b[:, 1, 0]
    if da is None:
        d11, d12, d21, d22 = (db[:, :, i, j] for i, j in ((0, 0), (0, 1), (1, 0), (1, 1)))
        out = np.empty_like(db)
        out[:, :, 0, 0] = (a12*a21*q2)[:, None]*d11
        out[:, :, 0, 1] = a12[:, None]*(q[:, None]*d12 + (b12*a22*q2)[:, None]*d11)
        out[:, :, 1, 0] = a21[:, None]*(q[:, None]*d21 + (b21*a22*q2)[:, None]*d11)
        out[:, :, 1, 1] = d22 + (a22*q)[:, None]*(d21*b12[:, None] + b21[:, None]*d12) + (a22*a22*b21*b12*q2)[:, None]*d11
    else:
        d11, d12, d21, d22 = (da[:, :, i, j] for i, j in ((0, 0), (0, 1), (1, 0), (1, 1)))
        out = np.empty_like(da)
        out[:, :, 0, 0] = d11 + (b11*q)[:, None]*(d12*a21[:, None] + a12[:, None]*d21) + (b11*b11*a12*a21*q2)[:, None]*d22
        out[:, :, 0, 1] = b12[:, None]*(q[:, None]*d12 + (a12*b11*q2)[:, None]*d22)
        out[:, :, 1, 0] = b21[:, None]*(q[:, None]*d21 + (a21*b11*q2)[:, None]*d22)
        out[:, :, 1, 1] = (b21*b12*q2)[:, None]*d22
    return out


def activate(mode):
    assert mode in ('base', 'A', 'B', 'AB')
    src = SOURCE
    if 'A' in mode:
        old_schur = textwrap.indent(textwrap.dedent(OLD_SCHUR), ' '*12)
        new_schur = textwrap.indent(textwrap.dedent(NEW_SCHUR), ' '*12)
        assert src.count(old_schur) == 1
        src = src.replace(old_schur, new_schur)
    if 'B' in mode:
        old = '''        zeros = np.zeros_like(dcore)
        dfirst = _cascade_jacobian(self.pre, zeros, core, dcore)
        dfull = _cascade_jacobian(first, dfirst, self.post, zeros)'''
        new = '''        dfirst = _cascade_jacobian(self.pre, None, core, dcore)
        dfull = _cascade_jacobian(first, dfirst, self.post, None)'''
        assert src.count(old) == 1
        src = src.replace(old, new)
    namespace = {}
    exec(compile(src, '<issue519-probe>', 'exec'), rf.__dict__, namespace)
    rf.RFEvaluator.evaluate_with_il_jacobian = namespace['evaluate_with_il_jacobian']
    rf._cascade_jacobian = cascade_one_side if 'B' in mode else OLD_CASCADE


def restore():
    rf.RFEvaluator.evaluate_with_il_jacobian = ORIGINAL
    rf._cascade_jacobian = OLD_CASCADE


def error(a, b):
    delta = np.abs(a-b)
    return dict(max_abs=float(np.max(delta)), max_scaled=float(np.max(delta/(1e-5+1e-4*np.abs(a)))))


def run_kernel(out):
    assert all(os.environ.get(k) == '1' for k in THREADS)
    vectors = json.loads((HERE/'vectors.json').read_text())
    result = {'baseline': 'be0bdb2bf3662512b30408091efc3906389c1f6e', 'pairs': 20, 'rows': []}
    for seed in SEEDS:
        _, starts, _, plan, profile, model = setup(seed)
        ev = model.evaluator(grid_from_record(plan.data['grids']['baseline/search']))
        inputs = [('initial', starts[str(seed)]['baseline']['vector'])]
        for key, record in vectors.items():
            if key.startswith(str(seed)+'-'):
                assert vector_sha(record['vector']) == record['vector_sha256']
                inputs.append((key, record['vector']))
        for name, vector in inputs:
            x = np.asarray(vector)
            activate('base'); ref, refjac = ev.evaluate_with_il_jacobian(x)
            _, ref_res_jac = least_squares_residual_and_jacobian(profile, ref, refjac)
            values = model.decode(x); top = model.topology
            omega = 2*np.pi*ev.grid.frequency_hz
            Y, dY = top.node_admittance_with_jacobian(values, model.schema, omega, ev.grid.setting)
            row = {'seed': seed, 'vector': name, 'vector_sha256': vector_sha(vector),
                   'Y_asymmetry': float(np.max(np.abs(Y-Y.swapaxes(-1,-2)))),
                   'dY_asymmetry': float(np.max(np.abs(dY-dY.swapaxes(-1,-2)))), 'variants': {}}
            for mode in ('A','B','AB'):
                activate(mode); response, jac = ev.evaluate_with_il_jacobian(x)
                _, rjac = least_squares_residual_and_jacobian(profile, response, jac)
                for field in ('s','il_db','apl_db','in_rl_db','out_rl_db'):
                    np.testing.assert_allclose(getattr(ref,field), getattr(response,field), rtol=1e-12, atol=1e-12)
                np.testing.assert_allclose(refjac, jac, rtol=1e-4, atol=1e-5)
                times = {'base': [], mode: []}
                for pair in range(20):
                    for arm in (('base',mode) if pair % 2 == 0 else (mode,'base')):
                        activate(arm)
                        t = time.perf_counter_ns(); ev.evaluate_with_il_jacobian(x); times[arm].append(time.perf_counter_ns()-t)
                diffs = [(b-a)/1e6 for a,b in zip(times['base'],times[mode])]
                row['variants'][mode] = {'jac': error(refjac,jac), 'residual_jac': error(ref_res_jac,rjac),
                    'base_ns': times['base'], 'variant_ns': times[mode], 'paired_ms_median': statistics.median(diffs),
                    'paired_ms_range': [min(diffs),max(diffs)]}
            result['rows'].append(row)
            Path(out).write_text(json.dumps(result,indent=2)+'\n')
            print(seed, name, {k: round(v['paired_ms_median'],3) for k,v in row['variants'].items()}, flush=True)
    restore()


if __name__ == '__main__':
    assert sys.argv[1] == 'kernel' and not Path(sys.argv[2]).exists()
    try:
        run_kernel(sys.argv[2])
    finally:
        restore()
