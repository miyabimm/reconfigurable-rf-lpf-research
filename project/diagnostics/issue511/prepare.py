#!/usr/bin/env python3
"""Issue 511 RF-forward-free input generation and four-Plan preflight.

Writes only to a new system-temporary directory supplied by the caller. No
solver or RF response is evaluated. A failed assertion means STOP, no retry.
"""
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from lpf.minimax_profile import load_minimax_profile
from lpf.search.development_plan import freeze_run
from lpf.search.proposals import definition_from_data
from lpf.search.plan import Loader
from lpf.search.starts import generate_for_definition
from lpf.search.storage import sha

FTOL = {'A': 1e-8, 'B': 1e-7, 'C': 1e-6, 'D': 1e-5}
EXPECTED = {'rf_samples': 140009520, 'rf_forwards': 2000020, 'independent_mna_samples': 40}

def write(path, obj):
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n')

def main(out):
    assert all(os.environ.get(k) == '1' for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'))
    out = Path(out).resolve()
    assert out.parent == Path('/tmp').resolve() and not out.exists()
    profile = load_minimax_profile('RF-T010', root=ROOT, allow_trial=True)
    assert profile.fingerprint == 'd50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417'
    assert profile.base_sha256 == 'e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532'
    definition_data = json.loads((ROOT/'project/diagnostics/issue361/definition.json').read_bytes())
    assert sha(definition_data) == 'bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068'
    definition = definition_from_data(definition_data)
    policy = json.loads(profile.base_json)
    with (ROOT/'project/diagnostics/issue465/paired.csv').open() as f:
        previous = {int(r['seed']): r['new_initial_sha'] for r in csv.DictReader(f)}
    assert set(previous) == set(range(1001, 1021))
    records = {s: generate_for_definition(definition, policy, s) for s in previous}
    assert all(records[s]['vector_sha256'] == previous[s] and len(records[s]['vector']) == 25 for s in previous)
    base = json.loads((ROOT/'project/diagnostics/issue470/config.json').read_text())
    plans = []
    inputs = []
    for run_index in range(4):
        config = copy.deepcopy(base)
        config['seeds'] = list(range(1001 + 5*run_index, 1006 + 5*run_index))
        config['budget'] = EXPECTED.copy()
        config['arms'] = []
        order = list(FTOL)[run_index:] + list(FTOL)[:run_index]
        for name in order:
            step = copy.deepcopy(base['arms'][0]['steps'][0])
            step.update(solver='trf', options={'max_evaluations': 100000, 'restart_sigma': .1,
                                               'ftol': FTOL[name], 'x_scale': 1.0})
            config['arms'].append({'name': name, 'steps': [step]})
        starts = {str(s): {name: {k: records[s][k] for k in ('vector', 'vector_sha256')}
                           for name in order} for s in config['seeds']}
        config_text = yaml.safe_dump(config, sort_keys=False)
        parsed = yaml.load(config_text, Loader=Loader)
        assert parsed == config and all(type(a['steps'][0]['options']['ftol']) is float for a in parsed['arms'])
        plan, _, _, _, bounds = freeze_run(parsed, starts, root=ROOT, spot_checks={'terminal': [0, 111]},
                                            search_bounds=None, checkpoint_interval=1000)
        data = plan.data
        assert len(bounds) == 25 and all(lo < hi for lo, hi in bounds)
        assert len(data['jobs']) == 20
        assert len(data['grids']['terminal']['frequency_hz']) == 476
        assert all(len(data['grids'][name+'/search']['frequency_hz']) == 70 for name in order)
        for grid in data['grids'].values():
            assert set(grid['setting']) == set(range(6)) and set(grid['segment']) == set(range(28))
        rf = data['rf_profile']
        assert rf['bands_sha256'] == '1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe'
        for side, expected in (('input', 'ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945'),
                               ('output', 'b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da')):
            item = rf['external_s2p'][side]
            assert item['sha256'] == hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest() == expected
        assert all(j['reservation'] == {'rf_samples': 7000476, 'rf_forwards': 100001,
                                        'independent_mna_samples': 2} for j in data['jobs'])
        assert {k: sum(j['reservation'][k] for j in data['jobs']) for k in EXPECTED} == EXPECTED
        assert data['rf_profile']['effective_sha256'] == profile.fingerprint
        plans.append({'plan_sha256': plan.sha256, 'order': order, 'seeds': config['seeds'],
                      'budget': EXPECTED, 'plan': data})
        inputs.append((config_text, starts))
    # No output at all until all starts and all four frozen plans have passed.
    out.mkdir()
    for i, (config_text, starts) in enumerate(inputs, 1):
        (out/f'config-{i}.yaml').write_text(config_text)
        write(out/f'starts-{i}.json', starts)
        plans[i-1]['config_raw_sha256'] = hashlib.sha256((out/f'config-{i}.yaml').read_bytes()).hexdigest()
        plans[i-1]['starts_raw_sha256'] = hashlib.sha256((out/f'starts-{i}.json').read_bytes()).hexdigest()
    write(out/'preflight.json', {'issue': 511, 'rf_forwards': 0, 'records': records, 'runs': plans})
    print(json.dumps({'status': 'PASS', 'rf_forwards': 0, 'starts_matched': len(records),
                      'plans': [p['plan_sha256'] for p in plans], 'output': str(out)}, indent=2))

if __name__ == '__main__':
    main(sys.argv[1])
