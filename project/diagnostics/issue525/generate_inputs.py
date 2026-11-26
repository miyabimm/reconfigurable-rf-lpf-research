#!/usr/bin/env python3
"""Freeze and preflight the two Issue 525 inputs; no RF forward is run."""
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from lpf.minimax_profile import load_minimax_profile
from lpf.search.component_constraints import physical_bounds, validate_search_box
from lpf.search.development_plan import freeze_run
from lpf.search.plan import Loader
from lpf.search.proposals import definition_from_data
from lpf.search.starts import generate_for_definition, IllegalStart
from lpf.search.storage import sha

SEEDS = list(range(1001, 1021))
PER_JOB = {'rf_forwards': 5001, 'rf_samples': 350476, 'independent_mna_samples': 2}

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main(out):
    out = Path(out).resolve()
    if out.exists():
        raise ValueError('Output already exists')
    out.mkdir(parents=True)
    profile = load_minimax_profile('RF-T010', root=ROOT, allow_trial=True)
    assert profile.fingerprint == 'd50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417'
    definition_data = json.loads((ROOT / 'project/diagnostics/issue361/definition.json').read_text())
    assert sha(definition_data) == 'bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068'
    definition = definition_from_data(definition_data)
    policy = json.loads(profile.base_json)
    model = profile.build_model(definition)
    a = np.asarray(physical_bounds(definition, model.schema, policy), dtype=float)
    b = a.copy()
    assert definition.inductor_types == ('LQP02HV',) * 4
    assert definition.fixed_c_types == ('GJM01', 'GJM01', 'GJM01', 'PCB_PATTERN_C')
    for i in range(len(definition.inductor_types)):
        b[i, 1] = min(b[i, 1], 20.)
    for i, kind in enumerate(definition.fixed_c_types, len(definition.inductor_types)):
        if kind == 'GJM01':
            b[i, 1] = min(b[i, 1], 10.)
    validate_search_box(b, a)
    changed = np.flatnonzero(np.any(a != b, axis=1)).tolist()
    assert a.shape == (25, 2) and changed == list(range(7))
    assert np.array_equal(a[:, 0], b[:, 0]) and np.all(a[:, 1] > a[:, 0])
    with (ROOT / 'project/diagnostics/issue513/paired.csv').open() as f:
        expected = {int(r['seed']): r['initial_sha'] for r in csv.DictReader(f)}
    assert set(expected) == set(SEEDS)
    starts = {'baseline': {}, 'limited': {}}
    try:
        for seed in SEEDS:
            records = [generate_for_definition(definition, policy, seed, bounds=box) for box in (a, b)]
            assert records[0]['vector_sha256'] == expected[seed]
            xa, xb = (np.asarray(r['vector']) for r in records)
            np.testing.assert_allclose((xa-a[:, 0])/(a[:, 1]-a[:, 0]), (xb-b[:, 0])/(b[:, 1]-b[:, 0]), rtol=0, atol=2e-15)
            np.testing.assert_array_equal(xa[7:], xb[7:])
            for name, rec in zip(starts, records, strict=True):
                starts[name][str(seed)] = {'baseline': {k: rec[k] for k in ('vector', 'vector_sha256')}}
    except IllegalStart as exc:
        (out / 'illegal-start.json').write_text(json.dumps(exc.record, indent=2) + '\n')
        raise
    config = json.loads((ROOT / 'project/diagnostics/issue470/config.json').read_text())
    config['seeds'] = SEEDS
    config['budget'] = {k: 20*v for k, v in PER_JOB.items()}
    config['arms'][0]['steps'][0].update(solver='trf', options={'max_evaluations': 5000, 'restart_sigma': .1, 'ftol': 1e-6, 'x_scale': 1.0})
    config_text = yaml.safe_dump(config, sort_keys=False)
    parsed = yaml.load(config_text, Loader=Loader)
    assert parsed == config and type(parsed['arms'][0]['steps'][0]['options']['ftol']) is float
    manifest = {'profile_sha256': profile.fingerprint, 'definition_sha256': sha(definition_data), 'changed_indices': changed, 'per_job': PER_JOB, 'arms': {}}
    for name, box in (('baseline', a), ('limited', b)):
        plan, _, _, _, _ = freeze_run(parsed, starts[name], root=ROOT, spot_checks={'terminal': [0, 111]}, search_bounds=box.tolist(), checkpoint_interval=1000)
        data = plan.data
        assert len(data['jobs']) == 20 and all(j['reservation'] == PER_JOB for j in data['jobs'])
        for grid, n in (('baseline/search', 70), ('terminal', 476)):
            g = data['grids'][grid]
            assert len(g['frequency_hz']) == n and set(g['setting']) == set(range(6)) and set(g['segment']) == set(range(28))
        assert data['rf_profile']['bands_sha256'] == '1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe'
        for item in data['rf_profile']['external_s2p'].values():
            assert digest(ROOT / item['path']) == item['sha256']
        dest = out / name
        dest.mkdir()
        (dest / 'config.yaml').write_text(config_text)
        (dest / 'starts.json').write_text(json.dumps(starts[name], indent=2, allow_nan=False) + '\n')
        (dest / 'bounds.json').write_text(json.dumps(box.tolist(), indent=2, allow_nan=False) + '\n')
        manifest['arms'][name] = {'plan_sha256': plan.sha256, 'files': {p.name: digest(p) for p in dest.iterdir()}, 'starts': {s: v['baseline']['vector_sha256'] for s, v in starts[name].items()}, 'grid_sha256': {k: v['sha256'] for k, v in data['grids'].items()}, 'bounds_sha256': data['search_bounds_sha256']}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('PASS: preflight 40 starts, 2 plans, zero RF forwards:', out)

if __name__ == '__main__':
    main(sys.argv[1])
