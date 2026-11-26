#!/usr/bin/env python3
"""Verify fixed candidate commits against the original fixed-vector diagnostics."""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import numpy as np
import kernel
from numerics import HERE, ROOT, SEEDS, THREADS, setup
import lpf.rf_core.model as rf
from lpf.search.plan import grid_from_record
from lpf.search.storage import vector_sha


def source_at(commit):
    text = subprocess.check_output(['git', 'show', f'{commit}:src/lpf/rf_core/model.py'], cwd=ROOT, text=True)
    tree = ast.parse(text)
    cls = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == 'RFEvaluator')
    fn = next(x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name == 'evaluate_with_il_jacobian')
    return textwrap.dedent(''.join(text.splitlines(keepends=True)[fn.lineno-1:fn.end_lineno]))


def compile_method(source):
    ns = {}
    exec(compile(source, '<issue521-committed-production>', 'exec'), rf.__dict__, ns)
    return ns['evaluate_with_il_jacobian']


def main(out):
    assert all(os.environ.get(k) == '1' for k in THREADS)
    base = '7957fd60e685b6afb2f62fcdc1551ab8bdbfc43d'
    commits = {'D1': '729e12453c882bf23b91cf8d79c02cb0f31b4392',
               'CD1': '4d3def8f636f14938097f22965315fc22d6ab7ca'}
    kernel.SOURCE = source_at(base)
    methods = {}
    for mode, commit in commits.items():
        diagnostic, diag_sha = kernel.variant(mode == 'CD1', 'D1')
        src = source_at(commit)
        methods[mode] = (diagnostic, compile_method(src), diag_sha, hashlib.sha256(src.encode()).hexdigest())
    fixed = json.loads((HERE.parent/'issue519/vectors.json').read_text())
    result = {'baseline': base, 'commits': commits, 'rows': []}
    for seed in SEEDS:
        _, starts, _, plan, _, model = setup(seed)
        ev = model.evaluator(grid_from_record(plan.data['grids']['baseline/search']))
        vectors = [('initial', starts[str(seed)]['baseline']['vector'])]
        vectors += [(k, v['vector']) for k, v in fixed.items() if k.startswith(str(seed)+'-')]
        for name, x in vectors:
            row = {'seed': seed, 'vector': name, 'vector_sha256': vector_sha(x), 'variants': {}}
            for mode, (reference, actual, dsha, psha) in methods.items():
                a, aj = reference(ev, x); b, bj = actual(ev, x)
                fields = {field: (getattr(a, field), getattr(b, field)) for field in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db')}
                fields['jac'] = aj, bj
                for field, (u, v) in fields.items():
                    np.testing.assert_array_equal(u, v, err_msg=f'{mode} {seed} {name} {field}')
                row['variants'][mode] = {'bitwise_equal': True, 'diagnostic_source_sha256': dsha,
                                         'production_source_sha256': psha}
            result['rows'].append(row)
    out.write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    out = Path(sys.argv[1]); assert not out.exists(); main(out)
