"""Stage-1 deterministic diagnostic errors for the generic forward solver.

A failure describes the numerical stage, not proof of an RF-infeasible
physical circuit. Optimization status, independent MNA, and RF certificate
states must remain separate.
"""


class CircuitNumericalError(ValueError):
    """Fail-closed forward computation with machine-readable cause.

    Attributes:
        code: Stable short failure classification for future search runners.
        sample_index: Optional sampled frequency row (never guessed).
    """

    def __init__(self, code, message, *, sample_index=None):
        self.code = str(code)
        self.sample_index = sample_index
        suffix = "" if sample_index is None else f" (sample {sample_index})"
        super().__init__(f"{self.code}: {message}{suffix}")
