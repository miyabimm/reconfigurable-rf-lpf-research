#!/usr/bin/env python3
"""Create a seed-paired CSV from the independently audited compact JSON."""
import csv
import json
from pathlib import Path
import sys


def main(source, target):
    rows = json.loads(Path(source).read_text())['runs']
    grouped = {arm: {r['seed']: r for r in rows if r['condition'] == arm} for arm in ('baseline', 'limited')}
    assert all(set(r) == set(range(1001, 1021)) for r in grouped.values())
    out = []
    for seed in range(1001, 1021):
        a, b = (grouped[arm][seed] for arm in ('baseline', 'limited'))
        row = {'seed': seed}
        for key in ('terminal_J_db2', 'terminal_max_margin_db', 'worst_il_db', 'min_h2_db', 'min_h3_db', 'search_J_db2'):
            row[key+'_A'], row[key+'_B'] = a[key], b[key]
            row[key+'_B_minus_A'] = b[key]-a[key]
        for arm, data in (('A', a), ('B', b)):
            row['feasible_'+arm] = data['feasible']
            row['nfev_'+arm], row['njev_'+arm] = data['nfev'], data['njev']
            row['local_runs_'+arm], row['restarts_'+arm] = data['local_runs'], data['restarts']
            for count in range(1000, 5001, 1000):
                # Snapshot objective, not global best. A final best checkpoint may
                # share count 5000; retain only the first periodic observation.
                matches = [x['objective'] for x in data['checkpoints'] if x['forward_count'] == count]
                row[f'CP{count}_observation_{arm}'] = matches[0] if matches else None
                observed = [x['objective'] for x in data['checkpoints'] if x['forward_count'] <= count]
                row[f'CP{count}_best_saved_{arm}'] = min(observed) if observed else None
        out.append(row)
    target = Path(target)
    assert not target.exists()
    with target.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=out[0], lineterminator='\n')
        writer.writeheader(); writer.writerows(out)

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
