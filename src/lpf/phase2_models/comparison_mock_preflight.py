"""Mock-only wiring probe for issue 299; not an experiment or production runner.

No CLI or production G0/G1 bypass is provided. Every forward is replaced by a
unittest Mock, including C1 seed/replay. The common observation path is
mock-only and does not establish production anytime or experiment readiness.
"""
from dataclasses import asdict
from pathlib import Path
from tempfile import gettempdir
from unittest.mock import Mock, patch

import numpy as np

from lpf.checkpoint_io import atomic_write_json
from lpf.optimizers.hybrid import hybrid_minimize
from lpf.optimizers.pipeline import minimize_pipeline
from lpf.optimizers.slp import slp_minimize
from .evaluation_cost import SampleBudgetCost, SampleBudgetExceeded
from .problem_seed import definition_fingerprint, vector_fingerprint
from .optimizer_comparison import sampled_score
from .rf_pipeline_adapter import RFPipelineAdapter
from .sampled_epigraph import SampledEpigraph
from .staged_optimization import run_c1_staged, _json_value


_PIPELINE = dict(sobol_m=0, starts=(), max_evaluations=20,
                 hybrid_max_evaluations=1, hybrid_maxiter=1,
                 hybrid_max_restarts=0, restart_sigma=.1,
                 slp_max_evaluations=2, slp_max_iterations=1,
                 max_slp_candidates=1)


def sobol_start(adapter, seed):
    """Use the actual pipeline generator, without invoking a forward callback."""
    options = dict(_PIPELINE, max_evaluations=0)
    result = minimize_pipeline(adapter.residuals, adapter.errors, adapter.bounds,
                               constraints=adapter.constraints, seed=seed, **options)
    x = np.asarray(result['starts'][0]['x'], dtype=float)
    adapter.comparison.validate_vector(x)  # no clip, replacement, or forward
    return x


class _GridBudget(SampleBudgetCost):
    """Requested/completed by grid, with a reserved terminal scan batch."""
    def __init__(self, maximum):
        super().__init__(maximum)
        self.terminal = False
        self.grids = {}
        self.stages = {}
        self.stage = 'not_started'
        self.on_forward = None

    def forward(self, evaluator, vector):
        n = len(evaluator.f)
        if not self.terminal and self.frequency_samples_requested + n > self.max_samples - 476:
            raise SampleBudgetExceeded('Terminal 17-point scan reservation')
        before = self.snapshot()
        try:
            result = super().forward(evaluator, vector)
        finally:
            for table in (self.grids, self.stages.setdefault(self.stage, {})):
                row = table.setdefault(str(n), {'requested': 0, 'completed': 0, 'calls': 0, 'failures': 0})
                row['requested'] += self.frequency_samples_requested - before['frequency_samples_requested']
                row['completed'] += self.frequency_samples_completed - before['frequency_samples_completed']
                row['calls'] += self.RF_forward_calls - before['RF_forward_calls']
                row['failures'] += self.forward_failures - before['forward_failures']
        if self.on_forward is not None:
            self.on_forward(evaluator, vector, result)
        return result


