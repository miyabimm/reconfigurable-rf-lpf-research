#!/usr/bin/env python3
"""Read-only RF analysis and evidence packaging; never performs RF evaluation."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'project/diagnostics/issue529'
RAW=Path('/home/user/src/issue529-persistent-raw')
sys.path.insert(0,str(ROOT/'src'))
from lpf.search.storage import sha

def load(p): return json.loads(p.read_text())
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p, obj):
    assert not p.exists(),p
    p.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
def stats(values):
    a=np.asarray(values,dtype=float)
    return dict(min=float(np.min(a)),q1=float(np.quantile(a,.25)),median=float(np.median(a)),q3=float(np.quantile(a,.75)),max=float(np.max(a)))
def artifact(source,target):
    assert not target.exists()
    if target.suffix == '.gz':
        with source.open('rb') as f, target.open('wb') as out:
            with gzip.GzipFile(filename='',mode='wb',fileobj=out,mtime=0) as z: shutil.copyfileobj(f,z)
        assert hashlib.sha256(gzip.decompress(target.read_bytes())).hexdigest()==digest(source)
    else:
        shutil.copyfile(source,target); assert digest(source)==digest(target)
    return dict(source=str(source),source_sha256=digest(source),source_bytes=source.stat().st_size,artifact=str(target.relative_to(ROOT)),artifact_sha256=digest(target),artifact_bytes=target.stat().st_size)

def main():
    spec=importlib.util.spec_from_file_location('issue529_selection',OUT/'select.py')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    audits={}
    for stage in (1,2,3):
        audited,_=module.audit(stage)
        saved=module.load_audit(stage)
        assert audited == saved
        audits[stage]=saved
    ref=load(OUT/'reference-compact.json')
    assert ref['full_evidence']['sha256']==digest(OUT/'reference.json')
    labels=['L0_nH','L1_nH','L2_nH','L3_nH','GJM0_pF','GJM1_pF','GJM2_pF','PCB0_pF','k01','k13','k32','ICfix0_pF','ICfix1_pF']+[f'{s}_Cv{i}_pF' for s in ('B71','B12','B28','B13+B14','B26','B8') for i in (0,1)]
    assert len(labels)==25
    box=np.asarray(load(OUT/'stage1-inputs/bounds.json'))
    summaries={}
    for stage,a in audits.items():
        rows=a['rows']; final=np.asarray([r['final_vector'] for r in rows]); normalized=(final-box[:,0])/(box[:,1]-box[:,0])
        metrics={k:stats([r[k] for r in rows]) for k in ('terminal_max_margin_db','terminal_J_db2','search_J_db2','worst_il_db','min_h2_db','min_h3_db','local_runs','restarts')}
        counts=dict(rf_t010=sum(r['feasible'] for r in rows),near_reference=sum(r['worst_il_db']<=ref['metrics']['worst_il_db']+0.05 and r['min_h2_db']>=30 and r['min_h3_db']>=30 for r in rows),at_least_reference=sum(r['worst_il_db']<=ref['metrics']['worst_il_db'] and r['min_h2_db']>=30 and r['min_h3_db']>=30 for r in rows),converged=sum(r['converged'] for r in rows))
        per_parameter=[dict(name=name,bounds=box[i].tolist(),values=stats(final[:,i]),fraction=stats(normalized[:,i]),within_1pct_lower=int(np.sum(normalized[:,i]<=.01)),within_1pct_upper=int(np.sum(normalized[:,i]>=.99))) for i,name in enumerate(labels)]
        costs={k:sum(r['actual'][k] for r in rows) for k in rows[0]['actual']}
        elapsed=(RAW/f'stage{stage}-finished.txt').read_text()
        job_times=[]
        for r in rows:
            job=RAW/f'stage{stage}'/r['job_id']
            job_times.append(dict(seed=r['seed'],approx_input_to_receipt_seconds=(job/'receipt.json').stat().st_mtime-(job/'input.json').stat().st_mtime,local_run_wall_seconds=sum(x['wall_s'] for x in r['local_run_details'])))
        summaries[str(stage)]=dict(jobs=len(rows),ranking=a['ranking'],metrics=metrics,counts=counts,per_parameter=per_parameter,costs=costs,execution_record=elapsed,job_times=job_times,checkpoint_counts=[dict(seed=r['seed'],count=len(r['checkpoints'])) for r in rows],stop_reasons={reason:sum(r['stop_reason']==reason for r in rows) for reason in sorted({r['stop_reason'] for r in rows})})
    stage1={r['seed']:r for r in audits[1]['rows']}
    comparison=[]
    for r in audits[2]['rows']:
        a=stage1[r['seed']]
        comparison.append(dict(seed=r['seed'],stage1_vector_sha256=a['final_sha256'],stage2_initial_sha256=r['initial_sha256'],stage2_final_sha256=r['final_sha256'],delta_stage2_minus_stage1={k:r[k]-a[k] for k in ('terminal_max_margin_db','terminal_J_db2','worst_il_db','min_h2_db','min_h3_db')}))
        assert a['final_sha256']==r['initial_sha256']
    best=audits[3]['rows'][0]; vector=np.asarray(best['final_vector']); reference=np.asarray(ref['vector'])
    thresholds=dict(rf_t010=best['feasible'],at_least_reference=best['worst_il_db']<=ref['metrics']['worst_il_db'] and min(best['min_h2_db'],best['min_h3_db'])>=30,near_reference=best['worst_il_db']<=ref['metrics']['worst_il_db']+.05 and min(best['min_h2_db'],best['min_h3_db'])>=30)
    total={k:sum(summaries[str(s)]['costs'][k] for s in (1,2,3))+ref['declared_cost'][k] for k in ('rf_forwards','rf_samples','independent_mna_samples')}
    assert total==dict(rf_forwards=881050,rf_samples=61874904,independent_mna_samples=264)
    raw_files={str(p.relative_to(RAW)):dict(bytes=p.stat().st_size,sha256=digest(p)) for p in sorted(RAW.rglob('*')) if p.is_file() and p.name!='uv-4a573bb78cb530b5.lock'}
    artifacts_dir=OUT/'artifacts'; artifacts_dir.mkdir(exist_ok=False)
    artifacts=[]
    artifacts.append(artifact(OUT/'reference.json',artifacts_dir/'reference-full.json.gz'))
    for stage in (1,2,3):
        a=audits[stage]; best=next(r for r in a['rows'] if r['seed']==a['ranking'][0]); raw=RAW/f'stage{stage}'; job=raw/best['job_id']
        for src,name in ((raw/'plan.json',f'stage{stage}-plan.json.gz'),(raw/'run.json',f'stage{stage}-run.json'),(job/'result.json',f'stage{stage}-best-result.json.gz'),(job/'receipt.json',f'stage{stage}-best-receipt.json'),(job/'input.json',f'stage{stage}-best-input.json.gz')):
            artifacts.append(artifact(src,artifacts_dir/name))
    summary=dict(reference_metrics=ref['metrics'],stages=summaries,stage1_to_stage2=comparison,stage3_decisions=thresholds,stage3_vs_reference_vector=[dict(name=n,reference=float(v),candidate=float(x),difference=float(x-v)) for n,v,x in zip(labels,reference,vector,strict=True)],total_including_reference=total,raw_directory=str(RAW),raw_files=raw_files,artifacts=artifacts,notes=['Stage 1/2 comparisons use the same 476-point terminal grid; Stage 3 is 28028 points and is not a same-grid improvement measurement.','Stage 2 is selected, not an independent-seed success rate.','Periodic checkpoints are instantaneous observations, not true cumulative-best curves.','Input-to-receipt times are filesystem timestamp differences, not instrumented per-job wall time.','Search maximum signed margin and search IL/H2/H3 are not saved in standard step raw; no extra RF evaluation was performed.'])
    save(OUT/'summary.json',summary)
    print('PASS re-audited all 49 jobs; total',total,'decisions',thresholds)
    print('raw files',len(raw_files),'artifacts',len(artifacts))
if __name__=='__main__': main()
