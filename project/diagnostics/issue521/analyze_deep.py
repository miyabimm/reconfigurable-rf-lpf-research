#!/usr/bin/env python3
"""Audit saved CLI evidence and compute non-overlapping deep breakdowns."""
import hashlib
import json
from pathlib import Path
import statistics
import sys


def load(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(path):
    path = Path(path); job = path/'job-0001'
    state, result, receipt = (load(p) for p in (path/'run.json', job/'result.json', job/'receipt.json'))
    assert state['status'] == 'completed' and state['jobs'][0]['actual'] == {
        'rf_forwards': 5001, 'rf_samples': 350476, 'independent_mna_samples': 2}
    assert result['terminal']['candidates'][0]['independent']['status'] == 'pass'
    assert set(receipt['files']) == {'input.json', 'result.json'} | {f'checkpoints/{p.name}' for p in (job/'checkpoints').iterdir()}
    for filename, info in receipt['files'].items():
        p = job/filename
        assert p.stat().st_size == info['bytes'] and digest(p) == info['sha256']
    for local in result['steps'][0]['local_run_details']:
        local.pop('wall_s'); local.pop('cpu_s')
    return {'scientific_sha256': hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest(),
            'checkpoint_sha256': [digest(x) for x in sorted((job/'checkpoints').iterdir())],
            'source_sha256': result['source_sha256'], 'plan_sha256': result['plan_sha256'],
            'nfev': sum(x['scipy_nfev'] for x in result['steps'][0]['local_run_details']),
            'njev': sum(x['scipy_njev'] for x in result['steps'][0]['local_run_details']),
            'restart_count': result['steps'][0]['restart_count'], 'stop': result['steps'][0]['stop_reason'],
            'selected_sha256': result['terminal']['candidates'][0]['vector_sha256']}


BREAKDOWNS = {
    'rf_evaluate': ['rf/decode', 'rf/matrices', 'rf/node_admittance', 'rf/jac_forward/reorder',
                    'rf/jac_forward/schur_solve', 'rf/jac_forward/schur_update', 'rf/jac_forward/y_to_s_build',
                    'rf/jac_forward/y_to_s_solve', 'rf/cascade', 'rf/power_response', 'rf/node_jacobian',
                    'rf/jac_sensitivity/reorder', 'rf/jac_sensitivity/schur', 'rf/jac_sensitivity/y_to_s',
                    'rf/cascade_jacobian', 'rf/jac_sensitivity/wave', 'rf/jac_sensitivity/il', 'rf/jac_sensitivity/freeze'],
    'rf/node_jacobian': ['rf/node_jacobian/schema', 'rf/node_jacobian/dh', 'rf/node_jacobian/hb',
                         'rf/node_jacobian/inductor_solve', 'rf/node_jacobian/expand',
                         'rf/node_jacobian/c_stamps', 'rf/node_jacobian/finite'],
    'rf/jac_sensitivity/y_to_s': ['rf/jac_sensitivity/y_to_s/prepare', 'rf/jac_sensitivity/y_to_s/solve',
                                    'rf/jac_sensitivity/y_to_s/reshape', 'rf/jac_sensitivity/y_to_s/product'],
    'rf/jac_sensitivity/wave': ['rf/jac_sensitivity/wave/prepare', 'rf/jac_sensitivity/wave/solve',
                                'rf/jac_sensitivity/wave/reshape', 'rf/jac_sensitivity/wave/product'],
    'trf/calc': ['trf/calc/cache_check', 'trf/calc/coordinates', 'trf/calc/worker',
                 'trf/calc/validate_objective', 'trf/calc/observe_cache'],
    'trf/calc/worker': ['worker_jac/budget', 'rf_evaluate', 'worker_jac/identity_audit', 'jacobian_residual'],
    'trf/least_squares': ['trf/calc'],
    'solver': ['trf/local'],
    'search': ['evaluator_setup', 'solver'],
}


def breakdown(regions):
    pre = 'baseline/search/'
    out = {}
    for parent, children in BREAKDOWNS.items():
        p = regions[pre+parent]
        child = {name: regions[pre+name] for name in children if pre+name in regions}
        ns = p['wall_ns']; total = sum(r['wall_ns'] for r in child.values())
        out[parent] = {'parent_wall_ns': ns, 'parent_count': p['count'], 'child_regions': list(child),
                       'children_wall_ns': total, 'other_ns': ns-total,
                       'other_fraction': (ns-total)/ns if ns else None}
    return out


def main(root, output, version='2'):
    assert version in ('1', '2')
    root = Path(root)
    compare = load(root/('compare' if version == '1' else 'compare-v2')/'summary.json'); assert compare['complete']
    baseline = {}; runs = []
    for row in compare['runs']:
        a = audit(row['output']); key = (row['seed'], row['mode'])
        if key in baseline: assert a == baseline[key]
        else: baseline[key] = a
        record = dict(row, audit=a)
        if row['level'] == 'deep':
            t = load(row['timing']); record['timing_sha256'] = digest(row['timing'])
            record['breakdown'] = breakdown(t['jobs'][0]['regions'])
            record['regions'] = t['jobs'][0]['regions']
        runs.append(record)
    trace = load(root/('trace-v2' if version == '1' else 'trace-v3')/'summary.json'); assert trace['complete']
    traces = []
    for row in trace['runs']:
        a = audit(row['output']); assert a == baseline[(row['seed'], row['mode'])]
        vector = load(row['trace']); assert vector['count'] == 5000
        traces.append(dict(row, vector_trace=vector, audit=a))
    for seed in (1001, 1010, 1020):
        for mode in ('base', 'CD1'):
            pair = [r for r in traces if r['seed'] == seed and r['mode'] == mode]
            assert len(pair) == 2 and pair[0]['vector_trace']['sha256'] == pair[1]['vector_trace']['sha256']
    allocator = load(root/('allocator' if version == '1' else 'allocator-v2')/'summary.json'); assert allocator['complete']
    for row in allocator['runs']:
        row['audit'] = audit(row['output']); assert row['audit'] == baseline[(1001, row['mode'])]
    controlled = []
    for seed in (1001, 1010, 1020):
        for short, mode in (('base', 'base'), ('cd1', 'CD1')):
            name = f'notrim-{"deep" if version == "1" else "v2"}-{seed}-{short}'
            path = root/name
            a = audit(path); assert a == baseline[(seed, mode)]
            tpath = root/(name+'-timing.json')
            t = load(tpath); regions = t['jobs'][0]['regions']
            controlled.append({'seed': seed, 'mode': mode, 'audit': a, 'timing_sha256': digest(tpath),
                               'resource': (root/(name+'.time')).read_text(),
                               'breakdown': breakdown(regions), 'regions': regions})
    replay = []
    for i in range(3):
        for mode in ('base', 'cd1'):
            replay_root = root if version == '1' else root/'replay-v2'
            obj = load(replay_root/f'replay-{i}-{mode}.json')
            assert obj['affinity'] == [compare['cpu']] and len(obj['rows']) == 9
            replay.append({'cycle': i, 'mode': mode, **obj})
    for mode in ('base', 'cd1'):
        sources = [r for r in replay if r['mode'] == mode]
        for idx in range(9):
            assert len({r['rows'][idx]['response_jac_sha256'] for r in sources}) == 1
    result = {'comparison_metadata': {k: v for k, v in compare.items() if k != 'runs'},
              'runs': runs, 'traces': traces, 'allocator': allocator, 'controlled_deep': controlled,
              'replay': replay, 'method': 'other = inclusive parent minus listed non-overlapping direct children; negative retained'}
    Path(output).write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    assert not Path(sys.argv[2]).exists(); main(*sys.argv[1:])
