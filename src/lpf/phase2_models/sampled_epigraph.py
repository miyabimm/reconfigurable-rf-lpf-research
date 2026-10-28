"""Finite-grid RF portion of the Stage 3 minimax problem (not an optimizer).

No optimization runner is supplied. The complete circuit vector precedes
one epigraph in dB.
Residuals are nonnegative when satisfied: t - IL on UL/DL and attenuation
minus the mandatory minimum on H2/H3. Nominal targets are not hard constraints.
All values refer to the external-port cascade and a finite sampling grid only.
"""
import numpy as np

from .api import NominalCircuit, build_nominal_circuit
from .problem_seed import circuit_box, make_seed


class SampledEpigraph:
    """Bind one approved nominal circuit and its explicit finite grid."""

    def __init__(self, circuit, points_per_interval):
        if not isinstance(circuit, NominalCircuit):
            raise TypeError("Expected an approved NominalCircuit")
        self.circuit = circuit
        policy = circuit.resolved_policy
        checked = build_nominal_circuit(policy, circuit.definition)
        if (checked.policy_fingerprint != circuit.policy_fingerprint or
                checked.schema != circuit.schema or checked.topology != circuit.topology):
            raise ValueError("Circuit policy, definition or schema mismatch")
        if circuit.policy_id not in ("RF-T005", "RF-T007", "RF-T008"):
            raise ValueError("Unsupported trial policy")
        self.box = circuit_box(circuit)
        self.mandatory_stop_db = float(
            policy["evaluation"]["full_phase2"]["minimum_h2_h3_db"]
        )
        if not np.isfinite(self.mandatory_stop_db):
            raise ValueError("Invalid mandatory stopband limit")
        self.evaluator = circuit.forward_evaluator(points_per_interval)
        self.points_per_interval = points_per_interval
        self.policy_id = circuit.policy_id
        self.policy_fingerprint = circuit.policy_fingerprint

    def seed(self, vector, **provenance):
        return make_seed(self, vector, **provenance)

    def _split(self, vector):
        x = np.asarray(vector, dtype=float)
        if (x.ndim != 1 or x.size != self.circuit.schema.vector_length + 1
                or not np.all(np.isfinite(x))):
            raise ValueError("Expected complete finite circuit vector plus epigraph dB")
        self.circuit.decode(x[:-1])
        return x[:-1], float(x[-1])

    def objective(self, vector):
        """Minimize the final coordinate, the passband IL epigraph in dB."""
        _, t = self._split(vector)
        return t

    def residuals(self, vector):
        """Per-sample RF residuals, in the evaluator's original grid order.

        Negative values violate the corresponding sampled RF inequality. This
        does not check component constraints, connectivity, MNA or promotion.
        """
        x, t = self._split(vector)
        il = self.evaluator.il(x)
        role = self.evaluator.role
        return np.where(role == 0, t - il, il - self.mandatory_stop_db)
