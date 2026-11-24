#!/usr/bin/env python3
"""Collect verified issue 511 runs incrementally; no RF evaluations or retries."""
import csv
import json
from pathlib import Path
import statistics
import sys


def load(p):
    return json.loads(p.read_text())


def collect(tmp, out, count):
    preflight = load(tmp/'preflight.json')
    runs = [load(tmp/f'audit-{i}.json') for i in range(1, count+1)]
    assert [r['run'] for r in runs] == list(range(1, count+1))
    assert len({r['source_sha256'] for r in runs}) == 1
    for r in runs:
        i = r['run']
        assert r['plan_sha256'] == preflight['runs'][i-1]['plan_sha256']
        r['cli_exit'] = int((tmp/f'run-{i}-exit.txt').read_text())
        assert r['cli_exit'] in (0, 4)
        r['run_time'] = (tmp/f'run-{i}-time.txt').read_text().strip()
        r['start'] = (tmp/f'run-{i}-start.txt').read_text().strip()
        r['end'] = (tmp/f'run-{i}-end.txt').read_text().strip()
        r['load_start'] = (tmp/f'run-{i}-load-start.txt').read_text().strip()
        r['load_end'] = (tmp/f'run-{i}-load-end.txt').read_text().strip()
    # Full source identity is identical across runs; retain once.
    source = runs[0]['source']
    for r in runs:
        assert r.pop('source') == source
    plans = [{k: r[k] for k in ('plan_sha256', 'config_raw_sha256', 'starts_raw_sha256', 'order', 'seeds', 'budget')}
             for r in preflight['runs']]
    first = preflight['runs'][0]['plan']
    summary = dict(kind='issue511_ftol_5000_trial', state='completed' if count == 4 else 'partial',
        rf_forwards_preflight=0, environment=(tmp/'environment.txt').read_text(), source=source,
        source_sha256=runs[0]['source_sha256'], rf_profile=first['rf_profile'],
        definition_reference=first['config']['definition'], bounds=first['search_bounds'],
        bounds_sha256=first['search_bounds_sha256'], spot_checks=first['spot_checks'],
        checkpoint_interval=first['checkpoint_interval'], plans=plans, runs=runs)
    if out.exists():
        old = load(out)
        assert old['kind'] == summary['kind'] and old['source_sha256'] == summary['source_sha256']
        assert old['plans'] == plans and old['runs'] == runs[:len(old['runs'])]
    if count == 4:
        rows = [j for r in runs for j in r['jobs']]
        assert len(rows) == 80 and len({(j['seed'], j['arm']) for j in rows}) == 80
        byseed = {(j['seed'],j['arm']):j for j in rows}
        assert set(byseed) == {(s,a) for s in range(1001,1021) for a in 'ABCD'}
        paired = []
        for seed in range(1001,1021):
            jobs = [byseed[seed,a] for a in 'ABCD']
            assert len({j['initial_sha'] for j in jobs}) == 1
            assert all(j['initial_vector'] == jobs[0]['initial_vector'] for j in jobs)
            row = {'seed': seed, 'initial_sha':jobs[0]['initial_sha']}
            for arm,j in zip('ABCD',jobs,strict=True):
                row.update({f'{arm}_{key}':j[key] for key in ('J','finite_grid_pass','worst_il','min_h2','min_h3','search_objective','search_forwards','job_wall_s','local_runs','restart_count','stop_reason','converged','final_sha')})
                row[f'{arm}_delta_J_vs_A'] = j['J'] - jobs[0]['J']
            paired.append(row)
        stats = {}
        for arm in 'ABCD':
            jobs = [byseed[s,arm] for s in range(1001,1021)]
            d = [j['J']-byseed[j['seed'],'A']['J'] for j in jobs]
            vals = [j['J'] for j in jobs]
            stats[arm] = dict(J_sorted=sorted(vals), J_median=statistics.median(vals), J_min=min(vals), J_max=max(vals),
                pass_count=sum(j['finite_grid_pass'] for j in jobs), delta_median=statistics.median(d),
                improved=sum(x<0 for x in d), worsened=sum(x>0 for x in d), tied=sum(x==0 for x in d),
                wall_median_s=statistics.median(j['job_wall_s'] for j in jobs),
                wall_total_s=sum(j['job_wall_s'] for j in jobs),
                restart_median=statistics.median(j['restart_count'] for j in jobs),
                restart_total=sum(j['restart_count'] for j in jobs),
                search_forwards=sum(j['search_forwards'] for j in jobs))
        summary['statistics'] = stats
        csv_path = out.with_name('paired.csv')
        assert not csv_path.exists()
        with csv_path.open('x', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(paired[0]), lineterminator='\n')
            writer.writeheader(); writer.writerows(paired)
    temp = out.with_suffix('.json.tmp')
    assert not temp.exists()
    with temp.open('x') as f:
        json.dump(summary, f, indent=2, allow_nan=False); f.write('\n')
        f.flush()
        import os
        os.fsync(f.fileno())
    temp.replace(out)
    print(json.dumps({'state':summary['state'],'runs':count,'jobs':sum(len(r['jobs']) for r in runs)}))

if __name__ == '__main__':
    collect(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]))
