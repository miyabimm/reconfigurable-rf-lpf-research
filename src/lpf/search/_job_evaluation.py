"""Stage 4C-1 implementation details; no CLI, EXP, resume or parent ledger."""
from dataclasses import asdict
import hashlib
import os
import platform
import subprocess

import numpy as np

from lpf.timing import timed_method
from .evaluation import FixedStageEvaluation, raw_numbers
from .preflight import check_next_batch
from .storage import sha, plain


def source_identity(root):
    """Current implementation bytes plus HEAD/dirty patch, rechecked before RF."""
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args])
    names = sorted(str(p.relative_to(root)) for p in (root/'src').rglob('*.py'))
    names += ['pyproject.toml', 'uv.lock', 'scripts/run_rf_search.py']
    files = {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names}
    import scipy
    return dict(head=git('rev-parse', 'HEAD').decode().strip(), files=files,
                environment=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__,
                    threads={k: os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')}),
                dirty_patch_sha256=hashlib.sha256(git('diff', 'HEAD', '--', 'src', 'pyproject.toml', 'uv.lock', 'scripts/run_rf_search.py')).hexdigest())


class FixedJobEvaluation(FixedStageEvaluation):
    """Reuse the single-stage durable forward and independent audit unchanged.

    One active allocation at a time; every inactive allocation remains reserved.
    Confirmed stage completion releases only its unused allocation. Unknown cost
    never leaves the requested total. Other jobs retain their entire caps.
    """
    def __init__(self, plan, definition, policy, arm, path, spec, *, root):
        self.spec = spec
        self.result = dict(kind=('campaign_formal_raw_v1' if spec.data['kind'] == 'campaign_formal_job_v1'
                                 else 'stage4c1_development_only'), spec=plain(spec),
            status='not_started', exit_reason=None, steps=[],
            selection=dict(status='not_run', ranked=[], excluded=[]),
            terminal=dict(status='not_run', candidates=[]), dense=dict(status='not_run'),
            anytime=[dict(milestone=m, status='not_run', reason='threshold_not_reached')
                     for m in plan.data['config']['anytime_samples']])
        self.allocations = {}
        self.active = None
        first = next(a for a in plan.data['config']['arms'] if a['name'] == arm)['steps'][0]['name']
        super().__init__(plan, definition, policy, arm, first, path, root=root)
        for name, stage in self.job['stages'].items():
            self.allocations[f'{arm}/{name}'] = stage['upper_reservation']
        cfg = self.data['config']
        for i in range(cfg['selection']['max_candidates']):
            self.allocations[f'selection:{i}'] = self.job['selection_one_forward']
        for i in range(cfg['selection']['top_k']):
            self.allocations[f'terminal:{i}'] = self.job['terminal_one_forward']
        for i in range(len(cfg['anytime_samples'])):
            self.allocations[f'anytime:{i}'] = self.job['anytime_one_forward']
        self._checkpoint()

    def _validate_checkpoint(self):
        if self.spec.data['kind'] == 'campaign_formal_job_v1':
            from .gates import verify_campaign_job
            verify_campaign_job(self.spec, self.path, self.root)
        else:
            super()._validate_checkpoint()

    @timed_method('source_contract')
    def _contract(self):
        super()._contract()
        if self.spec.data['kind'] == 'campaign_formal_job_v1':
            from .gates import verify_campaign_job
            verify_campaign_job(self.spec, self.path, self.root)
        if source_identity(self.root) != self.spec.data['source']:
            raise ValueError('Development Job source identity changed')
        if sha(self.spec.data['source']) != self.spec.source_sha256:
            raise ValueError('Development Job source SHA mismatch')

    def used(self, allocation):
        return sum(row['requested'] for row in self.rows if row.get('allocation') == allocation)

    @property
    def search_requested(self):
        return sum(r['requested'] for r in self.rows if r['stage'].startswith(self.arm+'/'))

    def snapshot(self):
        # Called by the base constructor before its model is ready only after
        # model/grid setup; result and allocations already exist.
        reserved = sum(v-self.used(k) for k, v in self.allocations.items() if k != self.active)
        return raw_numbers(dict(self.result, plan_sha256=self.plan.sha256,
            policy_id=self.model.policy_id, policy_fingerprint=self.model.policy_fingerprint,
            requirements_fingerprint=self.requirements.fingerprint,
            definition_sha256=sha(asdict(self.definition)), rf_inputs=self.data['rf_inputs'],
            grids=self.data['grids'], requested=self.requested, completed=self.completed,
            search_requested=self.search_requested, evaluation_status=self.status, reason=self.reason,
            active=self.active, allocations={k: dict(cap=v, requested=self.used(k), reserved=v-self.used(k))
                                            for k, v in self.allocations.items()},
            reservations=dict(inactive=reserved, other_jobs=self.other_jobs, dense=self.data['costs']['dense']),
            remaining=dict(job=self.job['max_requested_samples']-self.requested,
                trial=self.data['costs']['max_trial_requested_samples']-self.requested),
            batches=self.rows, gates=(dict(G0_G1='passed', G2='running', G3_G5='not_run')
                if self.spec.data['kind'] == 'campaign_formal_job_v1' else self.data['gates']), finite_grid_only=True,
            continuous_band_proven=False, rf_compliance_certified=False,
            physical_q_srf_em_checked=False))

    def activate(self, allocation, grid):
        if self.status != 'ready' or allocation not in self.allocations:
            raise RuntimeError('STOP: inactive/failed/unknown allocation')
        self.active, self.stage = allocation, grid
        self.grid = self.plan.requested_grid(grid)
        self._checkpoint()

    def finish(self):
        if self.status != 'ready':
            raise RuntimeError('Cannot release uncertain allocation')
        del self.allocations[self.active]
        self.active = None
        self._checkpoint()

    def _check_budget(self, n):
        reserved = sum(v-self.used(k) for k, v in self.allocations.items() if k != self.active)
        check_next_batch(n, step_remaining=self.allocations[self.active]-self.used(self.active),
            job_remaining=self.job['max_requested_samples']-self.requested,
            trial_remaining=self.data['costs']['max_trial_requested_samples']-self.requested,
            job_reserved=reserved, trial_reserved=reserved+self.other_jobs)

    @timed_method('evaluation')
    def evaluate(self, vector):
        # Base appends and checkpoints the row before forward. Tag the row in
        # _checkpoint, including rejected/unknown rows, before it is persisted.
        result = self._assess(vector)
        if self.stage.startswith(self.arm+'/'):
            active, grid = self.active, self.stage
            for i, scan in enumerate(self.result['anytime']):
                if scan['status'] == 'not_run' and self.search_requested >= scan['milestone']:
                    scan.update(status='unknown', reason='threshold_crossed',
                                observation_batch=result['batch_index'])
                    if self.spec.data.get('storage_mode') == 'window100' and not self.spec.data.get('debug_forward_history'):
                        scan.update(observation_vector=plain(result['vector']),
                                    observation_vector_sha256=result['vector_sha256'])
                    self.activate(f'anytime:{i}', 'anytime')
                    try:
                        observed = self._assess(result['vector'])
                        scan.update(status='completed', batch_index=observed['batch_index'])
                        self.finish()
                    except BaseException:
                        scan['status'] = self.status
                        raise
                    finally:
                        if self.status != 'storage_failed':
                            self._checkpoint()
                    self.activate(active, grid)
        return result

    def _assess(self, vector):
        result = super().evaluate(vector)
        indices = self.spec.data['spot_checks'].get(self.stage)
        if indices:
            self.spot_check(result['batch_index'], indices)
        return result

    @timed_method('checkpoint')
    def _checkpoint(self):
        for row in self.rows:
            if 'allocation' not in row:
                row['allocation'] = self.active
        super()._checkpoint()

    def spot_check(self, batch_index, sample_indices, *, atol=1e-9):
        # Each persisted batch has its own grid, including completed earlier steps.
        stage, grid = self.stage, self.grid
        self.stage = self.rows[batch_index]['stage']
        self.grid = self.plan.requested_grid(self.stage)
        try:
            return super().spot_check(batch_index, sample_indices, atol=atol)
        finally:
            self.stage, self.grid = stage, grid
