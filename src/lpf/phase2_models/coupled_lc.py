"""Phase-2 coupled-L / lossy-C nodal evaluator with explicit circuit inputs.

Reusable by NEW EXPs without importing any archived experimental runner or
mutating module globals. The forward model uses Schur nodal elimination; it
is NOT an independent branch-current MNA validation.

Units: L nH, C pF, omega rad/s, zero-based hot nodes, ground -1.
The parametric vector schema is explicit and is deliberately distinct
from the RF policy's admissible component ranges and topology restrictions.
"""
from dataclasses import dataclass

import numpy as np

from ._grid import CASES, SampledExternalEvaluator
from .circuit_layout import InductorTree, incidence_matrix
from .numerical_diagnostics import CircuitNumericalError


def _floats(values, *, label, positive=False, nonnegative=False):
    try:
        v = tuple(float(item) for item in values)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"Invalid {label}") from exc
    if not all(np.isfinite(item) for item in v):
        raise ValueError(f"Non-finite {label}")
    if positive and not all(item > 0 for item in v):
        raise ValueError(f"Non-positive {label}")
    if nonnegative and not all(item >= 0 for item in v):
        raise ValueError(f"Negative {label}")
    return v


@dataclass(frozen=True)
class CircuitValues:
    """One nominal circuit: setting-invariant L/k and six capacitor rows."""

    inductances_nh: tuple[float, ...]
    coupling_k: tuple[float, ...]
    capacitors_pf_by_setting: tuple[tuple[float, ...], ...]

    def __post_init__(self):
        object.__setattr__(
            self, "inductances_nh",
            _floats(self.inductances_nh, label="inductances", positive=True)
        )
        object.__setattr__(
            self, "coupling_k", _floats(self.coupling_k, label="coupling")
        )
        rows = tuple(_floats(row, label="C", nonnegative=True)
                     for row in self.capacitors_pf_by_setting)
        if len(rows) != len(CASES) or len({len(row) for row in rows}) != 1:
            raise ValueError("Exactly six equal-length capacitor rows required")
        object.__setattr__(self, "capacitors_pf_by_setting", rows)


@dataclass(frozen=True)
class ParameterVectorSchema:
    """Legacy-compatible numeric parameter order.

    Flat vector:
      [L_nH, fixed_C_pf, signed_k, IC_fixed_C_pf, variable_C_pf(6 x n_variable)]
    Stamping order:
      [fixed_C, variable_C(setting), IC_fixed_C, constant_C]

    A 'constant' capacitor is built in (e.g. RF-T007's shunt 0.5pF/Q40).
    It is not a variable-C or an RF-T008 IC-fixed branch. Its location and
    Q belong to the topology, not the vector. This schema does not assert
    that the values are RF-policy-compliant.
    """

    n_inductors: int
    n_fixed: int
    n_coupling: int
    n_ic_fixed: int
    n_variable: int
    constant_caps_pf: tuple[float, ...] = ()

    def __post_init__(self):
        for label in ("n_inductors", "n_fixed", "n_coupling",
                      "n_ic_fixed", "n_variable"):
            value = getattr(self, label)
            if type(value) is not int or value < (1 if label == "n_inductors" else 0):
                raise ValueError("Invalid schema dimension " + label)
        object.__setattr__(
            self, "constant_caps_pf",
            _floats(self.constant_caps_pf, label="constant C", nonnegative=True)
        )

    @property
    def vector_length(self):
        return (self.n_inductors + self.n_fixed + self.n_coupling
                + self.n_ic_fixed + len(CASES) * self.n_variable)

    @property
    def capacitor_count(self):
        return (self.n_fixed + self.n_variable + self.n_ic_fixed
                + len(self.constant_caps_pf))

    def decode(self, vector):
        x = np.asarray(vector, dtype=float)
        if x.ndim != 1 or x.size != self.vector_length or not np.all(np.isfinite(x)):
            raise ValueError(f"Expected finite vector of length {self.vector_length}")
        pos = 0
        def take(count):
            nonlocal pos
            v = tuple(map(float, x[pos:pos + count]))
            pos += count
            return v
        L = take(self.n_inductors)
        fixed = take(self.n_fixed)
        k = take(self.n_coupling)
        ic_fixed = take(self.n_ic_fixed)
        modes = take(len(CASES) * self.n_variable)
        rows = tuple(
            fixed + modes[s * self.n_variable:(s + 1) * self.n_variable]
            + ic_fixed + self.constant_caps_pf
            for s in range(len(CASES))
        )
        return CircuitValues(L, k, rows)

    def encode(self, values):
        """Reverse the schema; reject illegal cross-setting changes to fixed C."""
        if not isinstance(values, CircuitValues):
            raise TypeError("values must be CircuitValues")
        if (len(values.inductances_nh) != self.n_inductors or
                len(values.coupling_k) != self.n_coupling or
                any(len(row) != self.capacitor_count
                    for row in values.capacitors_pf_by_setting)):
            raise ValueError("Circuit values do not match vector schema")
        fixed = values.capacitors_pf_by_setting[0][:self.n_fixed]
        ic0 = self.n_fixed + self.n_variable
        ic_fixed = values.capacitors_pf_by_setting[0][ic0:ic0 + self.n_ic_fixed]
        for row in values.capacitors_pf_by_setting:
            if (row[:self.n_fixed] != fixed or
                    row[ic0:ic0 + self.n_ic_fixed] != ic_fixed or
                    row[ic0 + self.n_ic_fixed:] != self.constant_caps_pf):
                raise ValueError("Fixed/IC/constant capacitors differ by setting")
        variable = tuple(value for row in values.capacitors_pf_by_setting
                         for value in row[self.n_fixed:ic0])
        return np.array(
            values.inductances_nh + fixed + values.coupling_k
            + ic_fixed + variable, dtype=float
        )


