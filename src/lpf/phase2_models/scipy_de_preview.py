"""Small synthetic/mock DE connection, NOT an EXP runner or approved RF search.

SciPy uses Lampinen selection; rank_key is only our observed-best REPORT.
An invalid physical proposal aborts fail-closed, not a fabricated RF residual.
This conservative limitation must be resolved before any production connection.
Limits are mandatory caller choices, not research-standard budgets. Wall limit
is cooperative (cannot interrupt an in-flight forward or initializer).
"""
from dataclasses import asdict
import time

import numpy as np
from scipy.optimize import NonlinearConstraint, differential_evolution

from lpf.checkpoint_io import canonical_config_hash
from .evaluation_cost import EvaluationCost
from .problem_seed import definition_fingerprint, vector_fingerprint
from .optimizer_comparison import sampled_score


class _Stop(Exception):
    pass


class _BudgetCost(EvaluationCost):
    def __init__(self, sample_limit, wall_limit):
        super().__init__()
        self.sample_limit = sample_limit
        self.deadline = time.perf_counter() + wall_limit
        self.on_forward = None

    def check_wall(self):
        if time.perf_counter() >= self.deadline:
            raise _Stop('wall_limit')

    def forward(self, evaluator, vector):
        self.check_wall()
        if self.frequency_samples_requested + len(evaluator.f) > self.sample_limit:
            raise _Stop('budget_exhausted')
        il = super().forward(evaluator, vector)
        if self.on_forward is not None:
            self.on_forward(evaluator, vector, il)
        return il


