"""Development-only single-step Hybrid benchmark; no recovery or cost ledger."""
from dataclasses import asdict
from pathlib import Path

import numpy as np

from lpf.constraint_versions import constraint_fingerprint, load_constraint, rf_input_file
from lpf.optimizers.hybrid import hybrid_minimize
from lpf.rf_core.model import build_rf_model
from .component_constraints import (physical_bounds, validate_values, validate_search_box,
                                    _validate_values_with_bounds, _check_vector_box)
from .performance import compile_requirements, evaluate_requirements, grid_fingerprint, prepare_requirements
from .preflight import definition_sha, freeze
from .storage import sha, vector_sha


class MinimalWorker:
    """Prepare immutable scientific inputs once; never use for production jobs."""
    def __init__(self, plan, definition, policy, arm, seed, vector, expected_vector_sha, *, root):
        root = Path(root).resolve()
        data = plan.data
        cfg = data['config']
        if sha(data) != plan.sha256 or sha(freeze(cfg, root)) != plan.sha256:
            raise ValueError('Plan/current RF inputs mismatch')
        if sha(asdict(definition)) != definition_sha(cfg['definition']):
            raise ValueError('Definition/Plan mismatch')
        approved = load_constraint(cfg['rf']['constraint_id'], root=root, allow_trial=cfg['rf']['allow_trial'])
        if constraint_fingerprint(policy) != constraint_fingerprint(approved):
            raise ValueError('Policy/Plan mismatch')
        if type(seed) is not int or seed not in cfg['seeds'] or vector_sha(vector) != expected_vector_sha:
            raise ValueError('Seed/start SHA mismatch')
        chosen = next((a for a in cfg['arms'] if a['name'] == arm), None)
        if chosen is None or len(chosen['steps']) != 1 or chosen['steps'][0]['solver'] != 'hybrid':
            raise ValueError('Exactly one Hybrid step required')
        self.step = chosen['steps'][0]
        self.definition, self.policy, self.seed = definition, policy, seed
        self.model = build_rf_model(definition, policy)
        self.grid = plan.requested_grid(f"{arm}/{self.step['name']}")
        self.requirements = compile_requirements(policy, rf_input_file(root, policy['bands_file']), cfg['objective'])
        if (self.model.policy_fingerprint != constraint_fingerprint(approved) or
                sha(asdict(self.requirements)) != sha(data['requirements']) or
                grid_fingerprint(self.grid) != data['grids'][f"{arm}/{self.step['name']}"]['sha256']):
            raise ValueError('Model/requirements/grid mismatch')
        self.prepared_requirements = prepare_requirements(self.requirements, self.grid)
        self.bounds = physical_bounds(definition, self.model.schema, policy)
        self._physical_bounds = self.bounds
        _validate_values_with_bounds(definition, self.model.schema, vector, policy, self.bounds,
                                     frozen_model=self.model)
        self.x = np.array(vector, dtype=float, copy=True)
        self.evaluator = self.model.evaluator(self.grid)

    def _check_box(self, vector):
        return _check_vector_box(vector, self._physical_bounds)

    def evaluate(self, vector):
        # Public/external candidates cross a trust boundary. SPD remains RF Core's job.
        return self._evaluate(self._check_box(vector))

    def _evaluate(self, vector):
        x = np.array(vector, dtype=float, copy=True)
        x.setflags(write=False)
        response = self.evaluator.evaluate(x)
        assessment = evaluate_requirements(response, self.prepared_requirements)
        return response, assessment

    def residuals(self, vector):
        return self._residuals(self.evaluate(vector))

    def _solver_residuals(self, vector):
        # Hybrid constructs all callback candidates within its frozen box.
        return self._residuals(self._evaluate(vector))

    @staticmethod
    def _residuals(evaluation):
        _, a = evaluation
        if not np.isfinite(a['worst_il_db']) or a['worst_il_db'] < 0:
            raise ValueError('Hybrid requires finite nonnegative IL; no floor')
        return np.r_[np.sqrt(a['worst_il_db']), np.maximum(0., -np.asarray(a['mandatory_g']))]

    def solve(self):
        # Check the solver box at the boundary, not at every callback.
        validate_search_box(self.bounds, self._physical_bounds)
        self._check_box(self.x)
        result = hybrid_minimize(self._solver_residuals, self.x, self.bounds, seed=self.seed,
                                 aggregation=self.step['aggregation'], **self.step['options'])
        for vector in [result.best_x, *(run.end_x for run in result.runs)]:
            if vector is not None:
                self._check_box(vector)
                validate_values(self.definition, self.model.schema, vector, self.policy, frozen_model=self.model)
        return result
