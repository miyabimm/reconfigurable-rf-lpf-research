"""Sequential parent ledger, immutable job data and fail-closed gate boundary."""
from pathlib import Path
import hashlib
import platform
import os
from importlib.metadata import version
import subprocess
import sys

from .controller import actions
from .problem import build
from .starts import (generate, development_start, DEVELOPMENT_DEFINITION_SHA,
                     IllegalStart)
from .storage import atomic, canonical, sha
from .worker import JobSpec, execute_job


def provenance(root):
    root = Path(root)
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args])
    files = sorted((root / 'src').rglob('*.py')) + [root / 'uv.lock', root / 'pyproject.toml',
                                                     root / 'scripts/run_rf_search.py']
    patch = git('diff', 'HEAD', '--binary')
    tracked = set(git('ls-files').decode().splitlines())
    return {'git_head': git('rev-parse', 'HEAD').decode().strip(),
            'dirty_patch_sha256': hashlib.sha256(patch).hexdigest(),
            'dirty_patch': patch.decode(),
            'untracked_source': {str(p.relative_to(root)): p.read_text() for p in files
                                 if str(p.relative_to(root)) not in tracked},
            'packages': {name: version(name) for name in ('numpy', 'scipy', 'PyYAML')},
            'threads': {key: os.environ.get(key) for key in
                        ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')},
            'files': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
            'python': sys.version, 'platform': platform.platform()}


def check_development_plan(d):
    """Hard ceiling and fixed input for this non-EXP development smoke only."""
    config = d['config']
    arms = config['arms']
    if (sha(d['definition']) != DEVELOPMENT_DEFINITION_SHA or config['seeds'] != [23] or
            len(arms) != 1 or len(arms[0]['steps']) != 1 or config['anytime_samples'] or
            config['max_trial_requested_samples'] > 1600 or
            arms[0]['max_requested_samples'] > 1600 or
            arms[0]['steps'][0]['max_requested_samples'] > 1124):
        raise ValueError('development_rf requires fixed 4L input, one seed/step and <=1600 samples')
    opts = arms[0]['steps'][0]['options']
    if (opts['max_evaluations'] > 12 or
            opts.get('max_iterations', opts.get('maxiter', 0)) > 2 or
            opts.get('max_restarts', 0) != 0):
        raise ValueError('development_rf solver ceiling exceeded')


def run(plan, output, *, mode='fixture', root=None):
    if mode not in ('fixture', 'development_rf'):
        raise ValueError('not_ready: production requires existing G0/G1 manifest/remote readback and G2-G5 audits')
    if mode == 'development_rf':
        check_development_plan(plan.data)
    from .plan import ROOT
    root = (ROOT if root is None else Path(root)).resolve()
    output = Path(output).resolve()
    # Ignore checkout ancestors such as ~/src: protect repository inputs, not
    # unrelated names above the checkout. No EXP/evidence writes or resume.
    parts = output.relative_to(root).parts if output.is_relative_to(root) else output.parts
    if any(part in ('experiments', 'data', 'rf', 'src', 'project') or part.startswith('EXP-')
           for part in parts):
        raise ValueError('Fixture output cannot target research evidence/source directories')
    output.mkdir(parents=True, exist_ok=False)
    d = plan.data
    source = provenance(root)
    state = {'kind': ('development_rf_smoke_not_an_EXP' if mode == 'development_rf'
                      else 'fixture_only_not_an_EXP'), 'plan_sha256': plan.sha256,
             'source': source, 'source_sha256': sha(source), 'plan': d,
             'status': 'unknown', 'starts': {}, 'jobs': [], 'trials': {},
             'gates': d['gates'], 'ranking17': [], 'validation': 'not_run'}
    schedule = list(actions(plan))
    for action in schedule:
        arm = d['config']['arms'][action.arm_index]
        state['jobs'].append({'job_id': f'seed{action.seed}_{arm["name"]}',
                              'trial_id': f'seed{action.seed}', 'status': 'not_started'})
    atomic(output / 'run.json', state)
    try:
        c = build(d['definition'], d['config']['rf'])
        for seed in d['config']['seeds']:
            try:
                state['starts'][str(seed)] = (development_start(c, seed, d['box'], d['open_lower'])
                    if mode == 'development_rf' else generate(c, seed, d['box']))
            except IllegalStart as exc:
                state['starts'][str(seed)] = exc.record
                raise
        atomic(output / 'run.json', state)
        for action, row in zip(schedule, state['jobs']):
            data = {'plan': d, 'source': source, 'backend': mode,
                    'arm_index': action.arm_index, 'start': state['starts'][str(action.seed)]}
            spec = JobSpec(row['job_id'], row['trial_id'], plan.sha256,
                           sha(source), canonical(data))
            row['status'] = 'unknown'
            atomic(output / 'run.json', state)
            result = execute_job(spec, output / row['job_id'])
            row.update(status=result['status'], result_sha256=sha(result),
                       cost=result['cost'], exit_reason=result['exit_reason'])
            if result['terminal17']['status'] == 'completed':
                state['ranking17'].append({'job_id': row['job_id'],
                                          **result['terminal17']['observation']})
            requested = sum((r['cost'] or {}).get('frequency_samples_requested', 0)
                            for r in state['jobs'] if r['trial_id'] == row['trial_id'] and 'cost' in r)
            if requested > d['config']['max_trial_requested_samples']:
                raise RuntimeError('Trial requested-sample invariant violated')
            state['trials'][row['trial_id']] = {'frequency_samples_requested': requested,
                'frequency_samples_completed': sum((r.get('cost') or {}).get('frequency_samples_completed', 0)
                    for r in state['jobs'] if r['trial_id'] == row['trial_id'])}
            atomic(output / 'run.json', state)
            if result['status'] in ('failed', 'interrupted', 'unknown'):
                state['status'] = result['status']
                break
        else:
            state['status'] = 'completed'
    except KeyboardInterrupt:
        state.update(status='interrupted', exit_reason='parent KeyboardInterrupt')
    except Exception as exc:
        state.update(status='failed', exit_reason=f'{type(exc).__name__}: {exc}')
    finally:
        from .validation import rank_key
        state['ranking17'].sort(key=lambda row: (rank_key(row['score']), row['job_id']))
        if not state['ranking17']:
            state['no_candidate_reason'] = 'no_completed_terminal17_observation'
        atomic(output / 'run.json', state)
    return state