def run_mock_arm(circuit, arm, seed, *, mock_forward, output, max_samples=2000, milestones=()):
    """Exercise one existing API with mock RF only, saving an atomic temp record.

    This deliberately small-budget probe cannot establish production readiness.
    The last observation is a legal finite forward, not necessarily an optimizer
    iterate. The C1 optimizer itself is a mock, not SciPy.
    """
    if not isinstance(mock_forward, Mock):
        raise TypeError('mock_forward must be a unittest.mock.Mock')
    if arm not in ('A', 'B', 'C', 'D'):
        raise ValueError('Unknown arm')
    output = Path(output).resolve()
    if not output.is_relative_to(Path(gettempdir()).resolve()) or output.exists():
        raise ValueError('Output must be a new temporary fixture')
    if (not isinstance(milestones, tuple) or any(type(v) is not int or v <= 0 for v in milestones)
            or tuple(sorted(set(milestones))) != milestones):
        raise ValueError('Milestones must be strictly increasing positive integers')
    meter = _GridBudget(max_samples)
    record = dict(arm=arm, seed=seed, state='not_run', stage='start',
                  start=None, last_observation=None, result=None, error=None,
                  anytime='mock_four_arm', terminal_reservation='mock_only', scans=[],
                  terminal_scan='not_run', production_g0_g1_g2='not_run',
                  dense='not_run', independent_mna='not_run')
    def save():
        record['cost'] = meter.snapshot()
        record['cost_by_grid_samples'] = meter.grids
        record['cost_by_stage'] = meter.stages
        atomic_write_json(output, record, compact=True)
    save()  # marker, before any RF callback
    try:
        coarse = RFPipelineAdapter(circuit, 2, cost_meter=meter)
        fine = RFPipelineAdapter(circuit, 3, cost_meter=meter)
        scan_adapter = RFPipelineAdapter(circuit, 17, cost_meter=meter)
        x = sobol_start(coarse, seed)
        record['start'] = {'x': x.tolist(), 'sha256': vector_fingerprint(x)}
        record['state'] = 'running'
        save()
        evaluator_type = type(coarse.evaluator)
        def fake_il(evaluator, vector):
            return mock_forward(evaluator, np.asarray(vector).copy())
        pending = list(milestones)
        scanning = False
        def scan(label, *, terminal=False):
            nonlocal scanning
            point = record['last_observation']
            if point is None:
                record['scans'].append({'milestone': label, 'state': 'not_run'})
                return
            meter.terminal = terminal
            old_stage = meter.stage
            meter.stage = 'terminal_scan' if terminal else 'milestone_scan'
            scanning = True
            try:
                verdict = scan_adapter.assess(point['x'])
                if terminal:
                    record['terminal_scan'] = 'observed'
                record['scans'].append({'milestone': label, 'state': 'observed',
                    'x_sha256': point['sha256'], 'score': asdict(verdict['score']),
                    'strict_finite_grid_feasible': verdict['strict_finite_grid_feasible'],
                    'samples_at_completion': meter.frequency_samples_requested})
                save()
            except BaseException:
                if terminal:
                    record['terminal_scan'] = 'failed'
                raise
            finally:
                scanning = False
                meter.stage = old_stage
                meter.terminal = False
        def observed(evaluator, vector, il):
            if scanning:
                return
            # A's seed/solver path does not itself reject every illegal proposal.
            # Validate the exact physical vector and finite complete RF result
            # before calling it an observation, without a second forward.
            coarse.comparison.validate_vector(vector)
            sampled_score(il, evaluator.role, coarse.mandatory_stop_db)
            record['last_observation'] = {'x': np.asarray(vector).tolist(),
                                          'sha256': vector_fingerprint(vector)}
            save()
            while pending and meter.frequency_samples_requested >= pending[0]:
                milestone = pending.pop(0)
                if meter.frequency_samples_requested + 476 > max_samples - 476:
                    record['scans'].append({'milestone': milestone, 'state': 'not_run',
                                            'reason': 'terminal_reservation'})
                else:
                    scan(milestone)
        meter.on_forward = observed
        def observe(adapter, method):
            def callback(vector):
                record['stage'] = method
                meter.stage = method
                return getattr(adapter, method)(vector)
            return callback
        with patch.object(evaluator_type, 'il', new=fake_il):
            record['stage'] = 'solver'
            if arm == 'A':
                meter.stage = 'seed'
                record['stage'] = 'seed'
                problem = SampledEpigraph(circuit, 2)
                measured = meter.epigraph(problem)
                seed_record = measured.seed(x, policy_id=problem.policy_id,
                    policy_fingerprint=problem.policy_fingerprint,
                    definition_sha256=definition_fingerprint(circuit.definition),
                    input_sha256=vector_fingerprint(x), seed=seed, jitter_fraction=0.)
                if seed_record['changes'] or not np.array_equal(seed_record['vector'][:-1], x):
                    raise ValueError('C1 changed the physical start')
                def mock_stage(problem, vector, maxiter, target):
                    return vector, dict(success=True, status=0, message='mock', nit=0, nfev=0)
                def stage_sink(snapshot):
                    record['c1_snapshot'] = _json_value(snapshot)
                    if snapshot['stage_calls']:
                        meter.stage = 'c1_' + snapshot['stage_calls'][-1]['stage']
                        record['stage'] = meter.stage
                    save()
                meter.stage = 'seed_replay'
                record['stage'] = 'seed_replay'
                result = run_c1_staged(circuit, seed_record, coarse_points=2, fine_points=3,
                                       optimize_stage=mock_stage, cost_meter=meter,
                                       require_legal_output=True, record_sink=stage_sink)
            elif arm == 'B':
                result = asdict(hybrid_minimize(observe(coarse, 'residuals'), x, coarse.bounds,
                    seed=seed, maxiter=1, max_restarts=0, max_evaluations=1,
                    restart_sigma=.1, aggregation='sum'))
            elif arm == 'C':
                result = asdict(slp_minimize(observe(fine, 'errors'), x, fine.bounds,
                    constraints=observe(fine, 'constraints'), aggregation='signed_max',
                    max_iterations=1, max_evaluations=2))
            else:
                result = minimize_pipeline(observe(coarse, 'residuals'), observe(fine, 'errors'),
                    coarse.bounds, constraints=observe(fine, 'constraints'), seed=seed, **_PIPELINE)
                if not np.array_equal(result['starts'][0]['x'], x):
                    raise ValueError('Pipeline Sobol start mismatch')
            # A reports internal callback failures as a returned record. Do not
            # run another forward after such a failure; budget exhaustion is
            # different because the reserved terminal batch remains available.
            if arm != 'A' or result['numerical_state'] != 'failed':
                scan('terminal', terminal=True)
        record['result'] = _json_value(result)
        # C1 returns failures and budget exhaustion inside its record.
        c1_state = result.get('numerical_state') if arm == 'A' else None
        if c1_state in ('budget_exhausted', 'failed'):
            record['state'] = c1_state
            record['error'] = result['exception']
        else:
            # API returned is not synonymous with convergence or RF feasibility.
            record['state'] = 'returned_unverified'
    except SampleBudgetExceeded as exc:
        record['state'] = 'budget_exhausted'
        record['error'] = {'type': type(exc).__name__, 'message': str(exc)}
        if record['last_observation'] is not None and record['terminal_scan'] == 'not_run':
            try:
                with patch.object(evaluator_type, 'il', new=fake_il):
                    scan('terminal', terminal=True)
            except Exception as scan_exc:
                record['scans'].append({'milestone': 'terminal', 'state': 'failed',
                    'error': {'type': type(scan_exc).__name__, 'message': str(scan_exc)}})
    except Exception as exc:
        record['state'] = 'failed'
        record['error'] = {'type': type(exc).__name__, 'message': str(exc)}
    except BaseException as exc:
        record['state'] = 'interrupted'
        record['error'] = {'type': type(exc).__name__, 'message': str(exc)}
        raise
    finally:
        save()
    return record
