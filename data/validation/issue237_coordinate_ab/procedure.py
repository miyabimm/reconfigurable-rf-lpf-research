"""Issue 237 evidence recipe, not a general runner. Explicit one-EXP dispatch only.

Use Python3.12/frozen uv, OPENBLAS/OMP/MKL_NUM_THREADS=1, PYTHONPATH=src:.
prepare freezes saved inputs (no optimization); check is read-only; run EXP-NNN
calls the existing driver once and does NOT finalize/push or dispatch a next EXP.
"""
from copy import deepcopy
from functools import partial
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from lpf.checkpoint_io import atomic_write_json, canonical_config_hash
from lpf.experiment_manifest import new_manifest, write_manifest
from lpf.phase2_models.candidate_records import _circuit
from lpf.phase2_models.problem_seed import definition_fingerprint, vector_fingerprint
from lpf.phase2_models.sampled_epigraph import SampledEpigraph
from lpf.phase2_models.multistart import intermediate_scan
from lpf.phase2_models.staged_optimization import scipy_slsqp_stage
from scripts.experiment_id_registry import read_ledger, PATH
from scripts.run_phase2_shared import prepare_one_start, _complete_checkout, _fresh_main
from scripts.run_phase2_one_start import run_one_start

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
RUNS = ROOT / 'experiments/chatgpt_topology_search/runs'
BASE = '6ddc3deca86af9674d3167035397d59315c8cec3'


