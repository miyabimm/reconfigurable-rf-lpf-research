#!/usr/bin/env python3
"""Compact fixed-commit I2/I3 runs, retaining per-vector times and deep regions."""
import hashlib, json, statistics, sys
from pathlib import Path
import numpy as np
p,out=map(Path,sys.argv[1:]); assert not out.exists()
reference=np.load(p/'i2-0.npz'); result={'runs':[]}
for mode in ('i2','i3'):
    for path in sorted(p.glob(mode+'-*.json')):
        data=json.loads(path.read_text()); values=np.load(path.with_suffix('.npz')); errors={}
        for key in reference.files:
            a,b=reference[key],values[key]
            np.testing.assert_allclose(a,b,rtol=1e-11,atol=1e-11)
            field=key.rsplit('-',1)[-1]; errors[field]=max(errors.get(field,0.),float(np.max(np.abs(a-b))))
        rows=[]
        for r in data['rows']:
            regions=r['deep']; prefix='search/rf/'
            relevant={k:v for k,v in regions.items() if k.startswith(prefix+'port_jacobian') or k.startswith(prefix+'jac_sensitivity/')}
            rows.append({k:r[k] for k in ('seed','vector','vector_sha256','plan_sha256','wall_ns','cpu_ns','deep_wall_ns','deep_cpu_ns')} | {'deep':relevant})
        result['runs'].append({'mode':mode,'process':path.stem,'raw_json_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
             'raw_npz_sha256':hashlib.sha256(path.with_suffix('.npz').read_bytes()).hexdigest(),
             **{k:data[k] for k in ('commit','model_import','affinity','threads','python','numpy','vectors_sha256','repetitions','deep_repetitions','peak_rss_kib')},
             'max_abs_vs_i2':errors,'rows':rows})
out.write_text(json.dumps(result,separators=(',',':'),allow_nan=False)+'\n')
