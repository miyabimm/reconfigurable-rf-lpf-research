#!/usr/bin/env python3
"""Generate #533 inputs from the pinned #529 evidence; no RF evaluations."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / 'inputs'
sys.path.insert(0, str(ROOT / 'src'))
from lpf.search.storage import vector_sha

COMMIT = '0f7b1097217f913cfbaaf77b4fb1c0ddbad88bd3'
PREFIX = 'project/diagnostics/issue529/'
NAMES = ('compact-results.json', 'stage2-inputs/config.yaml', 'stage2-inputs/bounds.json', 'reference-compact.json')
def source(name):
    return subprocess.check_output(['git', 'show', f'{COMMIT}:{PREFIX}{name}'], cwd=ROOT)
def digest(data): return hashlib.sha256(data).hexdigest()

def main():
    compact, config, bounds, reference = json.loads(source(NAMES[0])), yaml.safe_load(source(NAMES[1])), json.loads(source(NAMES[2])), json.loads(source(NAMES[3]))
    seeds = [2015, 2008, 2037, 2031, 2001, 2038, 2025, 2009]
    assert compact['2']['ranking'] == seeds
    rows = {r['seed']: r for r in compact['2']['rows']}
    starts = {}
    for seed in seeds:
        row = rows[seed]
        vector = row['final_vector']
        assert len(vector) == 25 and vector_sha(vector) == row['final_sha256'] != reference['vector_sha256']
        assert all(lo <= v <= hi for v, (lo, hi) in zip(vector, bounds, strict=True))
        starts[str(seed)] = {'baseline': {'vector': vector, 'vector_sha256': row['final_sha256']}}
    assert len(bounds) == 25 and bounds[:4] == [[0.4, 27.0]] * 4 and bounds[4:7] == [[0.1, 10.0]] * 3
    OUT.mkdir(exist_ok=False)
    (OUT/'starts.json').write_text(json.dumps(starts, indent=2, allow_nan=False)+'\n')
    (OUT/'bounds.json').write_text(json.dumps(bounds, indent=2, allow_nan=False)+'\n')
    config['seeds'] = seeds
    config['budget'] = dict(rf_samples=5603808, rf_forwards=80008, independent_mna_samples=16)
    for i, (scale, ftol) in enumerate((s, f) for s in (1.0, 'jac') for f in (1e-6, 1e-8, 1e-10, None)):
        config['arms'][0]['steps'][0]['options'] = dict(max_evaluations=10000, ftol=ftol, x_scale=scale, restart_sigma=None)
        (OUT/f'A{i+1}.yaml').write_text(yaml.safe_dump(config, sort_keys=False))
    files = sorted(p for p in OUT.iterdir() if p.is_file())
    manifest = {'source_commit': COMMIT, 'source_sha256': {n: digest(source(n)) for n in NAMES},
                'files_sha256': {p.name: digest(p.read_bytes()) for p in files},
                'selected': [{'seed': s, 'job_id': rows[s]['job_id'], 'vector_sha256': rows[s]['final_sha256'], 'search_J_db2': rows[s]['search_J_db2'], 'terminal_max_margin_db': rows[s]['terminal_max_margin_db']} for s in seeds],
                'spot_checks': {'terminal': [0, 111]}, 'checkpoint_interval_forwards': 1000}
    (OUT/'manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False)+'\n')
    print('PASS pinned Stage 2 ranking, all 25 coordinates and vector SHA, bounds, reference exclusion')
if __name__ == '__main__': main()
