#!/usr/bin/env python3
"""Summarize audited CLI comparisons without selecting or dropping seeds."""
import json
from pathlib import Path
import sys
import numpy as np

METRICS = ('search_J', 'terminal_J', 'terminal_max_margin_db', 'worst_il_db', 'min_h2_db', 'min_h3_db',
           'nfev', 'njev', 'restarts', 'wall_s', 'cpu_s')


def stats(values):
    a = np.asarray(values, float)
    assert len(a) == 20 and np.isfinite(a).all()
    q = np.quantile(a, [0, .25, .5, .75, 1])
    return dict(min=float(q[0]), q1=float(q[1]), median=float(q[2]), q3=float(q[3]), max=float(q[4]), mean=float(a.mean()))


def main(calibration, quality, frozen, output):
    cal = json.loads(Path(calibration).read_text())
    qual = json.loads(Path(quality).read_text())
    frozen_data = json.loads(Path(frozen).read_text())
    assert cal['identities'] == qual['identities']
    assert len(cal['runs']) == 30 and len(qual['runs']) == 100 and qual['metadata']['frozen_budgets'] == frozen_data['budgets']
    rows = qual['runs']
    def select(phase, mode):
        values = sorted((r for r in rows if r['phase'] == phase and r['mode'] == mode), key=lambda r: r['seed'])
        assert [v['seed'] for v in values] == list(range(1001, 1021))
        return values
    baseline = select('fixed', 'base')
    scenarios = {}
    for phase, mode in [('fixed', 'base'), ('fixed', 'D1'), ('fixed', 'CD1'), ('time', 'D1'), ('time', 'CD1')]:
        values = select(phase, mode)
        for base, row in zip(baseline, values, strict=True):
            assert row['initial_sha256'] == base['initial_sha256'] and row['starts_sha256'] == base['starts_sha256']
            if phase == 'fixed':
                assert row['plan_sha256'] == base['plan_sha256'] and row['config_sha256'] == base['config_sha256']
        scenario = {'distribution': {key: stats([r[key] for r in values]) for key in METRICS},
                    'feasible_count': sum(r['feasible'] for r in values),
                    'independent_status': {s: sum(r['independent'] == s for r in values) for s in sorted({r['independent'] for r in values})},
                    'component_pass_count': sum(r['component_pass'] for r in values),
                    'positive_spd_count': sum(r['min_L_eigenvalue_H'] > 0 for r in values),
                    'passivity_status': {s: sum(r['external_passivity'] == s for r in values) for s in sorted({r['external_passivity'] for r in values})},
                    'power_status': {s: sum(r['power_balance'] == s for r in values) for s in sorted({r['power_balance'] for r in values})},
                    'stop_reasons': {s: sum(r['stop_reason'] == s for r in values) for s in sorted({r['stop_reason'] for r in values})}}
        if mode != 'base':
            scenario['paired'] = {}
            for key in METRICS:
                d = [r[key]-b[key] for r, b in zip(values, baseline, strict=True)]
                sign = 1 if key in ('min_h2_db', 'min_h3_db') else -1
                scenario['paired'][key] = {'candidate_minus_base': stats(d), 'per_seed': d,
                                           'better': sum(sign*x > 0 for x in d),
                                           'worse': sum(sign*x < 0 for x in d), 'equal': sum(x == 0 for x in d)}
        scenarios[phase+'-'+mode] = scenario
    source = {}
    for mode in ('base', 'D1', 'CD1'):
        values = {r['source_sha256'] for r in cal['runs']+qual['runs'] if r['mode'] == mode}
        assert len(values) == 1
        source[mode] = values.pop()
    result = {'calibration_metadata': cal['metadata'], 'quality_metadata': qual['metadata'],
              'identities': qual['identities'], 'frozen': frozen_data, 'source_sha256': source,
              'calibration_runs': cal['runs'], 'quality_runs': rows, 'scenarios': scenarios,
              'audit': 'CLI plan, input/final vector, receipt files, grid, budget and accounting checked; validations reported, not assumed'}
    Path(output).write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    assert not Path(sys.argv[4]).exists()
    main(*sys.argv[1:])
