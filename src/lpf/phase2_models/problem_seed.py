"""Policy-derived box and provenance-bound deterministic C1 initial vectors.

Bounds follow the complete ParameterVectorSchema order. Open lower bounds for
PCB inductors and GJM capacitors are represented by their closed relaxation in
the optimizer box; ``open_lower`` records them and seed/component validation
rejects equality. No arbitrary positive engineering minimum is invented.
The box alone cannot enforce SPD, connectivity or candidate promotion.
"""
from dataclasses import asdict, dataclass
import hashlib
import json

import numpy as np

from .nominal_inductors import nominal_inductor_series


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


def circuit_box(circuit):
    """Return policy box for full circuit vector, followed by unbounded t (dB)."""
    d, s, p = circuit.definition, circuit.schema, circuit.resolved_policy
    bounds, strict = [], []
    def add(lo, hi, *, open_lower=False):
        if open_lower:
            strict.append(len(bounds))
        bounds.append((float(lo), float(hi)))
    for kind in d.inductor_types:
        _, lo, hi = nominal_inductor_series(p, kind)
        add(lo, hi, open_lower=(kind == "PCB_L"))
    for kind, edge in zip(d.fixed_c_types, d.capacitor_placement.fixed_edges):
        if kind == "GJM01":
            add(0, p["components"]["GJM01"]["max_pf_per_component"], open_lower=True)
        else:
            spec = (p["trial_pcb_pattern_c_by_connection"][
                "grounded" if -1 in edge else "non_ground"]
                if circuit.policy_id == "RF-T008" else p["components"]["PCB_PATTERN_C"])
            add(spec["min_pf_per_component"], spec["max_pf_per_component"])
    limits = p["coupling_limits"]
    adjacent = {frozenset(pair) for pair in zip(d.physical_order, d.physical_order[1:])}
    for a, b in d.coupling_pairs:
        ta, tb = d.inductor_types[a], d.inductor_types[b]
        if ta == tb == "PCB_L":
            limit = limits["pcb_pcb_abs_k_max_default"]
        elif "PCB_L" in (ta, tb):
            limit = limits["chip_pcb_abs_k_max"]
        elif frozenset((a, b)) in adjacent:
            limit = limits["chip_chip_strong_adjacent_abs_k_max"]
        else:
            limit = 0.0
        add(-limit, limit)
    if circuit.policy_id == "RF-T008":
        spec = p["trial_ic_fixed_c_by_connection"]
        for edge in d.capacitor_placement.ic_fixed_edges:
            rule = spec["grounded" if -1 in edge else "non_ground"]
            add(rule["min_pf_per_branch"], rule["max_pf_per_branch"])
        vlo, vhi = spec["variable_capacitance_pf_range"]
    else:
        spec = p["components"]["IC_VARIABLE_C"]
        vlo = spec["min_total_variable_pf_per_branch"]
        vhi = spec["max_total_variable_pf_per_branch"]
    for _ in range(6 * s.n_variable):
        add(vlo, vhi)
    if len(bounds) != s.vector_length:
        raise ValueError("Vector schema and policy box disagree")
    return VectorBox(tuple(bounds) + ((None, None),), tuple(strict))


def make_seed(problem, vector, *, policy_id, policy_fingerprint,
              definition_sha256, input_sha256, seed, jitter_fraction=0.0):
    """Clip a provenance-bound full vector and optionally jitter within its box.

    All provenance is explicit, never guessed from a length-compatible vector.
    ``input_sha256`` hashes little-endian float64 vector bytes, not its source
    file; callers must separately preserve and verify the source-file hash.
    Clipping/perturbations are returned per index with before/after values.
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
    original = tuple(map(float, x))
    x = x.copy()
    changes = []
    rng = np.random.default_rng(seed)
    for i, (lo, hi) in enumerate(problem.box.bounds[:-1]):
        before = float(x[i])
        x[i] = np.clip(x[i], lo, hi)
        if x[i] != before:
            changes.append({"index": i, "kind": "clip", "before": before, "after": float(x[i])})
        if jitter_fraction and lo != hi:
            before = float(x[i])
            x[i] = np.clip(x[i] + rng.uniform(-1, 1) * (hi-lo) * jitter_fraction, lo, hi)
            if x[i] != before:
                changes.append({"index": i, "kind": "jitter", "before": before, "after": float(x[i])})
    if any(x[i] <= problem.box.bounds[i][0] for i in problem.box.open_lower):
        raise ValueError("Clipping reached an excluded open lower bound")
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
