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
from ._grid import CASES
from lpf.policy_schema import harmonic_limit_db


# Numerical search margin only; never an RF acceptance tolerance.
SEARCH_GUARD_DB = 0.005
_DEFAULT_WORKING_STOP = object()


class SampledEpigraph:
    """Bind one approved nominal circuit and its explicit finite grid.

    ``settings`` and ``working_stop_db`` are search-only opt-ins. None for
    working_stop_db drops harmonic inequalities, not their forward samples;
    neither option changes mandatory_stop_db or certifies RF compliance.
    """

    def __init__(self, circuit, points_per_interval, *, extra_frequencies=(), search_guard=False,
                 settings=None, working_stop_db=_DEFAULT_WORKING_STOP, gjm_search_max_pf=None):
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
        if type(search_guard) is not bool:
            raise TypeError("search_guard must be bool")
        self.search_guard_db = SEARCH_GUARD_DB if search_guard else 0.0
        self.box = circuit_box(circuit, gjm_search_max_pf=gjm_search_max_pf)
        self.gjm_search_max_pf = gjm_search_max_pf
        self.mandatory_stop_db = float(
            harmonic_limit_db(policy)
        )
        if not np.isfinite(self.mandatory_stop_db):
            raise ValueError("Invalid mandatory stopband limit")
        if working_stop_db is not _DEFAULT_WORKING_STOP:
            if search_guard:
                raise ValueError("Explicit working stop and search guard are mutually exclusive")
            if working_stop_db is not None:
                if isinstance(working_stop_db, (bool, str, bytes)):
                    raise ValueError("Working stop must be finite nonnegative dB or None")
                try:
                    working_stop_db = float(working_stop_db)
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError("Working stop must be finite nonnegative dB or None") from exc
                if not np.isfinite(working_stop_db) or working_stop_db < 0:
                    raise ValueError("Working stop must be finite nonnegative dB or None")
            self.search_stop_db = working_stop_db
        else:
            self.search_stop_db = self.mandatory_stop_db + self.search_guard_db
        if settings is not None:
            if (not isinstance(settings, (tuple, list)) or not settings or
                    any(not isinstance(case, str) or case not in CASES for case in settings) or
                    len(set(settings)) != len(settings)):
                raise ValueError("settings must contain unique known band cases")
            settings = tuple(settings)
        self.settings = settings
        extra_frequencies = tuple(extra_frequencies)
        self.evaluator = circuit.forward_evaluator(
            points_per_interval, extra_frequencies=extra_frequencies)
        if settings is not None:
            # Preserve the original CSV segment IDs and separate B13/B14 intervals.
            e = self.evaluator
            selected = np.isin(e.setting, [CASES.index(case) for case in settings])
            if any(not np.any((e.segment == segment) & selected)
                   for segment, _ in extra_frequencies):
                raise ValueError("Extra frequency belongs to an unselected setting")
            for name in ("f", "omega", "setting", "role", "segment", "pre", "post"):
                setattr(e, name, getattr(e, name)[selected])
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

        Negative values violate the corresponding sampled RF inequality. With
        an IL-only working target the returned array contains pass samples only.
        This does not check component constraints, connectivity, MNA or promotion.
        """
        x, t = self._split(vector)
        il = self.evaluator.il(x)
        role = self.evaluator.role
        if self.search_stop_db is None:
            return t - il[role == 0]
        return np.where(role == 0, t - il, il - self.search_stop_db)
