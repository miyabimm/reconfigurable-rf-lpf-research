"""Forward-free, topology-independent hypotheses on legal physical vectors."""
import numpy as np


def multiplier_interval(values, bounds, open_lower):
    """Intersect positive scaling intervals; zero stays zero, fixed values bind."""
    low, high, low_open = 0., np.inf, True
    for value, (lo, hi), opened in zip(values, bounds, open_lower):
        if value == 0:
            if not lo <= 0 <= hi or (opened and lo == 0):
                raise ValueError('Zero value violates scaling source bounds')
            continue
        if value < 0:
            raise ValueError('Negative L/C scaling source')
        a, b = lo / value, hi / value
        if a > low:
            low, low_open = a, opened
        elif a == low:
            low_open = low_open or opened
        high = min(high, b)
    if high < low or (high == low and low_open) or not np.isfinite(high):
        raise ValueError('Empty or unbounded positive multiplier interval')
    return float(low), float(high), bool(low_open)


def transform_candidate(problem, vector, unit, slot, metadata):
    """Slots 0/1 scale L/C; 2/3 blend Cv. Never clip, retry or forward."""
    x = np.asarray(vector, float)
    result = x.copy()
    schema = problem.circuit.schema
    nl, nf, nk = schema.n_inductors, schema.n_fixed, schema.n_coupling
    bounds = np.asarray(problem.box.bounds[:-1], float)
    if slot < 2:
        groups = (list(range(nl)), list(range(nl, nl + nf)) +
                  list(range(nl + nf + nk, len(x))))
        factors = []
        for coordinate, indices in enumerate(groups):
            interval = multiplier_interval(x[indices], bounds[indices],
                [i in problem.box.open_lower for i in indices])
            lo, hi, opened = interval
            factor = lo + float(unit[coordinate]) * (hi - lo)
            metadata.setdefault('multiplier_intervals', []).append(list(interval))
            factors.append(factor)
            if factor <= 0 or (opened and factor == lo):
                raise ValueError('Selected multiplier at excluded open boundary')
            result[indices] = x[indices] * factor
        metadata.update(lambda_L=factors[0], mu_C=factors[1],
                        alpha=np.sqrt(factors[0] / factors[1]),
                        beta=1 / np.sqrt(factors[0] * factors[1]))
    else:
        if schema.n_variable == 0:
            raise ValueError('No variable C branches for Cv trend')
        evaluator = problem.evaluator
        frequencies = []
        for setting in range(6):
            indices = np.flatnonzero((evaluator.setting == setting) & (evaluator.role == 0))
            if not len(indices):
                raise ValueError('Missing actual pass sample for Cv trend')
            mean = np.mean(evaluator.f[indices])
            i = min(indices, key=lambda j: (abs(evaluator.f[j] - mean), evaluator.f[j]))
            frequencies.append(float(evaluator.f[i]))
        inv = 1 / np.square(frequencies)
        if not np.all(np.isfinite(inv)) or np.ptp(inv) == 0:
            raise ValueError('Degenerate representative frequencies')
        trend = (inv - min(inv)) / np.ptp(inv)
        rho = .5
        metadata.update(rho=rho, representative_frequencies_mhz=frequencies)
        start = nl + nf + nk + schema.n_ic_fixed
        for setting in range(6):
            for branch in range(schema.n_variable):
                i = start + setting * schema.n_variable + branch
                lo, hi = bounds[i]
                target = lo + trend[setting] * (hi - lo)
                result[i] = (1 - rho) * x[i] + rho * target
    if np.array_equal(result, x):
        raise ValueError('Transformation duplicates source vector (zero/fixed/degenerate coordinates)')
    return result
