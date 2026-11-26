#!/usr/bin/env python3
"""Freeze approximate-time budgets from all nine paired calibration timings."""
import json
from pathlib import Path
import statistics
import sys

source, output = map(Path, sys.argv[1:])
assert not output.exists()
data = json.loads(source.read_text())
assert data['metadata']['complete']
runs = data['runs']
ratios, budgets = {}, {}
for mode in ('D1', 'CD1'):
    ratios[mode] = []
    for seed in (1001, 1010, 1020):
        for cycle in range(3):
            def get(arm):
                matches = [r for r in runs if r['phase'] == 'calibration' and r['seed'] == seed
                           and r['cycle'] == cycle and r['mode'] == arm]
                assert len(matches) == 1 and matches[0]['exit_code'] in (0, 4)
                return matches[0]
            ratios[mode].append(get('base')['wall_s']/get(mode)['wall_s'])
    budgets[mode] = int(round(5000*statistics.median(ratios[mode])/100)*100)
result = {'rule': 'nearest 100 to 5000 * median of nine same-seed/cycle base/candidate wall ratios',
          'calibration_file': str(source), 'ratios': ratios, 'budgets': budgets}
output.write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2))