def load(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def args_for(ident):
    m = load(RUNS / ident / 'manifest.json')
    s = m['search_scope']
    inp = s['input_source']
    return dict(circuit=_circuit(dict(definition=inp['definition'], policy_id='RF-T008')),
        vector=inp['vector'], seed=23, jitter_fraction=0., coarse_points=2, fine_points=3,
        budget=inp['budget'], owner=s['reservation']['record']['owner'],
        request_id=s['reservation']['record']['request_id'], policy_id='RF-T008',
        policy_sha256=m['constraints']['effective_constraint_sha256'],
        source_sha=m['code']['execution_sha'], bands_sha256=m['bands_sha256'],
        input_sha256=s['input_source_sha256'], allow_trial=True)


def prepare():
    _complete_checkout(ROOT)
    main = _fresh_main(ROOT)
    assert not git('status', '--porcelain')
    ledger = read_ledger(git('show', 'origin/main:' + PATH))
    # Build every manifest in memory while the tree is still clean.
    planned, pairs = [], []
    for pair, old in enumerate(range(86, 95), 1):
        source_path = RUNS / f'EXP-{old:03}' / 'manifest.json'
        old_m = load(source_path)
        scope0 = old_m['search_scope']
        inp = scope0['input_source']
        seed = scope0['input_source_origin']['generated_start']['seed_record']
        c = _circuit(dict(definition=inp['definition'], policy_id='RF-T008'))
        p = SampledEpigraph(c, 2)
        replay = p.seed(inp['vector'], policy_id=c.policy_id,
            policy_fingerprint=c.policy_fingerprint,
            definition_sha256=definition_fingerprint(c.definition),
            input_sha256=vector_fingerprint(inp['vector']), seed=23)
        assert json.loads(json.dumps(replay)) == seed
        assert sha(source_path) == hashlib.sha256(subprocess.check_output(
            ['git', 'show', BASE + ':' + str(source_path.relative_to(ROOT))], cwd=ROOT)).hexdigest()
        row = dict(pair=pair, old_experiment=old_m['experiment_id'],
            source_manifest=str(source_path.relative_to(ROOT)), source_manifest_sha256=sha(source_path),
            class_name=scope0['input_source_origin']['class_name'],
            topology_sha256=scope0['input_source_origin']['exact_topology_key'],
            definition_sha256=seed['definition_sha256'], vector_sha256=inp['vector_sha256'],
            seed_sha256=canonical_config_hash(seed), seed_record=seed)
        for mode, coord in [('A', 'physical'), ('B', 'normalized')]:
            reservation = next(r for r in ledger if r['request_id'] == f'issue237-pair{pair}-{mode}')
            ident = reservation['experiment_id']
            row[mode] = ident
            scope = deepcopy(scope0)
            scope.update(issue_url='https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/237',
                paired_comparison=dict(pair=pair, mode=mode, coordinates=coord,
                    finite_difference_eps=None, ftol='scipy_default_unchanged',
                    physical_difference_steps_equal=False, old_experiment=old_m['experiment_id'],
                    source_manifest_sha256=sha(source_path), seed_sha256=canonical_config_hash(seed)),
                reservation=dict(record=reservation, request_key=reservation['request_id'],
                    verified_main_sha=main, workflow='reserve_experiment_number.yml'))
            scope['execution_plan'].update(maximum_total_starts=18, maximum_total_stages=72,
                raw_path=f'results/{ident}/run.json',
                optimize_stage=f'partial(scipy_slsqp_stage, coordinates={coord!r}, finite_difference_eps=None)',
                fatal_stop='STOP/timeout, unclassified partial, source/provenance/storage mismatch: stop; classified optimizer exceptions saved without retry')
            scope['validation_plan']['dense'] = ('Only strict30/legal candidates; existing dense1001/MNA84/power/passivity procedure and budget; no new validation pipeline')
            m = new_manifest(ident, reservation['purpose'], scope, objective='full_lpf', seed=23,
                             root=ROOT, constraint_id='RF-T008', allow_trial=True)
            st = deepcopy(load(source_path.parent / 'storage_record.json'))
            st.update(experiment_id=ident, stage='planned', git_readback='not_run', summary=None,
                      checkpoints=[], validation_overlays=[], supporting_evidence=[], limitations=[])
            planned.append((ident, m, st))
        pairs.append(row)
    for ident, m, st in planned:
        directory = RUNS / ident
        directory.mkdir(exist_ok=False)
        write_manifest(directory / 'manifest.json', m, root=ROOT)
        atomic_write_json(directory / 'storage_record.json', st)
    atomic_write_json(HERE / 'pairs.json', dict(issue=237, base_main=BASE,
        reservation_main=main, execution_source=git('rev-parse', 'HEAD'),
        maximum_starts=18, maximum_stages=72, pairs=pairs))


def check():
    for row in load(HERE / 'pairs.json')['pairs']:
        for mode in ('A', 'B'):
            ident = row[mode]
            prepared = prepare_one_start(ROOT, ident, **args_for(ident))
            assert canonical_config_hash(prepared['seed_record']) == row['seed_sha256']
            print(ident, mode, 'G1 PASS', flush=True)


def run(ident):
    pairs = load(HERE / 'pairs.json')['pairs']
    assert ident in [r[k] for r in pairs for k in ('A', 'B')]
    m = load(RUNS / ident / 'manifest.json')
    coord = m['search_scope']['paired_comparison']['coordinates']
    result = run_one_start(ROOT, ident, **args_for(ident), timeout_seconds=300,
        optimize_stage=partial(scipy_slsqp_stage, coordinates=coord, finite_difference_eps=None))
    print(ident, result['termination'], result['preservation'], flush=True)
    if result.get('unclassified_attempt') or result.get('preservation_error'):
        raise RuntimeError('Unclassified/packaging failure; retain raw and stop')
    if result['termination']['type'] in ('TimeoutError', '_Stopped', 'KeyboardInterrupt'):
        raise RuntimeError('Timeout/STOP; retain raw and stop')


def overlay(ident):
    m = load(RUNS / ident / 'manifest.json')
    summary = load(RUNS / ident / 'run_summary.json')
    raw = load(ROOT / 'results' / ident / 'run.json')
    staged = raw['staged_record']
    # A failed driver record may contain a seed fallback, which is NOT a final vector.
    final = (staged['stage_calls'][-1]['output_vector'] if staged and
             staged['numerical_state'] != 'failed' else None)
    payload = dict(experiment_id=ident, comparison=m['search_scope']['paired_comparison'],
        source_provenance=raw['source_provenance'], numerical_state=staged['numerical_state'],
        termination=raw['termination'], elapsed_seconds=raw['elapsed_seconds'],
        attempts=summary['attempts'], final_vector_with_t_db=final,
        stages=staged['stage_calls'], scan=None,
        validation=dict.fromkeys(('dense1001', 'independent_mna84', 'power', 'passivity'), 'not_run'),
        validation_reason='No eligible candidate established; independent validation not performed.')
    if final is not None:
        payload['scan'] = intermediate_scan(args_for(ident)['circuit'], final[:-1])
    path = HERE / (ident + '-17pt.json')
    atomic_write_json(path, payload)
    ref = dict(path=str(path.relative_to(ROOT)), sha256=sha(path))
    m['evidence'].append(ref)
    st = load(RUNS / ident / 'storage_record.json')
    # Overlay status is scan execution, NOT strict RF compliance (kept in observation).
    st['validation_overlays'].append(dict(method='grid', status='passed' if final else 'not_run', **ref))
    atomic_write_json(RUNS / ident / 'manifest.json', m)
    atomic_write_json(RUNS / ident / 'storage_record.json', st)


if __name__ == '__main__':
    command = sys.argv[1]
    if command == 'prepare':
        prepare()
    elif command == 'check':
        check()
    elif command == 'run':
        run(sys.argv[2])
    elif command == 'overlay':
        overlay(sys.argv[2])
    else:
        raise SystemExit('prepare | check | run EXP-NNN | overlay EXP-NNN')
