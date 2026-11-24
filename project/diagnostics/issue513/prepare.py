#!/usr/bin/env python3
"""Issue 513: freeze calibration or comparison inputs without RF evaluations."""
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
from lpf.minimax_profile import load_minimax_profile
from lpf.search.development_plan import freeze_run
from lpf.search.plan import Loader
from lpf.search.proposals import definition_from_data
from lpf.search.starts import generate_for_definition
from lpf.search.storage import sha

COSTS = ('rf_samples', 'rf_forwards', 'independent_mna_samples')

def main(out, mode, n):
    assert all(os.environ.get(k) == '1' for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'))
    out = Path(out).resolve()
    assert out.parent == Path('/tmp').resolve() and not out.exists()
    assert mode in ('calibration', 'comparison') and 10000 <= n <= 140000
    profile = load_minimax_profile('RF-T010', root=ROOT, allow_trial=True)
    assert profile.fingerprint == 'd50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417'
    assert profile.base_sha256 == 'e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532'
    definition_data = json.loads((ROOT/'project/diagnostics/issue361/definition.json').read_bytes())
    assert sha(definition_data) == 'bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068'
    definition = definition_from_data(definition_data)
    with (ROOT/'project/diagnostics/issue465/paired.csv').open() as f:
        previous = {int(r['seed']): r['new_initial_sha'] for r in csv.DictReader(f)}
    with (ROOT/'project/diagnostics/issue511/paired.csv').open() as f:
        other = {int(r['seed']): r['initial_sha'] for r in csv.DictReader(f)}
    assert set(previous) == set(other) == set(range(1001, 1021))
    records = {s: generate_for_definition(definition, json.loads(profile.base_json), s) for s in previous}
    assert all(records[s]['vector_sha256'] == previous[s] == other[s] and len(records[s]['vector']) == 25 for s in previous)
    groups = [([1013], ['H0', 'H1', 'T'])] if mode == 'calibration' else [
        (list(range(1001, 1008)), ['H0', 'H1', 'T']),
        (list(range(1008, 1015)), ['H1', 'T', 'H0']),
        (list(range(1015, 1021)), ['T', 'H0', 'H1'])]
    base = json.loads((ROOT/'project/diagnostics/issue470/config.json').read_text())
    plans, inputs = [], []
    per_seed = {'rf_samples': 70*(2*(n+24)+5000)+3*476,
                'rf_forwards': 2*(n+24)+5000+3, 'independent_mna_samples': 6}
    for seeds, order in groups:
        config = copy.deepcopy(base)
        config['seeds'] = seeds
        config['budget'] = {k: per_seed[k]*len(seeds) for k in COSTS}
        config['arms'] = []
        for arm in order:
            step = copy.deepcopy(base['arms'][0]['steps'][0])
            if arm == 'T':
                step.update(solver='trf', options={'max_evaluations': 5000, 'restart_sigma': .1, 'ftol': 1e-6, 'x_scale': 1.0})
            else:
                opts = {'max_search_forwards': n, 'restart_sigma': .1}
                if arm == 'H1': opts['ftol'] = 1e-7
                step.update(solver='hybrid', options=opts)
            config['arms'].append({'name': arm, 'steps': [step]})
        starts = {str(s): {a: {k: records[s][k] for k in ('vector', 'vector_sha256')} for a in order} for s in seeds}
        text = yaml.safe_dump(config, sort_keys=False)
        parsed = yaml.load(text, Loader=Loader)
        assert parsed == config and type(parsed['arms'][order.index('H1')]['steps'][0]['options']['ftol']) is float
        plan, _, _, _, bounds = freeze_run(parsed, starts, root=ROOT, spot_checks={'terminal': [0, 111]}, search_bounds=None, checkpoint_interval=1000)
        data = plan.data
        assert len(bounds) == 25 and all(lo < hi for lo, hi in bounds)
        assert len(data['jobs']) == 3*len(seeds) and len(data['grids']['terminal']['frequency_hz']) == 476
        assert all(len(data['grids'][a+'/search']['frequency_hz']) == 70 for a in order)
        for grid in data['grids'].values():
            assert set(grid['setting']) == set(range(6)) and set(grid['segment']) == set(range(28))
        rf = data['rf_profile']
        assert rf['effective_sha256'] == profile.fingerprint
        assert rf['bands_sha256'] == '1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe'
        for side, expected in (('input', 'ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945'), ('output', 'b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da')):
            item = rf['external_s2p'][side]
            assert item['sha256'] == hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest() == expected
        for job in data['jobs']:
            cap = 5000 if job['arm'] == 'T' else n+24
            assert job['reservation'] == {'rf_samples': 70*cap+476, 'rf_forwards': cap+1, 'independent_mna_samples': 2}
        assert {k: sum(j['reservation'][k] for j in data['jobs']) for k in COSTS} == config['budget']
        plans.append({'plan_sha256': plan.sha256, 'order': order, 'seeds': seeds, 'budget': config['budget'], 'plan': data})
        inputs.append((text, starts))
    out.mkdir()
    for i, (text, starts) in enumerate(inputs, 1):
        (out/f'config-{i}.yaml').write_text(text)
        (out/f'starts-{i}.json').write_text(json.dumps(starts, indent=2, allow_nan=False)+'\n')
        for kind in ('config', 'starts'):
            suffix = 'yaml' if kind == 'config' else 'json'
            plans[i-1][kind+'_raw_sha256'] = hashlib.sha256((out/f'{kind}-{i}.{suffix}').read_bytes()).hexdigest()
    (out/'preflight.json').write_text(json.dumps({'issue': 513, 'mode': mode, 'N': n, 'rf_forwards': 0,
                                                  'per_seed': per_seed, 'records': records, 'runs': plans}, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'status': 'PASS', 'mode': mode, 'N': n, 'rf_forwards': 0, 'starts_matched': len(records),
                      'plans': [p['plan_sha256'] for p in plans], 'per_seed': per_seed, 'output': str(out)}, indent=2))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]))
