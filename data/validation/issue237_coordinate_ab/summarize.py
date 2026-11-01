import json, hashlib, subprocess
from pathlib import Path
import numpy as np
from lpf.checkpoint_io import atomic_write_json,canonical_config_hash
from lpf.phase2_models.candidate_records import _circuit
from lpf.phase2_models.sampled_epigraph import SampledEpigraph
# Read-only source replay: requires full evidence checkout; no optimizer calls.
root=Path(__file__).resolve().parents[3]; here=Path(__file__).resolve().parent
load=lambda p: json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
pairs=load(here/'pairs.json')
gates=load(here/'gates.json')
assert gates['G0']['main']==pairs['reservation_main']
remote_records={r['files'][0]['path'].split('/')[-2]:r for r in gates['G3']}
rows=[]; comparisons=[]
for pair in pairs['pairs']:
 group={}
 for mode in ('A','B'):
  ident=pair[mode]; run=root/'experiments/chatgpt_topology_search/runs'/ident
  m=load(run/'manifest.json'); st=load(run/'storage_record.json'); s=load(run/'run_summary.json'); o=load(here/(ident+'-17pt.json'))
  assert remote_records[ident]['remote_byte_readback']=='passed'
  assert st['stage']=='complete' and st['git_readback']=='passed'
  assert o['source_provenance']['execution_kind']=='scipy_slsqp'
  c=_circuit({'definition':m['search_scope']['input_source']['definition'],'policy_id':'RF-T008'})
  p=SampledEpigraph(c,2)
  assert canonical_config_hash(p.seed(m['search_scope']['input_source']['vector'],policy_id=c.policy_id,policy_fingerprint=c.policy_fingerprint,definition_sha256=pair['definition_sha256'],input_sha256=pair['vector_sha256'],seed=23))==pair['seed_sha256']
  obs=o['scan']['observation']; v=obs['sampled_forward_metrics']; x=o['final_vector_with_t_db']
  minrf=min(v['min_H2_db']-30,v['min_H3_db']-30)
  minepi=x[-1]-v['worst_IL_db']; minres=min(minrf,minepi)
  legal=obs['component_policy']['component_policy_pass'] and not obs['component_policy']['connection_role_evidence_incomplete'] and obs['component_policy']['min_L_eigenvalue_H']>0
  box=all(lo<=x[i]<=hi for i,(lo,hi) in enumerate(p.box.bounds[:-1])) and all(x[i]>p.box.bounds[i][0] for i in p.box.open_lower)
  r={'pair':pair['pair'],'mode':mode,'old_experiment':pair['old_experiment'],'experiment_id':ident,'class_name':pair['class_name'],'solver_state':o['numerical_state'],'attempts':s['attempts'],'stage_status':[i['status']['status'] for i in o['stages']],'stages':len(o['stages']),'nfev':sum(i['status']['nfev'] for i in o['stages']),'elapsed_seconds':o['elapsed_seconds'],'stage_seconds':sum(i['elapsed_seconds'] for i in o['stages']),'exceptions':[i['exception'] for i in o['stages'] if i['exception']],'worst_IL_db_17':v['worst_IL_db'],'min_H2_db_17':v['min_H2_db'],'min_H3_db_17':v['min_H3_db'],'strict30_17':v['min_H2_db']>=30 and v['min_H3_db']>=30,'strict35_17':v['min_H2_db']>=35 and v['min_H3_db']>=35,'minimum_harmonic_residual_db_17':minrf,'maximum_negative_harmonic_residual_db_17':max(0.,-minrf),'minimum_epigraph_residual_db_17':minepi,'maximum_negative_all_residual_db_17':max(0.,-minres),'legal_components_roles_spd':legal,'box_pass':box,'min_L_eigenvalue_H':obs['component_policy']['min_L_eigenvalue_H'],'final_physical_vector':x[:-1],'final_t_db':x[-1],'final_vector_sha256':o['scan']['vector_sha256'],'validation':o['validation'],'overlay':str((here/(ident+'-17pt.json')).relative_to(root)),'overlay_sha256':sha(here/(ident+'-17pt.json')),'curated_bytes_g3':sum((root/e['path']).stat().st_size for e in m['evidence'])+(run/'manifest.json').stat().st_size+(run/'storage_record.json').stat().st_size}
  assert not r['strict30_17']
  rows.append(r); group[mode]=r
 a,b=group['A'],group['B']; av=np.array(a['final_physical_vector']);bv=np.array(b['final_physical_vector']);width=np.array([hi-lo for lo,hi in p.box.bounds[:-1]]);mask=width>0
 comparisons.append({'pair':pair['pair'],'A':a['experiment_id'],'B':b['experiment_id'],'delta_B_minus_A_physical_vector':(bv-av).tolist(),'max_abs_physical_delta_mixed_units':float(abs(bv-av).max()),'max_abs_box_fraction_delta':float((abs(bv-av)[mask]/width[mask]).max()),'delta_worst_IL_db_17_B_minus_A':b['worst_IL_db_17']-a['worst_IL_db_17'],'delta_nfev_B_minus_A':b['nfev']-a['nfev'],'delta_elapsed_seconds_B_minus_A':b['elapsed_seconds']-a['elapsed_seconds'],'t_delta_db_separate':b['final_t_db']-a['final_t_db']})
