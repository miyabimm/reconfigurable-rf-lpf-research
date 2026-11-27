#!/usr/bin/env python3
"""Issue 529 stage-1 config and budget/grid preflight; no RF forwards."""
import json
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
from lpf.minimax_profile import load_minimax_profile
from lpf.search.performance import compile_profile_grid, build_evaluation_grid, grid_fingerprint

OUT = ROOT/'project/diagnostics/issue529'

def main():
    config = json.loads((ROOT/'project/diagnostics/issue470/config.json').read_text())
    config['seeds'] = list(range(2001, 2041))
    config['budget'] = dict(rf_samples=14019040, rf_forwards=200040, independent_mna_samples=80)
    config['arms'][0]['steps'][0].update(solver='trf', options=dict(max_evaluations=5000, ftol=1e-6, x_scale=1.0, restart_sigma=0.1))
    path = OUT/'stage1-config.yaml'
    assert not path.exists()
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    profile = load_minimax_profile('RF-T010', root=ROOT, allow_trial=True)
    assert profile.fingerprint == 'd50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417'
    req = compile_profile_grid(profile)
    assert len(req.intervals) == 28
    grids = {}
    for label, p, s, expected in [('search12',2,3,70),('terminal12',17,None,476),('search3',5,9,196),('terminal3',1001,None,28028)]:
        g = build_evaluation_grid(req, p, s)
        assert len(g.frequency_hz) == expected and set(g.segment) == set(range(28)) and set(g.setting) == set(range(6))
        grids[label] = dict(samples=expected, sha256=grid_fingerprint(g))
        if label == 'terminal3':
            indices = []
            for seg in range(28):
                ix = [i for i, v in enumerate(g.segment) if v == seg]
                assert len(ix) == 1001
                indices.extend([ix[0], ix[500], ix[-1]])
            grids[label]['spot_indices'] = indices
    reserved = dict(stage1=dict(rf_forwards=40*5001,rf_samples=40*(70*5000+476),independent_mna_samples=80),stage2=dict(rf_forwards=8*85001,rf_samples=8*(70*85000+476),independent_mna_samples=16),stage3=dict(rf_forwards=1001,rf_samples=196*1000+28028,independent_mna_samples=84),reference=dict(rf_forwards=1,rf_samples=28028,independent_mna_samples=84))
    assert sum(v['rf_forwards'] for v in reserved.values()) == 881050
    assert sum(v['rf_samples'] for v in reserved.values()) == 61874904
    assert sum(v['independent_mna_samples'] for v in reserved.values()) == 264
    (OUT/'preflight-grid-budget.json').write_text(json.dumps(dict(grids=grids,reserved=reserved),indent=2)+'\n')
    print('PASS grid and total budget (no RF forwards)')

if __name__ == '__main__':
    main()
