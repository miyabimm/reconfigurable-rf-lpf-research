"""Phase-2 coupled-L / lossy-C nodal evaluator with explicit circuit inputs.

Reusable by NEW EXPs without importing any archived experimental runner or
mutating module globals. The forward model uses Schur nodal elimination; it
is NOT an independent branch-current MNA validation.

Units: L nH, C pF, omega rad/s, zero-based hot nodes, ground -1.
The parametric vector schema is explicit and is deliberately distinct
from the RF policy's admissible component ranges and topology restrictions.
"""
from dataclasses import dataclass, field
from time import perf_counter_ns

import numpy as np

from ._grid import CASES
from lpf.topology_management.circuit_layout import InductorTree, incidence_matrix
from .numerical_diagnostics import CircuitNumericalError

# Installed only during the sequential development runner's deep Search.
_deep_timing = None


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
            v = tuple(x[pos:pos + count])
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

    def decode_batch(self, vectors):
        """Extract candidate-major L/k and six capacitor rows without objects.

        The evaluator replays invalid batches through decode() in candidate order.
        """
        x = np.asarray(vectors, dtype=float)
        if x.ndim != 2 or x.shape[1] != self.vector_length or not np.all(np.isfinite(x)):
            raise ValueError(f"Expected finite vectors of length {self.vector_length}")
        p = self.n_inductors
        L = x[:, :p]
        fixed = x[:, p:p + self.n_fixed]
        p += self.n_fixed
        k = x[:, p:p + self.n_coupling]
        p += self.n_coupling
        ic = x[:, p:p + self.n_ic_fixed]
        p += self.n_ic_fixed
        variable = x[:, p:].reshape(len(x), len(CASES), self.n_variable)
        if np.any(L <= 0):
            raise ValueError("Non-positive inductances")
        if np.any(fixed < 0) or np.any(ic < 0) or np.any(variable < 0):
            raise ValueError("Negative C")
        C = np.empty((len(x), len(CASES), self.capacitor_count), dtype=float)
        p = self.n_fixed
        C[:, :, :p] = fixed[:, None, :]
        C[:, :, p:p + self.n_variable] = variable
        p += self.n_variable
        C[:, :, p:p + self.n_ic_fixed] = ic[:, None, :]
        C[:, :, p + self.n_ic_fixed:] = self.constant_caps_pf
        return L, k, C

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
    _capacitor_stamps_flat: np.ndarray = field(init=False, repr=False, compare=False)
    _cap_incidence: np.ndarray = field(init=False, repr=False, compare=False)
    _cap_coefficient: np.ndarray = field(init=False, repr=False, compare=False)

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
        cap_incidence = incidence_matrix(cap_edges, self.inductor_tree.node_count).T
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
        # Each branch retains its own Q, including parallel and ground branches.
        coefficient = 1e-12 / (1 / np.asarray(cq) - 1j)
        object.__setattr__(self, '_cap_incidence', np.frombuffer(cap_incidence.tobytes(), dtype=cap_incidence.dtype).reshape(cap_incidence.shape))
        object.__setattr__(self, '_cap_coefficient', np.frombuffer(coefficient.tobytes(), dtype=complex))
        stamps = coefficient[:, None, None] * (
            cap_incidence[:, :, None] * cap_incidence[:, None, :]
        )
        flat = np.frombuffer(stamps.tobytes(), dtype=complex).reshape(
            len(cap_edges), self.inductor_tree.node_count ** 2
        )
        object.__setattr__(self, "_capacitor_stamps_flat", flat)

    def matrices(self, values):
        """Return the coupled L admittance numerator and signed M matrix."""
        if not isinstance(values, CircuitValues):
            raise TypeError("Expected CircuitValues")
        L = np.asarray(values.inductances_nh, dtype=float)
        k = np.asarray(values.coupling_k, dtype=float)
        n = len(self.inductor_tree.edges)
        if L.shape != (n,) or k.shape != (len(self.coupling_pairs),):
            raise ValueError("L/k dimensions do not match topology")
        return self._matrices_lk(L, k)

    def _matrices_lk(self, L, k):
        """Shared numerical kernel; callers validate dimensions and values."""
        timing = _deep_timing
        if timing: start = perf_counter_ns()
        M = np.diag(L.copy())
        for (a, b), coeff in zip(self.coupling_pairs, k):
            M[a, b] = M[b, a] = coeff * np.sqrt(L[a] * L[b])
        if not np.all(np.isfinite(M)):
            raise CircuitNumericalError("mutual_nonfinite", "Non-finite mutual L matrix")
        if timing: timing[0].add(timing[1] + '/matrices/build', perf_counter_ns() - start)
        try:
            if timing: start, failed = perf_counter_ns(), False
            try:
                eigenvalues = np.linalg.eigvalsh(M)
            except BaseException:
                if timing: failed = True
                raise
            finally:
                if timing: timing[0].add(timing[1] + '/matrices/spd_eigvalsh', perf_counter_ns() - start, failed=failed)
        except np.linalg.LinAlgError as exc:
            raise CircuitNumericalError(
                "mutual_eigensolve_failed", "Mutual L eigensolver failed"
            ) from exc
        if not np.all(np.isfinite(eigenvalues)):
            raise CircuitNumericalError("mutual_nonfinite", "Non-finite L eigenvalues")
        if eigenvalues[0] <= eigenvalues[-1] * 1e-12:
            raise CircuitNumericalError("mutual_not_spd", "Coupled L matrix is not SPD")
        if timing: start = perf_counter_ns()
        H = np.diag(L / np.asarray(self.inductor_q)) + 1j * M
        B = self.inductor_tree.incidence()
        if timing: timing[0].add(timing[1] + '/matrices/build_h_incidence', perf_counter_ns() - start)
        if timing: start, failed = perf_counter_ns(), False
        try:
            try:
                numerator = B @ np.linalg.solve(H, B.T)
            except BaseException:
                if timing: failed = True
                raise
        except np.linalg.LinAlgError as exc:
            raise CircuitNumericalError(
                "inductor_solve_failed", "Coupled L admittance solve failed"
            ) from exc
        finally:
            if timing: timing[0].add(timing[1] + '/matrices/inductor_solve', perf_counter_ns() - start, failed=failed)
        if not np.all(np.isfinite(numerator)):
            raise CircuitNumericalError(
                "inductor_admittance_nonfinite", "Non-finite L admittance"
            )
        return numerator, M

    def node_admittance(self, values, omega_rad_s, setting_indices, *, matrices=None):
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
        K, _ = self.matrices(values) if matrices is None else matrices
        timing = _deep_timing
        if timing: start = perf_counter_ns()
        Y = np.broadcast_to(
            K, (omega.size, self.inductor_tree.node_count,
                self.inductor_tree.node_count)
        ).copy() / (omega[:, None, None] * 1e-9)
        if timing: timing[0].add(timing[1] + '/node/l_expand', perf_counter_ns() - start)
        if timing: start = perf_counter_ns()
        C = np.asarray(values.capacitors_pf_by_setting, dtype=float)
        n = self.inductor_tree.node_count
        D = (C @ self._capacitor_stamps_flat).reshape(len(CASES), n, n)[setting]
        Y += omega[:, None, None] * D
        if timing: timing[0].add(timing[1] + '/node/c_stamping', perf_counter_ns() - start)
        if not np.all(np.isfinite(Y)):
            raise CircuitNumericalError(
                "node_nonfinite", "Non-finite nodal admittance",
                sample_index=int(np.flatnonzero(
                    ~np.all(np.isfinite(Y), axis=(1, 2))
                )[0])
            )
        return Y

    def node_admittance_with_jacobian(self, values, schema, omega_rad_s, setting_indices, *, matrices=None, node=None):
        """Nodal admittance and physical-unit derivatives in schema vector order.

        Constant capacitors have no vector column. Setting-specific columns are
        exactly zero at samples belonging to the other five settings.
        """
        timing = _deep_timing
        if timing: start = perf_counter_ns()
        if not isinstance(schema, ParameterVectorSchema):
            raise TypeError('Expected ParameterVectorSchema')
        schema.encode(values)
        if timing: timing[0].add(timing[1] + '/node_jacobian/schema', perf_counter_ns() - start)
        if matrices is None:
            matrices = self.matrices(values)  # preserves forward SPD/error checks
        Y = self.node_admittance(values, omega_rad_s, setting_indices, matrices=matrices) if node is None else node
        if timing: start = perf_counter_ns()
        L = np.asarray(values.inductances_nh)
        k = np.asarray(values.coupling_k)
        M = matrices[1]
        n, p = len(L), schema.vector_length
        dH = np.zeros((p, n, n), complex)
        for i in range(n):
            dH[i, i, i] = 1 / self.inductor_q[i] + 1j
        k_start = n + schema.n_fixed
        for j, ((a, b), coeff) in enumerate(zip(self.coupling_pairs, k)):
            dH[a, a, b] = dH[a, b, a] = 1j * M[a, b] / (2 * L[a])
            dH[b, a, b] = dH[b, b, a] = 1j * M[a, b] / (2 * L[b])
            dH[k_start + j, a, b] = dH[k_start + j, b, a] = 1j * np.sqrt(L[a] * L[b])
        if timing: timing[0].add(timing[1] + '/node_jacobian/dh', perf_counter_ns() - start)
        if timing: start = perf_counter_ns()
        H = np.diag(L / np.asarray(self.inductor_q)) + 1j * M
        B = self.inductor_tree.incidence()
        if timing: timing[0].add(timing[1] + '/node_jacobian/hb', perf_counter_ns() - start)
        if timing: start, failed = perf_counter_ns(), False
        try:
            X = np.linalg.solve(H, B.T)
            dK = -B @ np.linalg.solve(H, dH @ X)
        except np.linalg.LinAlgError as exc:
            if timing: failed = True
            raise CircuitNumericalError('sensitivity_inductor_solve_failed', 'Inductor sensitivity solve failed') from exc
        except BaseException:
            if timing: failed = True
            raise
        finally:
            if timing: timing[0].add(timing[1] + '/node_jacobian/inductor_solve', perf_counter_ns() - start, failed=failed)
        if timing: start = perf_counter_ns()
        omega = np.asarray(omega_rad_s)
        setting = np.asarray(setting_indices)
        dY = dK[None, :, :, :] / (omega[:, None, None, None] * 1e-9)
        if timing: timing[0].add(timing[1] + '/node_jacobian/expand', perf_counter_ns() - start)
        if timing: start = perf_counter_ns()
        stamps = self._capacitor_stamps_flat.reshape(schema.capacitor_count, Y.shape[1], Y.shape[2])
        for j in range(schema.n_fixed):
            dY[:, n + j] += omega[:, None, None] * stamps[j]
        ic_start = k_start + schema.n_coupling
        for j in range(schema.n_ic_fixed):
            dY[:, ic_start + j] += omega[:, None, None] * stamps[schema.n_fixed + schema.n_variable + j]
        variable_start = ic_start + schema.n_ic_fixed
        for s in range(len(CASES)):
            for j in range(schema.n_variable):
                dY[:, variable_start + s * schema.n_variable + j] += (
                    (omega * (setting == s))[:, None, None] * stamps[schema.n_fixed + j])
        if timing: timing[0].add(timing[1] + '/node_jacobian/c_stamps', perf_counter_ns() - start)
        if timing: start = perf_counter_ns()
        if not np.all(np.isfinite(dY)):
            if timing: timing[0].add(timing[1] + '/node_jacobian/finite', perf_counter_ns() - start, failed=True)
            raise CircuitNumericalError('sensitivity_node_nonfinite', 'Non-finite nodal sensitivity')
        if timing: timing[0].add(timing[1] + '/node_jacobian/finite', perf_counter_ns() - start)
        return Y, dY

    def port_admittance_jacobian(self, values, schema, omega_rad_s, setting_indices, T, *, matrices):
        """Project physical sensitivities onto ports in compact schema order.

        Shared directions precede only the variable-C directions of each sample's
        setting. Constant capacitors have no sensitivity direction.
        """
        timing = _deep_timing
        if timing: start = perf_counter_ns()
        if not isinstance(schema, ParameterVectorSchema):
            raise TypeError('Expected ParameterVectorSchema')
        schema.encode(values)
        if timing: timing[0].add(timing[1] + '/port_jacobian/schema', perf_counter_ns() - start)
        if timing: start = perf_counter_ns()
        L, k = np.asarray(values.inductances_nh), np.asarray(values.coupling_k)
        M = matrices[1]
        n = len(L)
        dH = np.zeros((n + schema.n_coupling, n, n), complex)
        for i in range(n):
            dH[i, i, i] = 1 / self.inductor_q[i] + 1j
        for j, ((a, b), coeff) in enumerate(zip(self.coupling_pairs, k)):
            dH[a, a, b] = dH[a, b, a] = 1j * M[a, b] / (2 * L[a])
            dH[b, a, b] = dH[b, b, a] = 1j * M[a, b] / (2 * L[b])
            dH[n + j, a, b] = dH[n + j, b, a] = 1j * np.sqrt(L[a] * L[b])
        if timing: timing[0].add(timing[1] + '/port_jacobian/dh', perf_counter_ns() - start)
        if timing: start = perf_counter_ns()
        H = np.diag(L / np.asarray(self.inductor_q)) + 1j * M
        B = self.inductor_tree.incidence()
        if timing: timing[0].add(timing[1] + '/port_jacobian/hb', perf_counter_ns() - start)
        if timing: start, failed = perf_counter_ns(), False
        try:
            X = np.linalg.solve(H, B.T)
            dK = -B @ np.linalg.solve(H, dH @ X)
        except np.linalg.LinAlgError as exc:
            if timing: failed = True
            raise CircuitNumericalError('sensitivity_inductor_solve_failed', 'Inductor sensitivity solve failed') from exc
        except BaseException:
            if timing: failed = True
            raise
        finally:
            if timing: timing[0].add(timing[1] + '/port_jacobian/inductor_solve', perf_counter_ns() - start, failed=failed)
        if timing: start = perf_counter_ns()
        omega = np.asarray(omega_rad_s)
        with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
            scale = omega * 1e-9
            # Detect overflow in the removed nodal expansion without allocating it.
            # Its real and imaginary components are scaled independently.
            nodal_peak = max(np.max(np.abs(dK.real)), np.max(np.abs(dK.imag))) / np.min(scale, initial=np.inf)
            dRL = (T.swapaxes(-1, -2)[:, None] @ dK[None] @ T[:, None]) / scale[:, None, None, None]
        if timing: timing[0].add(timing[1] + '/port_jacobian/l_projection', perf_counter_ns() - start)
        if timing: start = perf_counter_ns()
        with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
            count = schema.n_fixed + schema.n_variable + schema.n_ic_fixed
            cap_scale = omega[:, None] * self._cap_coefficient[None, :count]
            u = self._cap_incidence[:count] @ T
            dRC = cap_scale[:, :, None, None] * (u[:, :, :, None] * u[:, :, None, :])
        if timing: timing[0].add(timing[1] + '/port_jacobian/c_projection', perf_counter_ns() - start)
        if timing: start = perf_counter_ns()
        ks = n + schema.n_fixed
        ic = ks + schema.n_coupling
        shared = ic + schema.n_ic_fixed
        dR = np.zeros((len(omega), shared + schema.n_variable, 2, 2), complex)
        dR[:, :n] = dRL[:, :n]
        dR[:, ks:ic] = dRL[:, n:]
        dR[:, n:ks] = dRC[:, :schema.n_fixed]
        c_ic = schema.n_fixed + schema.n_variable
        dR[:, ic:shared] = dRC[:, c_ic:count]
        dR[:, shared:] = dRC[:, schema.n_fixed:c_ic]
        if timing: timing[0].add(timing[1] + '/port_jacobian/assemble', perf_counter_ns() - start)
        if timing: start = perf_counter_ns()
        if not (np.all(np.isfinite(dH)) and np.all(np.isfinite(dK)) and np.all(np.isfinite(scale)) and np.all(scale != 0) and np.isfinite(nodal_peak) and np.all(np.isfinite(cap_scale)) and np.all(np.isfinite(dRC)) and np.all(np.isfinite(dR))):
            if timing: timing[0].add(timing[1] + '/port_jacobian/finite', perf_counter_ns() - start, failed=True)
            raise CircuitNumericalError('sensitivity_node_nonfinite', 'Non-finite nodal sensitivity')
        if timing: timing[0].add(timing[1] + '/port_jacobian/finite', perf_counter_ns() - start)
        return dR

    def port_admittance(self, values, omega_rad_s, setting_indices, *, check_power=False, matrices=None):
        """Shared forward Schur reduction; never used by independent MNA."""
        if matrices is None:
            Y = self.node_admittance(values, omega_rad_s, setting_indices)
        else:
            Y = self.node_admittance(values, omega_rad_s, setting_indices, matrices=matrices)
        timing = _deep_timing
        if timing: start = perf_counter_ns()
        ports = (self.inductor_tree.source_node, self.inductor_tree.load_node)
        middle = tuple(i for i in range(self.inductor_tree.node_count) if i not in ports)
        order = np.asarray(ports + middle)
        reordered = Y[:, order[:, None], order]
        R = reordered[:, :2, :2]
        if middle:
            U = reordered[:, :2, 2:]
            V = reordered[:, 2:, :2]
            E = reordered[:, 2:, 2:]
            if timing: timing[0].add(timing[1] + '/port/reorder', perf_counter_ns() - start)
            try:
                if timing: start, failed = perf_counter_ns(), False
                try:
                    internal = np.linalg.solve(E, V)
                except BaseException:
                    if timing: failed = True
                    raise
                finally:
                    if timing: timing[0].add(timing[1] + '/port/schur_solve', perf_counter_ns() - start, failed=failed)
                if timing: start = perf_counter_ns()
                R = R - U @ internal
                if timing: timing[0].add(timing[1] + '/port/schur_update', perf_counter_ns() - start)
            except np.linalg.LinAlgError as exc:
                raise CircuitNumericalError('schur_solve_failed', 'Internal-node Schur solve failed') from exc
        elif timing:
            timing[0].add(timing[1] + '/port/reorder', perf_counter_ns() - start)
        if not np.all(np.isfinite(R)):
            raise CircuitNumericalError('schur_nonfinite', 'Non-finite port admittance',
                sample_index=int(np.flatnonzero(~np.all(np.isfinite(R), axis=(1, 2)))[0]))
        if check_power:
            # Compare real power at the reduced ports with real power in the
            # full nodal system for any two-port voltage excitation.
            lift = np.broadcast_to(np.eye(2), (len(Y), 2, 2))
            if middle:
                lift = np.concatenate((lift, -internal), axis=1)

            def hermitian(a):
                return (a + a.conj().swapaxes(-1, -2)) / 2

            dissipated = lift.conj().swapaxes(-1, -2) @ hermitian(reordered) @ lift
            if not np.allclose(hermitian(R), dissipated, rtol=1e-9, atol=1e-10):
                raise CircuitNumericalError('schur_power_balance', 'Reduced circuit fails nodal power balance')
        return R


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