@dataclass(frozen=True)
class CoupledLCTopology:
    """Circuit incidence, signed coupling slots and explicit per-component Q.

    The coupling slot list is in *vector k order*, not the electrical L
    edge order. Each inductor's edge direction must remain consistent with
    the physical winding definition used for its signed mutual coupling.
    """

    inductor_tree: InductorTree
    coupling_pairs: tuple[tuple[int, int], ...]
    inductor_q: tuple[float, ...]
    capacitor_edges: tuple[tuple[int, int], ...]
    capacitor_q: tuple[float, ...]

    def __post_init__(self):
        if not isinstance(self.inductor_tree, InductorTree):
            raise TypeError("inductor_tree must be InductorTree")
        ni = len(self.inductor_tree.edges)
        lq = _floats(self.inductor_q, label="inductor Q", positive=True)
        cq = _floats(self.capacitor_q, label="capacitor Q", positive=True)
        if len(lq) != ni or len(cq) != len(self.capacitor_edges):
            raise ValueError("Inductor/capacitor Q count mismatch")
        # Reuse shared checked endpoint routine without changing orientation.
        cap_edges = tuple(tuple(pair) for pair in self.capacitor_edges)
        incidence_matrix(cap_edges, self.inductor_tree.node_count)
        pairs = tuple(tuple(pair) for pair in self.coupling_pairs)
        if (any(len(pair) != 2 or type(pair[0]) is not int or
                type(pair[1]) is not int or pair[0] == pair[1] or
                min(pair) < 0 or max(pair) >= ni for pair in pairs) or
                len({frozenset(pair) for pair in pairs}) != len(pairs)):
            raise ValueError("Invalid duplicate or out-of-range coupling slots")
        object.__setattr__(self, "capacitor_edges", cap_edges)
        object.__setattr__(self, "coupling_pairs", pairs)
        object.__setattr__(self, "inductor_q", lq)
        object.__setattr__(self, "capacitor_q", cq)

    def matrices(self, values):
        """Return the coupled L admittance numerator and signed M matrix."""
        if not isinstance(values, CircuitValues):
            raise TypeError("Expected CircuitValues")
        L = np.asarray(values.inductances_nh, dtype=float)
        k = np.asarray(values.coupling_k, dtype=float)
        n = len(self.inductor_tree.edges)
        if L.shape != (n,) or k.shape != (len(self.coupling_pairs),):
            raise ValueError("L/k dimensions do not match topology")
        M = np.diag(L.copy())
        for (a, b), coeff in zip(self.coupling_pairs, k):
            M[a, b] = M[b, a] = coeff * np.sqrt(L[a] * L[b])
        if not np.all(np.isfinite(M)):
            raise CircuitNumericalError("mutual_nonfinite", "Non-finite mutual L matrix")
        try:
            eigenvalues = np.linalg.eigvalsh(M)
        except np.linalg.LinAlgError as exc:
            raise CircuitNumericalError(
                "mutual_eigensolve_failed", "Mutual L eigensolver failed"
            ) from exc
        if not np.all(np.isfinite(eigenvalues)):
            raise CircuitNumericalError("mutual_nonfinite", "Non-finite L eigenvalues")
        if eigenvalues[0] <= eigenvalues[-1] * 1e-12:
            raise CircuitNumericalError("mutual_not_spd", "Coupled L matrix is not SPD")
        H = np.diag(L / np.asarray(self.inductor_q)) + 1j * M
        B = self.inductor_tree.incidence()
        try:
            numerator = B @ np.linalg.solve(H, B.T)
        except np.linalg.LinAlgError as exc:
            raise CircuitNumericalError(
                "inductor_solve_failed", "Coupled L admittance solve failed"
            ) from exc
        if not np.all(np.isfinite(numerator)):
            raise CircuitNumericalError(
                "inductor_admittance_nonfinite", "Non-finite L admittance"
            )
        return numerator, M

    def node_admittance(self, values, omega_rad_s, setting_indices):
        """Assemble independent lossy L and C contributions for each sample."""
        if not isinstance(values, CircuitValues):
            raise TypeError("Expected CircuitValues")
        omega = np.asarray(omega_rad_s, dtype=float)
        raw_setting = np.asarray(setting_indices)
        if (raw_setting.dtype.kind not in "iu" or
                raw_setting.dtype.kind == "b"):
            raise ValueError("Setting indices must be integers")
        setting = raw_setting.astype(int)
        if (omega.ndim != 1 or setting.shape != omega.shape or
                not np.all(np.isfinite(omega)) or np.any(omega <= 0) or
                np.any(setting < 0) or np.any(setting >= len(CASES))):
            raise ValueError("Invalid sampling frequencies/settings")
        if (len(values.capacitors_pf_by_setting[0]) !=
                len(self.capacitor_edges)):
            raise ValueError("Capacitor count does not match topology")
        K, _ = self.matrices(values)
        Y = np.broadcast_to(
            K, (omega.size, self.inductor_tree.node_count,
                self.inductor_tree.node_count)
        ).copy() / (omega[:, None, None] * 1e-9)
        C = np.asarray(values.capacitors_pf_by_setting, dtype=float)[setting]
        yc = omega[:, None] * 1e-12 * C / (
            1 / np.asarray(self.capacitor_q)[None, :] - 1j
        )
        Bc = incidence_matrix(self.capacitor_edges,
                              self.inductor_tree.node_count)
        Y += np.einsum("fb,ib,jb->fij", yc, Bc, Bc, optimize=True)
        if not np.all(np.isfinite(Y)):
            raise CircuitNumericalError(
                "node_nonfinite", "Non-finite nodal admittance",
                sample_index=int(np.flatnonzero(
                    ~np.all(np.isfinite(Y), axis=(1, 2))
                )[0])
            )
        return Y


