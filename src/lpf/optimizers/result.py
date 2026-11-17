"""Minimal result produced directly by each optimizer, not an RF verdict."""
from dataclasses import dataclass


@dataclass(frozen=True)
class OptimizerResult:
    x: object  # selected Search-observed vector, or None when no valid point exists
    objective: float | None
    converged: bool  # solver numerical convergence, not RF compliance
    stop_reason: str
    evaluations: int  # solver callback count, distinct from actual RF forwards
