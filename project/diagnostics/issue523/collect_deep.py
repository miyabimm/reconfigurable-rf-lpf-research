#!/usr/bin/env python3
"""Preserve every observed deep region and non-overlapping per-run remainders."""
import hashlib, json, sys
from pathlib import Path

out = Path(sys.argv[-1]); assert not out.exists()
records=[]
for directory in map(Path, sys.argv[1:-1]):
    info=json.loads((directory/'summary.json').read_text())
    for run in info['runs']:
        if run['level'] != 'deep': continue
        path=Path(run['timing'])
        if not path.exists():
            records.append({'mode':run['mode'],'phase':run['phase'],'cycle':run['cycle'],'seed':run['seed'],'timing_missing':True})
            continue
        raw=path.read_bytes(); timing=json.loads(raw); regions=timing['jobs'][0]['regions']
        prefix='baseline/search/rf/'
        groups=['decode','matrices','node_admittance','jac_forward/reorder','jac_forward/schur_solve','jac_forward/schur_update',
                'jac_forward/y_to_s_build','jac_forward/y_to_s_solve','jac_forward/cascade_first','jac_forward/cascade_second',
                'power_response','jac_sensitivity/y_to_s','jac_sensitivity/cascade_first','jac_sensitivity/cascade_second',
                'jac_sensitivity/wave','jac_sensitivity/il','jac_sensitivity/freeze']
        if run['mode']=='base': groups += ['node_jacobian','jac_sensitivity/reorder','jac_sensitivity/schur']
        else: groups += ['jac_sensitivity/lift','port_jacobian','jac_sensitivity/restore']
        total=regions['baseline/search/rf_evaluate']['wall_ns']
        other=total-sum(regions[prefix+k]['wall_ns'] for k in groups)
        port_other=None
        if prefix+'port_jacobian/l_projection' in regions:
            child=['schema','dh','hb','inductor_solve','l_projection','c_projection','assemble','finite']
            port_other=regions[prefix+'port_jacobian']['wall_ns']-sum(regions[prefix+'port_jacobian/'+c]['wall_ns'] for c in child)
        records.append(dict(directory=str(directory),mode=run['mode'],phase=run['phase'],cycle=run['cycle'],seed=run['seed'],
                            timing_sha256=hashlib.sha256(raw).hexdigest(), plan_sha256=timing['plan_sha256'],source_sha256=timing['source_sha256'],
                            rf_nonoverlap_groups=groups,rf_other_wall_ns=other,port_other_wall_ns=port_other,regions=regions))
out.write_text(json.dumps(records,separators=(',',':'),allow_nan=False)+'\n')
