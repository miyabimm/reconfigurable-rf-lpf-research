import json, hashlib
from pathlib import Path
import yaml
from lpf.search.storage import canonical
from lpf.search.plan import load_preflight
root=Path.cwd(); out=Path('/tmp/issue361-dev-7RxpB4OQ'); report=json.loads((out/'benchmark-preflight.json').read_text()); data=report['definition']
defpath=root/'.issue361-definition.json'
if defpath.exists(): raise RuntimeError('STOP existing definition file')
raw=(canonical(data)+'\n').encode(); defpath.write_bytes(raw)
ref=dict(path=defpath.name,source_sha256=hashlib.sha256(raw).hexdigest(),definition_sha256=report['definition_sha256'])
plans=[('pilot',list(range(1001,1003)),250000,220000,3000,1,[70000,140000,210000]),('main',list(range(1003,1009)),650000,575000,8000,2,[140000,280000,420000,560000]),('extension',list(range(1009,1013)),650000,575000,8000,2,[140000,280000,420000,560000])]
print('extension decision frozen: run only if pilot/main complete without numerical STOP and fewer than two seeds have strict-eligible terminal IL <= reference+0.05dB; otherwise not_started.')
for name,seeds,cap,step,evals,restarts,milestones in plans:
 config=dict(schema_version=2,rf=dict(constraint_id='RF-T008',allow_trial=True),objective='full_lpf',definition=ref,seeds=seeds,max_trial_requested_samples=cap,selection=dict(rule='mandatory_vmax_vsum_il_sha',top_k=1,max_candidates=4,points_per_interval=3),validation=dict(terminal_points=17,dense_points=1001,max_candidates=1,max_requested_samples=28028),anytime_samples=milestones,anytime_points_per_interval=3,arms=[dict(name='hybrid',max_requested_samples=cap,steps=[dict(name='coarse',solver='hybrid',aggregation='sum',points_per_interval=2,stop_points_per_interval=3,max_requested_samples=step,options=dict(maxiter=150,max_restarts=restarts,max_evaluations=evals,restart_sigma=0.1))])])
 path=out/(name+'.yaml'); path.write_text(yaml.safe_dump(config,sort_keys=False)); starts={str(s):{'vector':report['starts'][str(s)]['vector'],'vector_sha256':report['starts'][str(s)]['vector_sha256']} for s in seeds}; (out/(name+'-starts.json')).write_text(json.dumps(starts,indent=2)+'\n')
 p=load_preflight(path); (out/(name+'-plan.json')).write_text(p.frozen_json+'\n'); job=p.data['costs']['jobs']['hybrid']; grid=p.data['grids']['hybrid/coarse']; assert grid['requested_samples_per_forward']==70; print(name,'plan',p.sha256,'stage',step,'required',job['total_upper_reservation'],'cap',cap,'grid',grid['sha256'])
(out/'extension-decision.txt').write_text('Frozen before Pilot: run Extension only if Pilot and Main complete without numerical STOP and fewer than two Pilot+Main seeds have physical/SPD-valid terminal strict RF H2/H3 >= 30 dB and terminal IL <= benchmark terminal 17 point IL + 0.05 dB. Otherwise do not run Extension. Solver convergence recorded separately; no rounding.\n')
