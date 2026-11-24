#!/usr/bin/env python3
"""Persist compact audited results after each completed run; no RF evaluations."""
import csv
import json
import os
from pathlib import Path
import statistics
import sys


def load(path): return json.loads(path.read_text())
def collect(tmp, calibration, output, count):
    preflight, cal = load(tmp/'preflight.json'), load(calibration/'audit-1.json')
    runs = [load(tmp/f'audit-{i}.json') for i in range(1, count+1)]
    assert preflight['mode'] == 'comparison' and 1 <= count <= 3
    assert all(r['source_sha256'] == cal['source_sha256'] for r in runs)
    for i, r in enumerate(runs, 1):
        assert r['run'] == i and r['plan_sha256'] == preflight['runs'][i-1]['plan_sha256']
        r['cli_exit'] = int((tmp/f'run-{i}-exit.txt').read_text())
        assert r['cli_exit'] in (0, 4)
        for key in ('time', 'start', 'end', 'load-start', 'load-end'):
            r[key.replace('-', '_')] = (tmp/f'run-{i}-{key}.txt').read_text().strip()
    source = cal['source']
    for r in runs: assert r.pop('source') == source
    first = preflight['runs'][0]['plan']
    plans = [{k: p[k] for k in ('plan_sha256', 'config_raw_sha256', 'starts_raw_sha256', 'order', 'seeds', 'budget')} for p in preflight['runs']]
    summary = dict(kind='issue513_hybrid_trf_trial', state='completed' if count == 3 else 'partial',
                   N=preflight['N'], rf_forwards_preflight=0, source=source,
                   source_sha256=cal['source_sha256'], environment=(calibration/'environment.txt').read_text(),
                   rf_profile=first['rf_profile'], definition_reference=first['config']['definition'],
                   bounds=first['search_bounds'], bounds_sha256=first['search_bounds_sha256'],
                   spot_checks=first['spot_checks'], checkpoint_interval=first['checkpoint_interval'],
                   calibration={'N': 15000, 'plan_sha256':cal['plan_sha256'], 'actual':cal['actual'],
                                'released':cal['released'], 'jobs':cal['jobs'],
                                'run_time':(calibration/'run-1-time.txt').read_text().strip(),
                                'cli_exit':int((calibration/'run-1-exit.txt').read_text()),
                                'basis':'round to nearest 1000 using T wall / mean H0,H1 wall * 15002; independent of quality'},
                   per_seed_reservation=preflight['per_seed'], plans=plans, runs=runs)
    if output.exists():
        old = load(output)
        assert old['kind'] == summary['kind'] and old['source_sha256'] == summary['source_sha256']
        assert old['plans'] == plans and old['runs'] == runs[:len(old['runs'])]
    if count == 3:
        jobs = [j for r in runs for j in r['jobs']]
        by = {(j['seed'], j['arm']):j for j in jobs}
        assert len(jobs) == len(by) == 60 and set(by) == {(s,a) for s in range(1001,1021) for a in ('H0','H1','T')}
        rows = []
        for seed in range(1001,1021):
            entries = [by[seed,a] for a in ('H0','H1','T')]
            assert len({j['initial_sha'] for j in entries}) == 1 and all(j['initial_vector'] == entries[0]['initial_vector'] for j in entries)
            row = dict(seed=seed, initial_sha=entries[0]['initial_sha'])
            for arm,j in zip(('H0','H1','T'), entries, strict=True):
                row.update({f'{arm}_{k}':j[k] for k in ('J','finite_grid_pass','worst_il','min_h2','min_h3','search_objective','search_forwards','job_wall_s','local_runs','restart_count','stop_reason','converged','final_sha')})
            for left,right in (('H1','H0'),('T','H1'),('T','H0')):
                row[f'{left}_minus_{right}_J'] = by[seed,left]['J']-by[seed,right]['J']
            rows.append(row)
        stats = {}
        def distribution(values):
            return dict(mean=statistics.mean(values), median=statistics.median(values), min=min(values), max=max(values), sorted=sorted(values))
        for arm in ('H0','H1','T'):
            js = [by[s,arm] for s in range(1001,1021)]
            stats[arm] = dict(J=distribution([j['J'] for j in js]), wall_s=distribution([j['job_wall_s'] for j in js]),
                              passes=sum(j['finite_grid_pass'] for j in js), search_forwards=sum(j['search_forwards'] for j in js))
        for left,right in (('H1','H0'),('T','H1'),('T','H0')):
            ds = [by[s,left]['J']-by[s,right]['J'] for s in range(1001,1021)]
            stats[f'{left}_minus_{right}'] = dict(delta_J=distribution(ds), improved=sum(x<0 for x in ds), worsened=sum(x>0 for x in ds), tied=sum(x==0 for x in ds))
        summary['statistics'] = stats
        path = output.with_name('paired.csv')
        assert not path.exists()
        with path.open('x', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n'); writer.writeheader(); writer.writerows(rows)
    temp = output.with_suffix('.json.tmp')
    assert not temp.exists()
    with temp.open('x') as f:
        json.dump(summary, f, indent=2, allow_nan=False); f.write('\n'); f.flush(); os.fsync(f.fileno())
    temp.replace(output)
    print(json.dumps({'state':summary['state'], 'runs':count, 'jobs':sum(len(r['jobs']) for r in runs)}))

if __name__ == '__main__': collect(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4]))
