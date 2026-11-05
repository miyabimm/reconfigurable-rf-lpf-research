"""Policy-derived box and provenance-bound deterministic C1 initial vectors.

Bounds follow the complete ParameterVectorSchema order and use the shared
JSON-derived closed intervals. The box alone cannot enforce SPD/connectivity.
"""
from dataclasses import asdict, dataclass
import hashlib
import json

import numpy as np


def definition_fingerprint(definition):
    raw = json.dumps(asdict(definition), sort_keys=True, separators=(",", ":"),
                     allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def vector_fingerprint(vector):
    x = np.asarray(vector, dtype="<f8")
    if x.ndim != 1 or not np.all(np.isfinite(x)):
        raise ValueError("Expected finite one-dimensional input vector")
    return hashlib.sha256(x.tobytes()).hexdigest()


@dataclass(frozen=True)
class VectorBox:
    bounds: tuple[tuple[float | None, float | None], ...]
    open_lower: tuple[int, ...]


def circuit_box(circuit, *, gjm_search_max_pf=None):
    """Return the policy box, optionally narrowing only the GJM search box."""
    d, s, p = circuit.definition, circuit.schema, circuit.resolved_policy
    if gjm_search_max_pf is not None:
        if (isinstance(gjm_search_max_pf, (bool, str, bytes)) or
                not np.isscalar(gjm_search_max_pf)):
            raise ValueError("Invalid GJM search maximum")
        try:
            gjm_search_max_pf = float(gjm_search_max_pf)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Invalid GJM search maximum") from exc
        if (not np.isfinite(gjm_search_max_pf) or gjm_search_max_pf <= 0 or
                gjm_search_max_pf > p['components']['GJM01']['bounds']['max']):
            raise ValueError("GJM search maximum must be within physical limits")
    from lpf.search.component_constraints import physical_bounds, validate_search_box
    hard = physical_bounds(d, s, p)
    bounds = list(hard)
    if gjm_search_max_pf is not None:
        for i, kind in enumerate(d.fixed_c_types, len(d.inductor_types)):
            if kind == 'GJM01':
                bounds[i] = (bounds[i][0], gjm_search_max_pf)
    validate_search_box(bounds, hard)
    return VectorBox(tuple(bounds) + ((None, None),), ())


def make_seed(problem, vector, *, policy_id, policy_fingerprint,
              definition_sha256, input_sha256, seed, jitter_fraction=0.0,
              for_exploration=False):
    """Check a provenance-bound full vector and optionally jitter within its box.

    All provenance is explicit, never guessed from a length-compatible vector.
    ``input_sha256`` hashes little-endian float64 vector bytes, not its source
    file; callers must separately preserve and verify the source-file hash.
    Out-of-box input is rejected; explicit perturbations record before/after values.
    The resulting vector must pass existing component/SPD checks. No retries or
    search are performed; epigraph starts at the sampled worst passband IL.
    """
    c = problem.circuit
    if (policy_id != problem.policy_id or policy_fingerprint != problem.policy_fingerprint
            or definition_sha256 != definition_fingerprint(c.definition)):
        raise ValueError("Seed policy or topology fingerprint mismatch")
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    if not np.isfinite(jitter_fraction) or not 0 <= jitter_fraction <= 1:
        raise ValueError("jitter_fraction must be in [0, 1]")
    x = np.asarray(vector, dtype=float)
    if x.shape != (c.schema.vector_length,) or not np.all(np.isfinite(x)):
        raise ValueError("Expected finite complete circuit vector")
    if vector_fingerprint(x) != input_sha256:
        raise ValueError("Seed vector SHA mismatch")
    if any(v < lo or v > hi for v, (lo, hi) in zip(x, problem.box.bounds[:-1])):
        raise ValueError('Seed outside physical/search box; clipping is forbidden')
    original = tuple(map(float, x))
    if getattr(problem, "gjm_search_max_pf", None) is not None:
        if jitter_fraction:
            raise ValueError("Jitter is not supported with a GJM search box")
        if (any(x[i] < lo or x[i] > hi
                for i, (lo, hi) in enumerate(problem.box.bounds[:-1])) or
                any(x[i] <= problem.box.bounds[i][0] for i in problem.box.open_lower)):
            raise ValueError("Seed outside search box; clipping is forbidden")
    x = x.copy()
    changes = []
    rng = np.random.default_rng(seed)
    for i, (lo, hi) in enumerate(problem.box.bounds[:-1]):
        if jitter_fraction and lo != hi:
            before = float(x[i])
            x[i] = np.clip(x[i] + rng.uniform(-1, 1) * (hi-lo) * jitter_fraction, lo, hi)
            if x[i] != before:
                changes.append({"index": i, "kind": "jitter", "before": before, "after": float(x[i])})
    if for_exploration and c.policy_id != "RF-T008":
        raise ValueError("Exploration-only absence is RF-T008-only")
    gjm = {len(c.definition.inductor_types) + i
           for i, kind in enumerate(c.definition.fixed_c_types)
           if kind == "GJM01"} if for_exploration else set()
    if any(x[i] <= problem.box.bounds[i][0]
           for i in problem.box.open_lower if i not in gjm):
        raise ValueError("Clipping reached an excluded open lower bound")
    if for_exploration:
        c.validate_components(x, allow_absent_gjm=True)
    else:
        c.validate_components(x)
    il = problem.evaluator.il(x)
    t = float(np.max(il[problem.evaluator.role == 0]))
    return {"vector": tuple(map(float, x)) + (t,), "input_vector": original,
            "input_vector_sha256": input_sha256,
            "policy_id": policy_id, "policy_fingerprint": policy_fingerprint,
            "definition_sha256": definition_sha256, "seed": seed,
            "jitter_fraction": float(jitter_fraction), "changes": tuple(changes),
            "points_per_interval": problem.points_per_interval,
            "candidate_promotion_blocked": True}
