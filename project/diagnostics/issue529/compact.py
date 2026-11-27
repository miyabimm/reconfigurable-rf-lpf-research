#!/usr/bin/env python3
"""Create compact, reproducible 49-job observations from the audited records."""
import gzip
import json
from pathlib import Path
import sys

OUT = Path(__file__).resolve().parent

def build():
    compact = {}
    for stage in (1, 2, 3):
        path = OUT/f'stage{stage}-audit.json'
        if path.exists():
            audit = json.loads(path.read_text())
        else:
            with gzip.open(path.with_suffix('.json.gz'), 'rt') as stream:
                audit = json.load(stream)
        rows = []
        for row in audit['rows']:
            r = {k: v for k, v in row.items() if k not in ('raw', 'checkpoints', 'local_run_details')}
            r['checkpoint_count'] = len(row['checkpoints'])
            r['local_run_wall_seconds'] = sum(run['wall_s'] for run in row['local_run_details'])
            rows.append(r)
        compact[str(stage)] = {'plan_sha256': audit['plan_sha256'],
                               'ranking': audit['ranking'], 'rows': rows}
    return compact

if __name__ == '__main__':
    sys.stdout.write(json.dumps(build(), indent=2, allow_nan=False)+'\n')
