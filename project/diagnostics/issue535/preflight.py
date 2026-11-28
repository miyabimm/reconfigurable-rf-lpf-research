#!/usr/bin/env python3
"""Freeze and audit four independent plans without RF evaluation."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parents[3]
INP = Path(__file__).resolve().parent / 'inputs'
sys.path.insert(0, str(ROOT/'src'))
from lpf.search.development_plan import freeze_run
from lpf.search.component_constraints import validate_values
from lpf.search.source import source_identity
from lpf.search.storage import sha, vector_sha
from lpf.search.plan import Loader

load = lambda p: json.loads(p.read_text())
def main():
    assert all(os.environ.get(k) == '1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'))
    assert not subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=all'], cwd=ROOT, text=True)
    output = Path(sys.argv[1]); assert not output.exists()
    manifest = load(INP/'manifest.json')
    for name, expected in manifest['files_sha256'].items():
        assert hashlib.sha256((INP/name).read_bytes()).hexdigest() == expected
    starts, bounds = load(INP/'starts.json'), load(INP/'bounds.json')
    reports = {}
    for name, ftol, scale in [('A',1e-6,1.0),('B',1e-7,1.0),('C',1e-7,'jac'),('D',1e-8,'jac')]:
        config = yaml.load((INP/f'{name}.yaml').read_text(), Loader=Loader)
        plan, d, profile, model, _ = freeze_run(config, starts, root=ROOT, spot_checks={'terminal':[0,111]}, search_bounds=bounds, checkpoint_interval=1000)
        p = plan.data
        assert profile.fingerprint == 'd50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417'
        assert config['definition']['definition_sha256'] == 'bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068'
        assert len(p['jobs']) == 8 and len(p['grids']['baseline/search']['frequency_hz']) == 70 and len(p['grids']['terminal']['frequency_hz']) == 476
        assert p['search_bounds'] == bounds and p['spot_checks'] == {'terminal':[0,111]}
        step = p['config']['arms'][0]['steps'][0]
        assert (step['solver'],step['objective'],step['aggregation']) == ('trf','signed_margin_db','sum')
        assert step['effective_options'] == dict(max_evaluations=20000, ftol=ftol, x_scale=scale, restart_sigma=0.1)
        assert all(j['reservation'] == dict(rf_samples=1400476,rf_forwards=20001,independent_mna_samples=2) for j in p['jobs'])
        for j in p['jobs']:
            assert vector_sha(j['vector']) == j['vector_sha256'] == starts[str(j['seed'])]['baseline']['vector_sha256']
            physical = validate_values(d, model.schema, j['vector'], json.loads(profile.base_json))
            assert physical['component_policy_pass'] and physical['checked_settings'] == 6 and physical['min_L_eigenvalue_H'] > 0 and not physical['connection_role_evidence_incomplete']
        for s in p['rf_profile']['external_s2p'].values(): assert hashlib.sha256((ROOT/s['path']).read_bytes()).hexdigest() == s['sha256']
        reports[name] = {'plan':p, 'plan_sha256':plan.sha256}
    source = source_identity(ROOT)
    report = {'head': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(), 'source':source, 'source_sha256':sha(source), 'input_manifest_sha256':hashlib.sha256((INP/'manifest.json').read_bytes()).hexdigest(), 'files_sha256':manifest['files_sha256'], 'physical_starts':'pass', 'git_status':'clean', 'plans':reports}
    output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print('PASS four plans, source, trial, S2P, all starts, bounds, grids, budget', report['head'], report['source_sha256'])
if __name__ == '__main__': main()
