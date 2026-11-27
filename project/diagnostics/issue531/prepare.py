#!/usr/bin/env python3
"""Freeze Issue 531 inputs from the immutable Issue 529 commit; no RF forwards."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
from lpf.search.storage import vector_sha

COMMIT = '0f7b1097217f913cfbaaf77b4fb1c0ddbad88bd3'
PREFIX = 'project/diagnostics/issue529/'
def source(name):
    return subprocess.check_output(['git', 'show', f'{COMMIT}:{PREFIX}{name}'], cwd=ROOT)
def digest(data):
    return hashlib.sha256(data).hexdigest()
def main():
    compact, oldstarts = (json.loads(source(name)) for name in ('compact-results.json', 'stage2-inputs/starts.json'))
    config = yaml.safe_load(source('stage2-inputs/config.yaml'))
    bounds = json.loads(source('stage2-inputs/bounds.json'))
    seeds = [2008, 2009, 2031, 2015, 2025, 2038, 2001, 2037]
    assert compact['1']['ranking'][:8] == config['seeds'] == seeds
    rows = {r['seed']: r for r in compact['1']['rows']}
    starts = {}
    reference = json.loads(source('reference-compact.json'))['vector_sha256']
    for seed in seeds:
        row = rows[seed]
        start = oldstarts[str(seed)]['baseline']
        assert row['final_vector'] == start['vector']
        assert row['final_sha256'] == start['vector_sha256'] == vector_sha(start['vector']) != reference
        starts[str(seed)] = {'baseline': start}
    config['budget'] = dict(rf_samples=11203808, rf_forwards=160008, independent_mna_samples=16)
    config['arms'][0]['steps'][0]['options']['max_evaluations'] = 20000
    assert len(bounds) == 25 and bounds[:4] == [[0.4, 27.0]] * 4 and bounds[4:7] == [[0.1, 10.0]] * 3
    dest = OUT / 'inputs'
    dest.mkdir(exist_ok=False)
    files = {'config.yaml': yaml.safe_dump(config, sort_keys=False),
             'starts.json': json.dumps(starts, indent=2, allow_nan=False)+'\n',
             'bounds.json': json.dumps(bounds, indent=2, allow_nan=False)+'\n'}
    for name, text in files.items():
        (dest/name).write_text(text)
    manifest = {'source_commit': COMMIT, 'source_sha256': {name: digest(source(name)) for name in ('compact-results.json', 'stage2-inputs/starts.json', 'stage2-inputs/config.yaml', 'stage2-inputs/bounds.json', 'reference-compact.json')},
                'files_sha256': {name: digest((dest/name).read_bytes()) for name in files},
                'selected': [{'seed': s, 'job_id': rows[s]['job_id'], 'vector_sha256': rows[s]['final_sha256']} for s in seeds],
                'spot_checks': {'terminal': [0, 111]}, 'checkpoint_interval_forwards': 1000}
    (dest/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print('PASS: fixed commit ranking, vectors, hashes, Stage 2 starts, reference exclusion')
if __name__ == '__main__': main()
