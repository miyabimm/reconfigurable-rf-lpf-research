import json, hashlib, time, platform
from dataclasses import asdict
from pathlib import Path
import numpy as np
from lpf.search.proposals import definition_from_data
from lpf.search.storage import sha, vector_sha, plain
from lpf.constraint_versions import load_constraint, constraint_fingerprint
from lpf.search.starts import generate_for_definition
from lpf.search.component_constraints import validate_values
from lpf.search.performance import compile_requirements, build_evaluation_grid, evaluate_requirements
from lpf.rf_core.model import build_rf_model

root=Path.cwd(); out=Path('/tmp/issue361-dev-7RxpB4OQ')
checkpoint=root/'experiments/chatgpt_topology_search/runs/EXP-062/checkpoints/a6_best.json'
m=json.loads((root/'experiments/chatgpt_topology_search/runs/EXP-115/manifest.json').read_text())
c=json.loads(checkpoint.read_text()); data=m['search_scope']['input_source']['executable_plan']['definition']; d=definition_from_data(data)
assert sha(asdict(d)) == 'bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068'
t=c['topology']; assert data['inductor_tree']['edges']==t['L_edges']; assert data['capacitor_placement']['fixed_edges']==t['fixed_GJM_edges']+t['PCB_C_edges']; assert data['capacitor_placement']['variable_edges']==t['variable_C_edges']; assert data['capacitor_placement']['ic_fixed_edges']==t['IC_fixed_C_parallel_edges']
assert data['inductor_types']==[v['type'] for v in c['components'][:4]]; assert data['fixed_c_types']==['GJM01']*3+['PCB_PATTERN_C']; assert data['coupling_pairs']==[[0,1],[1,3],[3,2]] and data['physical_order']==[0,1,3,2]
x=c['vector']; fv=c['fixed_values']; cv=c['ic_variable_C_pf_by_setting']; assert x==fv['L_nH']+fv['GJM_C_pf']+fv['PCB_C_pf']+fv['k_signed']+fv['IC_fixed_C_pf']+sum([cv[k] for k in ['B71','B12','B28','B13+B14','B26','B8']],[])
for i,comp in enumerate(c['components'][:8]):
 assert comp.get('L_nH',comp.get('C_pF')) == x[i]
assert [v['k'] for v in c['couplings']]==fv['k_signed']
p=load_constraint('RF-T008',allow_trial=True); model=build_rf_model(d,p); physical=validate_values(d,model.schema,x,p)
assert physical['component_policy_pass'] and not physical['connection_role_evidence_incomplete']
req=compile_requirements(p,root/'rf/bands.csv','full_lpf'); g=build_evaluation_grid(req,17); tic=time.time(); r=model.evaluator(g).evaluate(x); a=plain(evaluate_requirements(r,req,requested_grid=g)); print('assessment keys',list(a));
regions=np.array([req.intervals[int(i)].region for i in g.segment]); vals={reg:float(np.min(r.il_db[regions==reg])) for reg in ['H2','H3']}; vals['worst_IL_db']=float(np.max(r.il_db[np.isin(regions,['UL','DL'])])); print('benchmark', vals, 'strict',a['strict_feasible'],'wall',time.time()-tic)
starts={str(seed):generate_for_definition(d,p,seed) for seed in range(1001,1013)}
report=dict(definition=data,definition_sha256=sha(asdict(d)), checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),vector_sha256=vector_sha(x),constraint_sha256=constraint_fingerprint(p),benchmark_17=vals,assessment=a,physical=plain(physical),starts=starts,python=platform.python_version())
(out/'benchmark-preflight.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n'); print('saved',out/'benchmark-preflight.json')
