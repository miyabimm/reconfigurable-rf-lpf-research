#!/usr/bin/env python3
"""Verify stage 1 inputs and freeze source/environment; no RF forwards."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import yaml
ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'project/diagnostics/issue529'
sys.path.insert(0, str(ROOT/'src'))
from lpf.search.component_constraints import validate_values
from lpf.search.development_plan import freeze_run
from lpf.search.plan import Loader
from lpf.search.source import source_identity
from lpf.search.storage import sha, vector_sha

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    assert all(os.environ.get(k) == '1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'))
    output = OUT/'preflight-source.json'
    assert not output.exists()
    inputs = OUT/'stage1-inputs'
    config = yaml.load((inputs/'config.yaml').read_text(), Loader=Loader)
    starts, bounds, manifest = (json.loads((inputs/f'{n}.json').read_text()) for n in ('starts','bounds','manifest'))
    assert all(digest(inputs/name) == value for name,value in manifest['files_sha256'].items())
    plan, d, profile, model, physical = freeze_run(config, starts, root=ROOT, spot_checks={'terminal':[0,111]}, search_bounds=bounds, checkpoint_interval=1000)
    assert plan.sha256 == manifest['plan_sha256']
    assert profile.fingerprint == 'd50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417'
    assert len(bounds) == 25 and bounds[:4] == [[0.4,27.0]]*4 and bounds[4:7] == [[0.1,10.0]]*3
    assert len(plan.data['jobs']) == 40
    assert all(j['reservation'] == dict(rf_forwards=5001,rf_samples=350476,independent_mna_samples=2) for j in plan.data['jobs'])
    assert [j['seed'] for j in plan.data['jobs']] == list(range(2001,2041))
    for job in plan.data['jobs']:
        assert manifest['sobol_seeds'][str(job['seed'])][job['arm']] == job['seed']
        assert vector_sha(job['vector']) == job['vector_sha256']
        evidence = validate_values(d, model.schema, job['vector'], json.loads(profile.base_json))
        assert evidence['component_policy_pass'] and evidence['checked_settings'] == 6 and evidence['min_L_eigenvalue_H'] > 0 and not evidence['connection_role_evidence_incomplete']
    for item in plan.data['rf_profile']['external_s2p'].values():
        assert digest(ROOT/item['path']) == item['sha256']
    assert digest(ROOT/'project/diagnostics/issue361/definition.json') == 'e8ac857c063e0b9d2eb8eaf629c2e4b700a694e9241f3bbc596d99f6374487f6'
    source = source_identity(ROOT)
    status = subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=all'],cwd=ROOT,text=True)
    assert not status, 'Run preflight from committed clean tree'
    report = dict(source=source,source_sha256=sha(source),git_status=status,plan_sha256=plan.sha256,rf_profile=plan.data['rf_profile'],bounds=bounds,bounds_sha256=plan.data['search_bounds_sha256'],parameter_schema=plan.data['parameter_schema'],starts={str(j['seed']):j['vector_sha256'] for j in plan.data['jobs']},input_files=manifest['files_sha256'],grid_sha256={k:v['sha256'] for k,v in plan.data['grids'].items()},script_sha256={p.name:digest(p) for p in OUT.glob('*.py')}, reference_file_sha256=digest(ROOT/'experiments/chatgpt_topology_search/runs/EXP-062/checkpoints/a6_best.json'))
    output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print('PASS: all stage1 starts physical, frozen inputs and clean source; zero RF forwards')
if __name__ == '__main__': main()
