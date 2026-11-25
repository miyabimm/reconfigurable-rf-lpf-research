#!/usr/bin/env python3
"""Compact completed #519 measurements; input /tmp directories remain untouched."""
import json
from pathlib import Path
import statistics
import sys


def main(kernel, numerics, runner, trace, output):
    k=json.loads(Path(kernel).read_text()); n=json.loads(Path(numerics).read_text())
    r=json.loads((Path(runner)/'summary.json').read_text()); t=json.loads((Path(trace)/'summary.json').read_text())
    assert len(k['rows'])==9 and len(r['runs'])==54 and len(r['warmups'])==12 and len(t['runs'])==12
    result={'kernel':k,'numerics':n,'metadata':r['metadata'],'inputs':r['inputs'],
            'warmups':r['warmups'],'trace':t['runs'],'runs':[],'cases':{},'pairs':[]}
    for x in r['runs']:
        step=x['step']; terminal=x['terminal']; response=terminal['response']; grid=response['grid']
        # Reconstruct finite-grid worst IL by segment; no frequency gaps are bridged.
        intervals=[]
        for seg in range(28):
            idx=[i for i,s in enumerate(grid['segment']) if s==seg]
            vals=[response['il_db'][i] for i in idx]
            intervals.append({'segment':seg,'min_il_db':min(vals),'max_il_db':max(vals)})
        result['runs'].append({'seed':x['seed'],'comparison':x['comparison'],'pair':x['pair'],'mode':x['mode'],
            'wall_s':x['wall_s'],'cpu_s':x['cpu_s']})
        case={'status':x['status'],'actual':x['actual'],
            'objective':step['solver_result']['objective'],'selected_vector':step['solver_result']['x'],
            'stop_reason':step['stop_reason'],'local_runs':step['local_runs'],'restart_count':step['restart_count'],
            'nfev':sum(q['scipy_nfev'] for q in step['local_run_details']),
            'njev':sum(q['scipy_njev'] for q in step['local_run_details']),
            'terminal_vector_sha256':terminal['vector_sha256'],'terminal_max_margin_db':terminal['terminal_signed_max_margin_db'],
            'intervals':intervals,'performance_feasible':terminal['performance_feasible'],
            'external_passivity':terminal['external_passivity'],'power_balance':terminal['power_balance'],
            'physical_component_policy_pass':terminal['physical']['component_policy_pass'],
            'physical_min_L_eigenvalue_H':terminal['physical']['min_L_eigenvalue_H'],
            'independent':terminal['independent'],'checkpoints':x['checkpoints']}
        key=f"{x['seed']}-{x['mode']}"
        if key in result['cases']:
            assert result['cases'][key] == case
        else:
            result['cases'][key]=case
    for seed in (1001,1010,1020):
        for mode in ('A','B','AB'):
            rr=[x for x in result['runs'] if x['seed']==seed and x['comparison']==mode]
            diffs=[]
            for pair in range(3):
                old=next(x for x in rr if x['mode']=='base' and x['pair']==pair)
                new=next(x for x in rr if x['mode']==mode and x['pair']==pair)
                diffs.append(new['wall_s']-old['wall_s'])
            result['pairs'].append({'seed':seed,'comparison':mode,'paired_wall_difference_s':diffs,
                                    'median_s':statistics.median(diffs),'range_s':[min(diffs),max(diffs)]})
    Path(output).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')

if __name__=='__main__': main(*sys.argv[1:])
