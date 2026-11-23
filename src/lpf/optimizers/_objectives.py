"""Weighted squared positive-violation calculations shared by solvers."""
import numpy as np


def validate_weights(weights):
    if weights is None:
        return None
    weights = np.asarray(weights, dtype=float)
    if weights.ndim != 1 or not weights.size or not np.all(np.isfinite(weights)) or np.any(weights < 0):
        raise ValueError('weights must be a nonempty finite nonnegative vector')
    return weights


def squared_terms(residuals, weights):
    # Multiplication order matters: zero weight must suppress even huge residuals.
    positive = np.maximum(residuals, 0)
    with np.errstate(over='ignore', invalid='ignore'):
        if weights is None:
            return np.multiply(positive, positive, out=positive)
        return weights * positive * positive


def aggregate(terms, aggregation):
    with np.errstate(over='ignore', invalid='ignore'):
        return float(np.sum(terms) if aggregation == 'sum' else np.max(terms))