def _fixed_port_impedance(policy, key):
    """Load exact source/load values from the resolved RF policy, never guess."""
    try:
        section = policy[key]
        impedance = complex(float(section["real"]), float(section["imag"]))
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"Invalid {key} in resolved RF policy") from exc
    if (not np.isfinite(impedance) or impedance.real <= 0 or
            section.get("frequency_dependent", False)):
        raise ValueError(f"Unsupported or non-passive constant {key}")
    return impedance


class CoupledLCEvaluator(SampledExternalEvaluator):
    """Phase-2 sampled RF forward evaluator over explicit immutable inputs.

    Samples exactly the grid and frozen S2P in SampledExternalEvaluator.
    Neither the RF constraint nor the independent MNA is implicitly proven.
    """

    def __init__(self, policy, points, topology, schema):
        if not isinstance(topology, CoupledLCTopology):
            raise TypeError("Expected CoupledLCTopology")
        if not isinstance(schema, ParameterVectorSchema):
            raise TypeError("Expected ParameterVectorSchema")
        if (schema.n_inductors != len(topology.inductor_tree.edges) or
                schema.n_coupling != len(topology.coupling_pairs) or
                schema.capacitor_count != len(topology.capacitor_edges)):
            raise ValueError("Circuit schema and topology disagree")
        self.topology = topology
        self.schema = schema
        self.source_ohms = _fixed_port_impedance(policy, "source_ohms")
        self.load_ohms = _fixed_port_impedance(policy, "load_ohms")
        super().__init__(policy, points)

    def il(self, vector):
        if isinstance(vector, CircuitValues):
            # A typed value is not an escape hatch for cross-setting changes
            # to fixed/IC-fixed/constant C or topology dimension mismatches.
            self.schema.encode(vector)
            values = vector
        else:
            values = self.schema.decode(vector)
        Y = self.topology.node_admittance(values, self.omega, self.setting)
        ports = (self.topology.inductor_tree.source_node,
                 self.topology.inductor_tree.load_node)
        middle = tuple(i for i in range(self.topology.inductor_tree.node_count)
                       if i not in ports)
        if not middle:
            R = Y[:, ports, :][:, :, ports]
        else:
            P = Y[:, ports, :][:, :, ports]
            U = Y[:, ports, :][:, :, middle]
            V = Y[:, middle, :][:, :, ports]
            E = Y[:, middle, :][:, :, middle]
            try:
                R = P - U @ np.linalg.solve(E, V)
            except np.linalg.LinAlgError as exc:
                raise CircuitNumericalError(
                    "schur_solve_failed",
                    "Internal-node Schur solve singular or ill-conditioned"
                ) from exc
        if not np.all(np.isfinite(R)):
            raise CircuitNumericalError(
                "schur_nonfinite", "Non-finite reduced two-port admittance",
                sample_index=int(np.flatnonzero(
                    ~np.all(np.isfinite(R), axis=(1, 2))
                )[0])
            )
        a, b, c, d = R[:, 0, 0], R[:, 0, 1], R[:, 1, 0], R[:, 1, 1]
        bad_transfer = np.flatnonzero(np.abs(c) < 1e-21)
        if bad_transfer.size:
            raise CircuitNumericalError(
                "transfer_singular", "Transfer admittance is singular",
                sample_index=int(bad_transfer[0])
            )
        t = np.empty((len(self.f), 2, 2), complex)
        t[:, 0, 0] = -d / c
        t[:, 0, 1] = -1 / c
        t[:, 1, 0] = -(a * d - b * c) / c
        t[:, 1, 1] = -a / c
        if not np.all(np.isfinite(t)):
            raise CircuitNumericalError("abcd_nonfinite", "Non-finite LPF ABCD")
        full = self.pre @ t @ self.post
        if not np.all(np.isfinite(full)):
            raise CircuitNumericalError(
                "cascade_nonfinite", "Non-finite external S2P + LPF cascade"
            )
        zl, zs = self.load_ohms, self.source_ohms
        den = full[:, 0, 0] * zl + full[:, 0, 1] + zs * (
            full[:, 1, 0] * zl + full[:, 1, 1]
        )
        if not np.all(np.isfinite(den)) or np.any(den == 0):
            raise CircuitNumericalError(
                "gain_denominator_invalid", "Non-finite or zero cascade denominator"
            )
        gain = 4 * zs.real * zl.real / np.abs(den) ** 2
        if not np.all(np.isfinite(gain)):
            raise CircuitNumericalError("gain_nonfinite", "Non-finite transfer gain")
        il = -10 * np.log10(np.maximum(gain, 1e-300))
        if not np.all(np.isfinite(il)):
            raise CircuitNumericalError("il_nonfinite", "Non-finite insertion loss")
        return il

    def summary(self, vector):
        values = vector if isinstance(vector, CircuitValues) else self.schema.decode(vector)
        y = self.il(values)
        critical = []
        for role in (0, 1, 2):
            index = np.flatnonzero(self.role == role)
            critical.append(int(index[np.argmax(y[index])
                                      if role == 0 else np.argmin(y[index])]))
        _, M = self.topology.matrices(values)
        return {
            "worst_IL_db": float(y[critical[0]]),
            "min_H2_db": float(y[critical[1]]),
            "min_H3_db": float(y[critical[2]]),
            "locations": tuple({
                "case": CASES[self.setting[i]],
                "frequency_mhz": float(self.f[i]),
                "segment": int(self.segment[i])
            } for i in critical),
            "min_L_eigenvalue_nH": float(np.linalg.eigvalsh(M)[0]),
        }