def run_de_preview(comparison, *, initialize, seed, maxiter,
                   max_frequency_samples, max_proposals, max_wall_seconds):
    """Run public SciPy DE on mock forwards, returning partial evidence on stop.

    initialize(meter) returns generate_starts(..., count=N, cost_meter=meter).
    It is inside the budget/timer/exception boundary. Population must be >=5,
    distinct, complete, physically legal and SHA-bound. Its forward diagnostics
    are charged and included in observed-best reporting, even on partial init.
    No final re-evaluation is performed; solver's result is not RF certification.
    Use a fresh PhysicalComparison. No persistence/export/automatic retry.
    """
    for name, value, minimum in (('seed', seed, 0), ('maxiter', maxiter, 0),
            ('max_frequency_samples', max_frequency_samples, 0),
            ('max_proposals', max_proposals, 1)):
        if type(value) is not int or value < minimum:
            raise ValueError('Invalid ' + name)
    if not np.isfinite(max_wall_seconds) or max_wall_seconds <= 0:
        raise ValueError('Invalid max_wall_seconds')
    if comparison.cost.RF_forward_calls or comparison.cost.component_checks or comparison.cache:
        raise ValueError('A fresh, uncached comparison is required')
    meter = _BudgetCost(max_frequency_samples, max_wall_seconds)
    comparison.cost = meter
    best, last, generated, solver_state = None, None, None, None
    requests = 0
    reason, error = 'not_started', None
    wall, cpu = time.perf_counter(), time.process_time()

    def remember(x, score):
        nonlocal best
        candidate = {'vector': np.asarray(x, float).tolist(),
                     'vector_sha256': vector_fingerprint(x), 'score': asdict(score)}
        if best is None or score.rank_key() < best[0]:
            best = score.rank_key(), candidate

    def initialized_forward(evaluator, x, il):
        # A differently gridded initializer is not comparable to this run.
        if (not np.array_equal(evaluator.f, comparison.evaluator.f) or
                not np.array_equal(evaluator.role, comparison.evaluator.role)):
            raise ValueError('Initializer forward grid mismatch')
        remember(x, sampled_score(il, evaluator.role, comparison.mandatory_stop_db))

    meter.on_forward = initialized_forward

    def observe(x):
        nonlocal last, requests
        meter.check_wall()
        if requests >= max_proposals:
            raise _Stop('proposal_limit')
        requests += 1
        x = np.asarray(x, float)
        key = x.tobytes()
        if last is not None and last[0] == key:
            meter.cache_hits += 1  # exact F/constraint sharing, not another forward
            return last[1]
        score = comparison.evaluate(x)
        remember(x, score)
        last = key, score
        return score

    def objective(x):
        return observe(x).worst_il_db

    def residual(x):
        score = observe(x)
        return np.array([score.min_h2_db - comparison.mandatory_stop_db,
                         score.min_h3_db - comparison.mandatory_stop_db])

    try:
        generated = initialize(meter)
        meter.on_forward = None
        starts = generated['starts']
        circuit = comparison.circuit
        if any(s['policy_id'] != circuit.policy_id or
               s['policy_sha256'] != circuit.policy_fingerprint or
               s['definition_sha256'] != definition_fingerprint(circuit.definition) or
               s['schema_sha256'] != canonical_config_hash(asdict(circuit.schema))
               for s in starts):
            raise ValueError('Population policy/definition/schema mismatch')
        bounds = comparison.box.bounds[:-1]
        population = np.asarray([s['vector'] for s in starts], float)
        if population.ndim != 2 or population.shape[0] < 5 or population.shape[1] != len(bounds):
            raise ValueError('DE requires at least five complete physical vectors')
        hashes = [vector_fingerprint(x) for x in population]
        if len(set(hashes)) != len(hashes) or hashes != [s['vector_sha256'] for s in starts]:
            raise ValueError('Population duplicate or SHA mismatch')
        # SciPy clips explicit init to its closed box. Reject BEFORE it can do so.
        for x in population:
            if (any(not lo <= v <= hi for v, (lo, hi) in zip(x, bounds)) or
                    any(x[i] <= bounds[i][0] for i in comparison.box.open_lower)):
                meter.box_rejections += 1
                raise ValueError('Population outside physical box/open endpoint')
            component = meter.components(comparison.circuit, x)
            if component['connection_role_evidence_incomplete']:
                meter.role_rejections += 1
                raise ValueError('Population role not proven')
        result = differential_evolution(
            meter.callback(objective), bounds,
            constraints=(NonlinearConstraint(meter.callback(residual, constraint=True), 0., np.inf),),
            init=population, rng=np.random.default_rng(seed), maxiter=maxiter,
            polish=False, workers=1)
        solver_state = {'success': bool(result.success), 'message': str(result.message),
                        'nit': int(result.nit), 'nfev': int(result.nfev)}
        reason = 'solver_returned'
    except _Stop as exc:
        reason = str(exc)
    except KeyboardInterrupt as exc:
        reason, error = 'interrupted', type(exc).__name__
    except Exception as exc:
        rejected = meter.box_rejections + meter.component_rejections + meter.role_rejections
        reason = 'physical_rejected' if rejected and not meter.forward_failures else 'failed'
        error = f'{type(exc).__name__}: {exc}'
    finally:
        # PhysicalComparison also times evaluations. Replace, do not add nested
        # timings: total includes initialization + solver overhead, exactly once.
        meter.wall_seconds = time.perf_counter() - wall
        meter.cpu_seconds = time.process_time() - cpu
    return {'mode': 'synthetic_mock', 'termination': reason, 'error': error,
            'policy_id': comparison.circuit.policy_id,
            'policy_sha256': comparison.circuit.policy_fingerprint,
            'definition_sha256': definition_fingerprint(comparison.circuit.definition),
            'seed': seed, 'maxiter': maxiter,
            'limits': {'frequency_samples_requested': max_frequency_samples,
                       'proposal_requests': max_proposals, 'wall_seconds': max_wall_seconds},
            'evaluation_cost': meter.snapshot(),
            'coarse2_equivalent': meter.frequency_samples_requested / 56,
            'proposal_requests': requests, 'generated': generated,
            'best_observed': None if best is None else best[1], 'solver': solver_state,
            'selection': 'SciPy Lampinen; lexicographic observed-best reporting only',
            'final_reevaluation': 'not_run', 'experiment_execution': 'not_run',
            'candidate_promotion_blocked': True, 'rf_compliance_certified': False}