totals={}
for mode in ('A','B'):
 rr=[r for r in rows if r['mode']==mode]
 totals[mode]={'planned':9,'attempted':9,'converged':sum(r['solver_state']=='converged' for r in rr),'nonconverged':sum(r['solver_state']=='not_converged' for r in rr),'failed':0,'not_started':0,'strict30_17':sum(r['strict30_17'] for r in rr),'stages':sum(r['stages'] for r in rr),'nfev':sum(r['nfev'] for r in rr),'elapsed_seconds':sum(r['elapsed_seconds'] for r in rr),'stage_seconds':sum(r['stage_seconds'] for r in rr),'exception_stops':sum(len(r['exceptions']) for r in rr),'v2_recovery_starts':sum(r['stages']>2 for r in rr),'additional_retries':0,'timeout':0,'stop':0,'legal_components_roles_spd_box':sum(r['legal_components_roles_spd'] and r['box_pass'] for r in rr)}
report={'issue':237,'base_main':pairs['base_main'],'execution_source':pairs['execution_source'],'policy_id':'RF-T008','effective_sha256':'7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4','formal_unchanged':'RF-F003','objective':'full_lpf','reference_planes':'external_input_to_external_output','grid':'coarse2/fine3 per 28 separate intervals; 17-point read-only all six settings','finite_difference_eps':None,'ftol':'SciPy default 1e-6 unchanged','default_absolute_eps':1.4901161193847656e-8,'physical_fd_steps_equal':False,'totals':totals,'starts':rows,'paired_differences':comparisons,'validation':dict.fromkeys(('dense1001','independent_mna84','power','passivity'),'not_run'),'validation_reason':'strict30_17 eligible candidates zero, not rounded to PASS','limitations':['Finite grid only; no continuous-band guarantee','Coordinates and physical finite-difference steps both change; not a pure coordinate causal contrast','No statistical generalization, timing microbenchmark, initial-value independence or global optimality claim','Q(f), SRF, EM, tolerance, physical signed-k realization and measurements unverified','No solver reruns or additional starts; raw retained; G5 not performed']}
assert report==load(here/'report.json'), 'Saved aggregation differs from source evidence'
print('PASS: report replay matches saved evidence; no optimization or evidence rewrite')
print(json.dumps(totals,indent=2))
for pair in pairs['pairs']:
 rr=[r for r in rows if r['pair']==pair['pair']]
 print(pair['pair'],pair['old_experiment'],pair['class_name'],[(r['experiment_id'],r['stage_status'],r['worst_IL_db_17'],r['maximum_negative_harmonic_residual_db_17'],r['maximum_negative_all_residual_db_17'],r['nfev'],r['elapsed_seconds']) for r in rr])
