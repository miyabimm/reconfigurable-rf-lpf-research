#!/usr/bin/env python3
"""Generate frozen CLI config/starts only; no runner or search is invoked."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
from lpf.minimax_profile import load_minimax_profile
from lpf.search.proposals import definition_from_data
from lpf.search.starts import generate_for_definition
from lpf.search.storage import sha


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('out', type=Path)
    parser.add_argument('--budget', type=int, required=True)
    args = parser.parse_args()
    assert args.budget > 0 and not args.out.exists()
    args.out.mkdir(parents=True)
    profile = load_minimax_profile('RF-T010', root=ROOT, allow_trial=True)
    assert profile.fingerprint == 'd50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417'
    definition = json.loads((ROOT/'project/diagnostics/issue361/definition.json').read_text())
    assert sha(definition) == 'bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068'
    with (ROOT/'project/diagnostics/issue513/paired.csv').open() as f:
        expected = {int(r['seed']): r['initial_sha'] for r in csv.DictReader(f)}
    assert set(expected) == set(range(1001, 1021))
    manifest = {'budget': args.budget, 'rf_profile_sha256': profile.fingerprint, 'seeds': {}}
    for seed in range(1001, 1021):
        record = generate_for_definition(definition_from_data(definition), json.loads(profile.base_json), seed)
        assert record['vector_sha256'] == expected[seed]
        config = json.loads((ROOT/'project/diagnostics/issue470/config.json').read_text())
        config['seeds'] = [seed]
        config['arms'][0]['steps'][0].update(solver='trf', options=dict(max_evaluations=args.budget,
            restart_sigma=.1, ftol=1e-6, x_scale=1.))
        config['budget'] = dict(rf_samples=70*args.budget+476, rf_forwards=args.budget+1, independent_mna_samples=2)
        starts = {str(seed): {'baseline': {k: record[k] for k in ('vector', 'vector_sha256')}}}
        paths = []
        for kind, data in (('config', config), ('starts', starts)):
            path = args.out/f'{seed}-{kind}.json'
            path.write_text(yaml.safe_dump(data, sort_keys=False) if kind == 'config'
                            else json.dumps(data, indent=2)+'\n')
            paths.append(hashlib.sha256(path.read_bytes()).hexdigest())
        manifest['seeds'][str(seed)] = dict(config_sha256=paths[0], starts_sha256=paths[1],
                                             vector_sha256=record['vector_sha256'])
    (args.out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')


if __name__ == '__main__':
    main()
