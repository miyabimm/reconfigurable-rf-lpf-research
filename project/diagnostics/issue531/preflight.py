import hashlib,json,os,sys,subprocess
from pathlib import Path
import yaml
root=Path.cwd(); inp=Path(os.environ['INPUT'])
sys.path.insert(0,str(root/'src'))
from lpf.search.development_plan import freeze_run
from lpf.search.component_constraints import validate_values
from lpf.search.source import source_identity
from lpf.search.storage import sha,vector_sha
from lpf.search.plan import Loader
assert all(os.environ.get(k)=='1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'))
assert not subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=all'],text=True)
load=lambda p: json.loads(p.read_text())
manifest=load(inp/'manifest.json')
for name,expected in manifest['files_sha256'].items(): assert hashlib.sha256((inp/name).read_bytes()).hexdigest()==expected
config=yaml.load((inp/'config.yaml').read_text(),Loader=Loader); starts=load(inp/'starts.json'); bounds=load(inp/'bounds.json')
plan,d,profile,model,_=freeze_run(config,starts,root=root,spot_checks={'terminal':[0,111]},search_bounds=bounds,checkpoint_interval=1000)
p=plan.data
assert profile.fingerprint=='d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417'
assert len(p['jobs'])==8 and len(p['grids']['baseline/search']['frequency_hz'])==70 and len(p['grids']['terminal']['frequency_hz'])==476
assert all(j['reservation']==dict(rf_samples=1400476,rf_forwards=20001,independent_mna_samples=2) for j in p['jobs'])
for j in p['jobs']:
    assert vector_sha(j['vector'])==j['vector_sha256']
    physical=validate_values(d,model.schema,j['vector'],json.loads(profile.base_json))
    assert physical['component_policy_pass'] and physical['checked_settings']==6 and physical['min_L_eigenvalue_H']>0 and not physical['connection_role_evidence_incomplete']
for s in p['rf_profile']['external_s2p'].values(): assert hashlib.sha256((root/s['path']).read_bytes()).hexdigest()==s['sha256']
source=source_identity(root)
report={'head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'source':source,'source_sha256':sha(source),'plan':p,'plan_sha256':plan.sha256,'files_sha256':manifest['files_sha256'],'physical_starts':'pass','git_status':'clean'}
Path(os.environ['OUTPUT']).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
print('PASS preflight',report['head'],plan.sha256,report['source_sha256'])
