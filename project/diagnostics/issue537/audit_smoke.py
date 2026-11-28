#!/usr/bin/env python3
"""Audit #537's single staged CLI smoke, without running RF or modifying raw files."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
from lpf.search._development_runner import _bytes_info, _verify_receipt
from lpf.search.storage import sha, vector_sha

PHASES = ('screening', 'discovery', 'exploitation', 'refinement')
COSTS = ('rf_forwards', 'rf_samples', 'independent_mna_samples')


def load(path):
    return json.loads(path.read_text())


def audit(path):
    path = Path(path)
    config, manifest, summary = (load(path/name) for name in ('config.json', 'manifest.json', 'summary.json'))
    assert config == load(ROOT/'tests/fixtures/issue537-staged-smoke.json')
    assert manifest['config_sha256'] == sha(config)
    assert manifest['source_sha256'] == sha(manifest['source'])
    source = manifest['source']
    assert source['head'] == '388fc961d67230970abff56b01637257e1f6e0c0'
    assert source['dirty_patch_sha256'] == hashlib.sha256(b'').hexdigest()
    assert source['environment']['threads'] == dict(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    for name, digest in source['files'].items():
        blob = subprocess.check_output(['git', '-C', str(ROOT), 'show', f"{source['head']}:{name}"])
        assert hashlib.sha256(blob).hexdigest() == digest, name
    assert manifest['identity']['rf_profile']['effective_sha256'] == 'd50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417'
    assert manifest['identity']['search_bounds_sha256'] == '4a72989fbbc1db6ba73719dae9c85f7dc82e18d4e91402d316c60cba7e64525e'
    assert manifest['maximum_cost'] == dict(rf_forwards=48, rf_samples=63378, independent_mna_samples=182)
    assert summary['status'] == 'completed' and not summary['reproducible']
    previous = {r['seed']: r for r in manifest['initial_starts']}
    totals = {k: 0 for k in COSTS}
    rows = {}
    for name, expected_count in zip(PHASES, (3, 2, 2, 2), strict=True):
        folder = path/name
        plan, state = load(folder/'plan.json'), load(folder/'run.json')
        assert state['status'] == 'completed' and sha(plan) == state['plan_sha256']
        assert state['source_sha256'] == manifest['source_sha256']
        assert state['plan_raw'] == _bytes_info((folder/'plan.json').read_bytes())
        assert len(state['jobs']) == len(plan['jobs']) == expected_count
        assert {k: plan[k] for k in manifest['identity']} == manifest['identity']
        assert len(plan['grids']['baseline/search']['segment']) == (196 if name == 'refinement' else 70)
        assert len(plan['grids']['terminal']['segment']) == (28028 if name == 'refinement' else 476)
        found = []
        for job, frozen in zip(state['jobs'], plan['jobs'], strict=True):
            assert job['status'] == 'completed' and job['seed'] == frozen['seed']
            seed = job['seed']
            assert seed in previous
            assert frozen['vector_sha256'] == previous[seed]['vector_sha256'] == vector_sha(previous[seed]['vector'])
            directory = folder/job['raw_path']
            verified = _verify_receipt(directory, job['raw']['receipt.json'], job, state)
            assert all(job[k] == verified[k] for k in ('scientific_status', 'actual', 'released', 'raw'))
            inp, result = load(directory/'input.json'), load(directory/'result.json')
            assert inp['source'] == result['source'] == source
            assert inp['start']['vector_sha256'] == result['initial_vector_sha256'] == frozen['vector_sha256']
            assert inp['start']['vector'] == result['initial_vector'] == frozen['vector']
            step = result['steps'][0]
            candidate = result['terminal']['candidates'][0]
            assert candidate['vector'] == step['solver_result']['x']
            assert vector_sha(candidate['vector']) == candidate['vector_sha256']
            assert candidate['physical']['component_policy_pass'] and candidate['physical']['checked_settings'] == 6
            assert candidate['physical']['min_L_eigenvalue_H'] > 0
            assert not candidate['physical']['connection_role_evidence_incomplete']
            assert candidate['external_passivity'] == candidate['power_balance'] == 'checked_on_terminal_grid'
            independent = candidate['independent']
            assert independent['status'] == 'pass'
            assert independent['sample_indices'] == config['phases'][name]['spot_checks']['terminal']
            assert independent['passivity'] == independent['power_balance'] == 'pass_at_samples'
            grid = candidate['response']['grid']
            assert all(grid[k] == plan['grids']['terminal'][k] for k in ('frequency_hz', 'setting', 'segment'))
            assert set(grid['segment']) == set(range(28)) and set(grid['setting']) == set(range(6))
            assert step['stop_reason'] != 'solver_failure'
            assert all(local['status'] >= 0 for local in step['local_run_details'])
            for k in COSTS:
                totals[k] += job['actual'][k]
            found.append(dict(seed=seed, initial_vector_sha256=frozen['vector_sha256'],
                              vector_sha256=candidate['vector_sha256'], receipt_sha256=job['raw']['receipt.json']['sha256'],
                              actual=job['actual'], stop_reason=step['stop_reason'], converged=step['converged'],
                              independent_spots=len(independent['sample_indices'])))
        rows[name] = found
        selected = summary['selection'][name]
        for r in selected:
            assert any(x['seed'] == r['seed'] and x['vector_sha256'] == r['vector_sha256'] for x in found)
        previous = {r['seed']: r for r in selected}
    assert totals == manifest['maximum_cost']
    for k in COSTS:
        assert summary['ledger']['total'][k] == dict(maximum=totals[k], completed=totals[k], released=0, unknown=0, not_started=0)
    return dict(status='PASS', source_head=source['head'], source_sha256=manifest['source_sha256'],
                rf_profile=manifest['identity']['rf_profile'], totals=totals, phases=rows,
                final=summary['final'], note='Finite-grid development smoke only; no formal RF certification.')


if __name__ == '__main__':
    print(json.dumps(audit(sys.argv[1]), indent=2, sort_keys=True, allow_nan=False))
