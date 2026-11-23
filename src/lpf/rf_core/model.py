"""Policy-frozen RF model and power-wave response at the external ports.

Peak phasors, currents INTO both ports. Kurokawa waves:
 a=(V+Z I)/(2 sqrt(Re Z)), b=(V-conj(Z) I)/(2 sqrt(Re Z)).
With the specified Thevenin source and load, a2=0, GT=|S21|²;
GA=GT/(1-|S22|²) allows conjugate output matching with the source held
fixed. IL=-10 log10(GT), APL=-10 log10(GA), RL=-20 log10(|Sii|).
Exact zero gain/reflection gives +inf dB (not a numerical failure or floor).
"""
from collections import OrderedDict
from contextlib import nullcontext
from dataclasses import dataclass, field
import json
from time import perf_counter_ns
import numpy as np

from lpf.constraint_versions import load_constraint, constraint_fingerprint
from .port_parasitics import get_two_port_s
from lpf.topology_management import CircuitDefinition
from .coupled_lc import (
    CoupledLCTopology, ParameterVectorSchema, CircuitValues, _fixed_port_impedance,
)
from .nominal_parts import checked_inductor_metadata, checked_fixed_c_types
from lpf.topology_management import audit_variable_connection_roles
from .rft008_layout import RFT008CapacitorLayout, policy_edges
from lpf.constraint_versions import validate_variable_c_connections
from lpf.trial_shunt_dtc import shunt_dtc_parasitic_branches
from .numerical_diagnostics import CircuitNumericalError

# Installed only during the sequential development runner's deep Search.
_deep_timing = None


def _frozen(array, dtype):
    a = np.ascontiguousarray(array, dtype=dtype)
    # Immutable bytes backing, not merely a reversible writeable=False flag.
    return np.frombuffer(a.tobytes(), dtype=a.dtype).reshape(a.shape)


@dataclass(frozen=True)
class EvaluationGrid:
    """Explicit sample identity. segment 0..27 refers to rf/bands.csv row order.

    Additional planned intervals may use IDs >=28 (e.g. T006 3--6 GHz).
    This numeric layer does not compile requirements or merge intervals.
    """
    frequency_hz: np.ndarray
    setting: np.ndarray
    segment: np.ndarray

    def __post_init__(self):
        f, s, g = map(np.asarray, (self.frequency_hz, self.setting, self.segment))
        if (f.ndim != 1 or not f.size or f.dtype.kind not in 'fiu' or
                s.shape != f.shape or g.shape != f.shape or
                s.dtype.kind not in 'iu' or g.dtype.kind not in 'iu' or
                not np.all(np.isfinite(f)) or np.any(f <= 0) or
                np.any(s < 0) or np.any(s >= 6) or np.any(g < 0)):
            raise ValueError('Invalid frequency/setting/segment grid')
        for name, a, dtype in [('frequency_hz', f, np.float64),
                               ('setting', s, np.int64), ('segment', g, np.int64)]:
            object.__setattr__(self, name, _frozen(a, dtype))


@dataclass(frozen=True)
class RFResponse:
    grid: EvaluationGrid
    policy_id: str
    policy_fingerprint: str
    s: np.ndarray
    il_db: np.ndarray
    apl_db: np.ndarray
    in_rl_db: np.ndarray
    out_rl_db: np.ndarray
    independent_mna_checked: bool = False


def _adjoint(a):
    return a.conj().swapaxes(-1, -2)


def _wave_loss(s):
    return np.eye(2) - _adjoint(s) @ s


def power_response(s, zs, zl, *, check_power=False):
    """Renormalize original real-50-ohm S without changing Touchstone data."""
    s = np.asarray(s, dtype=np.complex128)
    if s.ndim != 3 or s.shape[1:] != (2, 2) or not np.all(np.isfinite(s)):
        raise ValueError('Expected finite S[N,2,2]')
    z = np.asarray([zs, zl], complex)
    if not np.all(np.isfinite(z)) or np.any(z.real <= 0):
        raise ValueError('Non-passive reference impedance')
    timing = _deep_timing
    if timing: start = perf_counter_ns()
    eye = np.eye(2)
    v = np.sqrt(50.) * (eye + s)
    i = (eye - s) / np.sqrt(50.)
    a = (v + z[None, :, None] * i) / (2*np.sqrt(z.real)[None, :, None])
    b = (v - z.conj()[None, :, None] * i) / (2*np.sqrt(z.real)[None, :, None])
    if timing: timing[0].add(timing[1] + '/power/wave_build', perf_counter_ns() - start)
    if timing: start, failed = perf_counter_ns(), False
    try:
        result = np.linalg.solve(a.transpose(0, 2, 1), b.transpose(0, 2, 1)).transpose(0, 2, 1)
    except np.linalg.LinAlgError as exc:
        if timing: failed = True
        raise CircuitNumericalError('wave_singular', 'Singular power-wave conversion') from exc
    except BaseException:
        if timing: failed = True
        raise
    finally:
        if timing: timing[0].add(timing[1] + '/power/wave_solve', perf_counter_ns() - start, failed=failed)
    if not np.all(np.isfinite(result)):
        raise CircuitNumericalError('wave_nonfinite', 'Non-finite power waves')
    if check_power:
        # Both normalized wave bases describe the same port voltages/currents.
        loss = _wave_loss(result)
        if (np.any(np.linalg.eigvalsh(loss) < -2e-8) or
                not np.allclose(_adjoint(a) @ loss @ a, _wave_loss(s), rtol=1e-9, atol=1e-10)):
            raise CircuitNumericalError('external_power_balance', 'External waves are non-passive or fail power balance')
    if timing: start = perf_counter_ns()
    magnitude = np.abs(result)
    if not np.all(np.isfinite(magnitude)):
        raise CircuitNumericalError('wave_nonfinite', 'Power-wave magnitude overflow')
    with np.errstate(over='ignore', invalid='ignore'):
        available = 1 - magnitude[:, 1, 1]**2
    if not np.all(np.isfinite(available)) or np.any(available <= 0):
        raise CircuitNumericalError('available_gain_undefined', 'No finite available output power')
    # Work in log amplitude: squaring S21 can underflow before the log.
    with np.errstate(divide='ignore'):
        il = -20*np.log10(magnitude[:, 1, 0])
        metrics = (il, il + 10*np.log10(available),
                   -20*np.log10(magnitude[:, 0, 0]),
                   -20*np.log10(magnitude[:, 1, 1]))
    if not np.all(np.concatenate(metrics) > -np.inf):
        raise CircuitNumericalError('db_invalid', 'Undefined dB response')
    if timing: timing[0].add(timing[1] + '/power/db_metrics', perf_counter_ns() - start)
    return (result, *metrics)


def _cascade(a, b, *, check_power=False):
    """Scalar two-port Redheffer product; valid even at transmission zeros."""
    den = 1-a[:, 1, 1]*b[:, 0, 0]
    if np.any(den == 0) or not np.all(np.isfinite(den)):
        raise CircuitNumericalError('cascade_singular', 'Singular S cascade')
    s = np.empty_like(a)
    s[:, 0, 0] = a[:, 0, 0] + a[:, 0, 1]*b[:, 0, 0]*a[:, 1, 0]/den
    s[:, 0, 1] = a[:, 0, 1]*b[:, 0, 1]/den
    s[:, 1, 0] = b[:, 1, 0]*a[:, 1, 0]/den
    s[:, 1, 1] = b[:, 1, 1] + b[:, 1, 0]*a[:, 1, 1]*b[:, 0, 1]/den
    if not np.all(np.isfinite(s)):
        raise CircuitNumericalError('cascade_nonfinite', 'Non-finite S cascade')
    if check_power:
        # Map the two external incident waves to each constituent's inputs.
        # Net power lost at the external ports must equal the sum of the two
        # absorber powers, for arbitrary excitation (including cross terms).
        in_b = np.zeros_like(s)
        in_b[:, 0, 0] = a[:, 1, 0] / den
        in_b[:, 0, 1] = a[:, 1, 1] * b[:, 0, 1] / den
        in_b[:, 1, 1] = 1
        in_a = np.zeros_like(s)
        in_a[:, 0, 0] = 1
        in_a[:, 1, :] = (b @ in_b)[:, 0, :]
        loss_a, loss_b, loss = _wave_loss(a), _wave_loss(b), _wave_loss(s)
        absorbed = _adjoint(in_a) @ loss_a @ in_a + _adjoint(in_b) @ loss_b @ in_b
        if (any(np.any(np.linalg.eigvalsh(d) < -2e-8) for d in (loss_a, loss_b, loss)) or
                not np.allclose(loss, absorbed, rtol=1e-9, atol=1e-10)):
            raise CircuitNumericalError('cascade_power_balance', 'Cascade is non-passive or fails power balance')
    return s


def _cascade_jacobian(a, da, b, db):
    """Differentiate the scalar Redheffer product without transmission division."""
    den = 1 - a[:, 1, 1] * b[:, 0, 0]
    dd = -(da[:, :, 1, 1] * b[:, None, 0, 0] + a[:, None, 1, 1] * db[:, :, 0, 0])

    def product(*terms):
        value = np.ones_like(den)
        for v, _ in terms:
            value *= v
        deriv = np.zeros_like(dd)
        for i, (_, d) in enumerate(terms):
            other = np.ones_like(den)
            for j, (v, _) in enumerate(terms):
                if i != j:
                    other *= v
            deriv += d * other[:, None]
        return deriv / den[:, None] - value[:, None] * dd / den[:, None]**2

    def A(i, j): return a[:, i, j], da[:, :, i, j]
    def B(i, j): return b[:, i, j], db[:, :, i, j]
    out = np.empty_like(da)
    out[:, :, 0, 0] = da[:, :, 0, 0] + product(A(0, 1), B(0, 0), A(1, 0))
    out[:, :, 0, 1] = product(A(0, 1), B(0, 1))
    out[:, :, 1, 0] = product(B(1, 0), A(1, 0))
    out[:, :, 1, 1] = db[:, :, 1, 1] + product(B(1, 0), A(1, 1), B(0, 1))
    return out


@dataclass(frozen=True)
class RFModel:
    definition: CircuitDefinition
    topology: CoupledLCTopology
    schema: ParameterVectorSchema
    policy_json: str
    policy_id: str
    policy_fingerprint: str

    @property
    def resolved_policy(self):
        return json.loads(self.policy_json)

    def decode(self, x):
        if np.asarray(x).dtype.kind not in 'fiu':
            raise ValueError('Expected numeric vector, not boolean/string/complex coercion')
        return self.schema.decode(x)

    def encode(self, values):
        return self.schema.encode(values)

    def evaluator(self, grid, *, cache_mode='off', cache_diagnostics=False):
        return RFEvaluator(self, grid, cache_mode=cache_mode, cache_diagnostics=cache_diagnostics)


@dataclass(frozen=True)
class RFEvaluator:
    model: RFModel
    grid: EvaluationGrid
    cache_mode: str = 'off'
    cache_diagnostics: bool = False
    pre: np.ndarray = field(init=False, repr=False)
    post: np.ndarray = field(init=False, repr=False)
    source_ohms: complex = field(init=False, repr=False)
    load_ohms: complex = field(init=False, repr=False)
    _lk_cache: object = field(init=False, repr=False, compare=False)
    _response_cache: object = field(init=False, repr=False, compare=False)
    _setting_indices: object = field(init=False, repr=False, compare=False)
    cache_stats: dict = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        if not isinstance(self.grid, EvaluationGrid):
            raise TypeError('Expected frozen EvaluationGrid')
        if self.cache_mode not in ('off', 'lk', 'response', 'both'):
            raise ValueError('Invalid RF cache mode')
        object.__setattr__(self, '_lk_cache', OrderedDict())
        object.__setattr__(self, '_response_cache', [OrderedDict() for _ in range(6)])
        object.__setattr__(self, '_setting_indices', tuple(np.flatnonzero(self.grid.setting == s) for s in range(6)))
        object.__setattr__(self, 'cache_stats', dict(lk_lookups=0, lk_hits=0, lk_misses=0,
            lk_computations=0, response_lookups=0, response_hits=0, response_misses=0,
            computed_samples=0, capacity=16))
        if self.cache_diagnostics:
            self.cache_stats['response_distribution'] = {
                name: dict(forwards=0, computed_samples=0)
                for name in ('all_miss', 'partial_hit', 'all_hit')}
        policy = self.model.resolved_policy
        object.__setattr__(self, 'source_ohms', _fixed_port_impedance(policy, 'source_ohms'))
        object.__setattr__(self, 'load_ohms', _fixed_port_impedance(policy, 'load_ohms'))
        for name, key in [('pre', 'input_parasitic'), ('post', 'output_parasitic')]:
            s = [get_two_port_s(policy, key, float(f)) for f in self.grid.frequency_hz]
            object.__setattr__(self, name, _frozen(s, np.complex128))

    def evaluate(self, x, *, check_power=False):
        m, g = self.model, self.grid
        if isinstance(x, CircuitValues):
            m.encode(x)  # Validate dimensions and setting-invariant capacitors.
            values = x
        else:
            values = m.decode(x)
        if check_power or self.cache_mode == 'off':
            data = self._compute(values, slice(None), check_power=check_power)
        else:
            data = self._cached(values)
        timing = _deep_timing
        if timing: start = perf_counter_ns()
        arrays = [_frozen(a, np.complex128 if j == 0 else np.float64)
                  for j, a in enumerate(data)]
        response = RFResponse(g, m.policy_id, m.policy_fingerprint, *arrays)
        if timing: timing[0].add(timing[1] + '/response_build', perf_counter_ns() - start)
        return response

    def evaluate_with_il_jacobian(self, x):
        """Return external-port response and dIL/dx in physical vector units.

        Sensitivities at zero transmission are undefined and fail closed.
        This independent path does not use the development runner caches.
        """
        m, g, topology = self.model, self.grid, self.model.topology
        values = m.decode(x)
        omega = 2*np.pi*g.frequency_hz
        matrices = topology.matrices(values)
        node = topology.node_admittance(values, omega, g.setting, matrices=matrices)
        n = topology.inductor_tree.node_count
        ports = (topology.inductor_tree.source_node, topology.inductor_tree.load_node)
        middle = tuple(i for i in range(n) if i not in ports)
        order = np.asarray(ports + middle)
        Y = node[:, order[:, None], order]
        R = Y[:, :2, :2]
        if middle:
            U, V, E = Y[:, :2, 2:], Y[:, 2:, :2], Y[:, 2:, 2:]
            try:
                internal = np.linalg.solve(E, V)
            except np.linalg.LinAlgError as exc:
                raise CircuitNumericalError('schur_solve_failed', 'Internal-node Schur solve failed') from exc
            R = R - U @ internal
        if not np.all(np.isfinite(R)):
            raise CircuitNumericalError('schur_nonfinite', 'Non-finite port admittance',
                sample_index=int(np.flatnonzero(~np.all(np.isfinite(R), axis=(1, 2)))[0]))
        eye = np.eye(2)
        A = eye + 50*R
        try:
            core = np.linalg.solve(A, eye - 50*R)
        except np.linalg.LinAlgError as exc:
            raise CircuitNumericalError('s_singular', 'Singular Y-to-S conversion') from exc
        first = _cascade(self.pre, core)
        full = _cascade(first, self.post)
        data = power_response(full, self.source_ohms, self.load_ohms)
        # Complete the original forward and its error checks before sensitivity.
        _, dY = topology.node_admittance_with_jacobian(
            values, m.schema, omega, g.setting, matrices=matrices, node=node)
        dY = dY[:, :, order[:, None], order]
        dR = dY[:, :, :2, :2]
        try:
            if middle:
                dU, dV, dE = dY[:, :, :2, 2:], dY[:, :, 2:, :2], dY[:, :, 2:, 2:]
                dX = np.linalg.solve(E[:, None], dV - dE @ internal[:, None])
                dR = dR - dU @ internal[:, None] - U[:, None] @ dX
            dcore = np.linalg.solve(A[:, None], -50*dR @ (eye + core[:, None]))
            zeros = np.zeros_like(dcore)
            dfirst = _cascade_jacobian(self.pre, zeros, core, dcore)
            dfull = _cascade_jacobian(first, dfirst, self.post, zeros)
            z = np.asarray([self.source_ohms, self.load_ohms])
            scale = (2*np.sqrt(z.real))[None, None, :, None]
            da = (np.sqrt(50.) - z[None, None, :, None]/np.sqrt(50.)) * dfull / scale
            db = (np.sqrt(50.) + z.conj()[None, None, :, None]/np.sqrt(50.)) * dfull / scale
            v = np.sqrt(50.) * (eye + full)
            i = (eye - full) / np.sqrt(50.)
            a = (v + z[None, :, None]*i) / (2*np.sqrt(z.real)[None, :, None])
            ds = np.linalg.solve(a[:, None].swapaxes(-1, -2),
                (db - data[0][:, None] @ da).swapaxes(-1, -2)).swapaxes(-1, -2)
        except np.linalg.LinAlgError as exc:
            raise CircuitNumericalError('sensitivity_solve_failed', 'RF sensitivity solve failed') from exc
        transmission = data[0][:, 1, 0]
        if np.any(transmission == 0):
            raise CircuitNumericalError('sensitivity_zero_transmission', 'IL derivative undefined at zero transmission')
        with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
            jac = -20/np.log(10) * np.real(ds[:, :, 1, 0] / transmission[:, None])
        if not np.all(np.isfinite(jac)):
            raise CircuitNumericalError('sensitivity_nonfinite', 'Non-finite IL sensitivity')
        arrays = [_frozen(a, np.complex128 if j == 0 else np.float64) for j, a in enumerate(data)]
        return RFResponse(g, m.policy_id, m.policy_fingerprint, *arrays), _frozen(jac, np.float64)

    def evaluate_batch(self, vectors):
        """Evaluate a candidate-major batch on the Search grid.

        Failures are replayed in candidate order through the scalar path so its
        error precedence and sample indices remain authoritative. The L/k LRU
        and counters are committed only after the whole vectorized calculation.
        """
        x = np.asarray(vectors)
        if (x.ndim != 2 or not len(x) or x.shape[1] != self.model.schema.vector_length
                or x.dtype.kind not in 'fiu'):
            raise ValueError('Expected real numeric vectors[B, vector_length], B >= 1')
        if self.cache_mode in ('response', 'both'):
            return tuple(self.evaluate(row) for row in x)
        try:
            return self._compute_batch(x)
        except (ValueError, np.linalg.LinAlgError, FloatingPointError):
            return tuple(self.evaluate(row) for row in x)

    def evaluate_partial_batch(self, vectors, base_response, mask):
        """Evaluate selected candidate/grid pairs, filling the rest from base_response.

        The caller must select every sample affected by each candidate. Failures
        replay complete candidates in order, just like evaluate_batch.
        """
        x = np.asarray(vectors)
        if (x.ndim != 2 or not len(x) or x.shape[1] != self.model.schema.vector_length
                or x.dtype.kind not in 'fiu'):
            raise ValueError('Expected real numeric vectors[B, vector_length], B >= 1')
        mask = np.asarray(mask)
        if mask.dtype != np.bool_ or mask.shape != (len(x), len(self.grid.setting)):
            raise ValueError('Expected boolean candidate/sample mask')
        if (not isinstance(base_response, RFResponse) or base_response.grid is not self.grid or
                base_response.policy_id != self.model.policy_id or
                base_response.policy_fingerprint != self.model.policy_fingerprint):
            raise ValueError('Base response profile/grid mismatch')
        if self.cache_mode in ('response', 'both'):
            return self.evaluate_batch(x)
        try:
            return self._compute_batch(x, mask=mask, base_response=base_response)
        except (ValueError, np.linalg.LinAlgError, FloatingPointError):
            return tuple(self.evaluate(row) for row in x)

    def _compute_batch(self, x, *, mask=None, base_response=None):
        m, g, topology = self.model, self.grid, self.model.topology
        timing = _deep_timing
        with timing[0].measure(timing[1] + '/batch/decode_lk') if timing else nullcontext():
            with timing[0].measure(timing[1] + '/batch/decode') if timing else nullcontext():
                L, k, C = m.schema.decode_batch(x)
            if (L.shape[1] != len(topology.inductor_tree.edges) or
                    k.shape[1] != len(topology.coupling_pairs)):
                raise ValueError('L/k dimensions do not match topology')
            # Stage LRU mutations so even a late wave/Schur failure cannot cache
            # matrices belonging to a failed evaluation.
            cache = self._lk_cache.copy()
            hits = misses = computations = 0
            numerators = []
            for inductances, coupling in zip(L, k):
                if self.cache_mode == 'lk':
                    key = np.concatenate((inductances, coupling)).tobytes()
                    if key in cache:
                        hits += 1
                        cache.move_to_end(key)
                        matrices = cache[key]
                    else:
                        misses += 1
                        computations += 1
                        matrices = topology._matrices_lk(inductances, coupling)
                        self._put(cache, key, matrices)
                else:
                    computations += 1
                    matrices = topology._matrices_lk(inductances, coupling)
                numerators.append(matrices[0])
        with timing[0].measure(timing[1] + '/batch/select') if timing else nullcontext():
            if mask is None:
                candidates = np.repeat(np.arange(len(x)), len(g.setting))
                samples = np.tile(np.arange(len(g.setting)), len(x))
            else:
                candidates, samples = np.nonzero(mask)
            # Count attempted selected samples even if a later numerical stage
            # fails and scalar replay is needed, matching scalar _compute's counter.
            if mask is not None:
                self.cache_stats['computed_samples'] += len(samples)
        with timing[0].measure(timing[1] + '/batch/stamp') if timing else nullcontext():
            omega = 2*np.pi*g.frequency_hz[samples]
            n = topology.inductor_tree.node_count
            D = (C @ topology._capacitor_stamps_flat).reshape(len(x), 6, n, n)[candidates, g.setting[samples]]
            Y = np.asarray(numerators)[candidates] / (omega[:, None, None] * 1e-9)
            Y = Y + omega[:, None, None] * D
            if not np.all(np.isfinite(Y)):
                raise ValueError('Non-finite batch nodal admittance')
            ports = (topology.inductor_tree.source_node, topology.inductor_tree.load_node)
            middle = tuple(i for i in range(n) if i not in ports)
            order = np.asarray(ports + middle)
            Y = Y[..., order[:, None], order]
            r = Y[..., :2, :2]
        if middle:
            with timing[0].measure(timing[1] + '/batch/schur_solve') if timing else nullcontext():
                solved = np.linalg.solve(Y[..., 2:, 2:], Y[..., 2:, :2])
            with timing[0].measure(timing[1] + '/batch/schur_update') if timing else nullcontext():
                r = r - Y[..., :2, 2:] @ solved
        with timing[0].measure(timing[1] + '/batch/y_to_s') if timing else nullcontext():
            if not np.all(np.isfinite(r)):
                raise ValueError('Non-finite batch port admittance')
            eye = np.eye(2)
            core = np.linalg.solve(eye + 50*r, eye - 50*r).reshape(-1, 2, 2)
        data = power_response(_cascade(_cascade(self.pre[samples], core), self.post[samples]),
                              self.source_ohms, self.load_ohms)
        with timing[0].measure(timing[1] + '/batch/output') if timing else nullcontext():
            if mask is None:
                data = [a.reshape(len(x), len(g.setting), *a.shape[1:]) for a in data]
            else:
                names = ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db')
                assembled = [np.broadcast_to(getattr(base_response, name), (len(x), *getattr(base_response, name).shape)).copy()
                             for name in names]
                for dest, src in zip(assembled, data):
                    dest[candidates, samples] = src
                data = assembled
            responses = tuple(RFResponse(g, m.policy_id, m.policy_fingerprint,
                *(_frozen(a[i], np.complex128 if j == 0 else np.float64)
                  for j, a in enumerate(data))) for i in range(len(x)))
            if self.cache_mode == 'lk':
                self._lk_cache.clear()
                self._lk_cache.update(cache)
                self.cache_stats['lk_lookups'] += len(x)
                self.cache_stats['lk_hits'] += hits
                self.cache_stats['lk_misses'] += misses
            self.cache_stats['lk_computations'] += computations
            if mask is None:
                self.cache_stats['computed_samples'] += len(samples)
        return responses

    @staticmethod
    def _put(cache, key, value):
        cache[key] = value
        cache.move_to_end(key)
        if len(cache) > 16:
            cache.popitem(last=False)

    def _cached(self, values):
        g, stats, timing = self.grid, self.cache_stats, _deep_timing
        if timing: start = perf_counter_ns()
        lk_key = np.asarray(values.inductances_nh + values.coupling_k, dtype=np.float64).tobytes()
        use_response = self.cache_mode in ('response', 'both')
        use_lk = self.cache_mode in ('lk', 'both')
        lk_ns = perf_counter_ns() - start if timing else 0
        keys, hits, missing_settings = {}, {}, []
        if use_response:
            if timing: start = perf_counter_ns()
            for setting, indices in enumerate(self._setting_indices):
                if not len(indices):
                    continue
                key = lk_key + np.asarray(values.capacitors_pf_by_setting[setting], dtype=np.float64).tobytes()
                keys[setting] = key
                cache = self._response_cache[setting]
                stats['response_lookups'] += 1
                if key in cache:
                    stats['response_hits'] += 1
                    cache.move_to_end(key)
                    hits[setting] = cache[key]
                else:
                    stats['response_misses'] += 1
                    missing_settings.append(setting)
            if timing: timing[0].add(timing[1] + '/cache/response_lookup', perf_counter_ns() - start)
            distribution = stats.get('response_distribution')
            if distribution is not None:
                category = 'all_miss' if not hits else ('all_hit' if not missing_settings else 'partial_hit')
                distribution = distribution[category]
                distribution['forwards'] += 1
        else:
            distribution = None
        if not use_response or missing_settings:
            if timing: start = perf_counter_ns()
            indices = (np.sort(np.asarray([i for s in missing_settings for i in self._setting_indices[s]], dtype=int))
                       if use_response else slice(None))
            if timing and use_response: timing[0].add(timing[1] + '/cache/missing_select', perf_counter_ns() - start)
            matrices = None
            if use_lk:
                if timing: start = perf_counter_ns()
                stats['lk_lookups'] += 1
                if lk_key in self._lk_cache:
                    stats['lk_hits'] += 1
                    self._lk_cache.move_to_end(lk_key)
                    matrices = self._lk_cache[lk_key]
                else:
                    stats['lk_misses'] += 1
                if timing: lk_ns += perf_counter_ns() - start
            if timing:
                timing[0].add(timing[1] + '/cache/lk_lookup', lk_ns)
                start, failed = perf_counter_ns(), False
            try:
                if use_lk and matrices is None:
                    stats['lk_computations'] += 1
                    matrices = self.model.topology.matrices(values)
                try:
                    if distribution is not None: distribution['computed_samples'] += len(indices)
                    data = self._compute(values, indices, matrices=matrices)
                except (ValueError, np.linalg.LinAlgError):
                    # Re-run the original full grid to preserve error precedence and sample_index.
                    if use_response and len(indices) != len(g.setting):
                        if distribution is not None: distribution['computed_samples'] += len(g.setting)
                        return self._compute(values, slice(None))
                    raise
            except BaseException:
                if timing: failed = True
                raise
            finally:
                if timing: timing[0].add(timing[1] + '/cache/missing_compute', perf_counter_ns() - start, failed=failed)
            if timing: start = perf_counter_ns()
            if use_lk:
                self._put(self._lk_cache, lk_key, matrices)
            if use_response:
                for setting in missing_settings:
                    positions = np.searchsorted(indices, self._setting_indices[setting])
                    entry = tuple(_frozen(a[positions], a.dtype) for a in data)
                    self._put(self._response_cache[setting], keys[setting], entry)
                    hits[setting] = entry
            if timing: timing[0].add(timing[1] + '/cache/store', perf_counter_ns() - start)
            if not use_response or len(missing_settings) == len(keys):
                # All grid rows were computed in original order; caches own frozen copies.
                return data
        elif timing:
            timing[0].add(timing[1] + '/cache/lk_lookup', lk_ns)
        if timing: start = perf_counter_ns()
        result = [np.empty((len(g.setting), 2, 2), complex)] + [np.empty(len(g.setting)) for _ in range(4)]
        for setting, entry in hits.items():
            positions = self._setting_indices[setting]
            for dest, src in zip(result, entry):
                dest[positions] = src
        if timing: timing[0].add(timing[1] + '/cache/assemble', perf_counter_ns() - start)
        return tuple(result)

    def _compute(self, values, indices, *, check_power=False, matrices=None):
        m, g = self.model, self.grid
        self.cache_stats['computed_samples'] += len(g.setting) if isinstance(indices, slice) else len(indices)
        if matrices is None:
            self.cache_stats['lk_computations'] += 1
        kwargs = {}
        if check_power: kwargs['check_power'] = True
        if matrices is not None: kwargs['matrices'] = matrices
        r = m.topology.port_admittance(values, 2*np.pi*g.frequency_hz[indices], g.setting[indices], **kwargs)
        eye = np.eye(2)
        timing = _deep_timing
        if timing: start, failed = perf_counter_ns(), False
        try:
            try:
                core = np.linalg.solve(eye + 50*r, eye - 50*r)
            except BaseException:
                if timing: failed = True
                raise
        except np.linalg.LinAlgError as exc:
            raise CircuitNumericalError('s_singular', 'Singular Y-to-S conversion') from exc
        finally:
            if timing: timing[0].add(timing[1] + '/y_to_s_solve', perf_counter_ns() - start, failed=failed)
        if check_power:
            voltage = np.sqrt(50.) * (eye + core)
            absorbed = _adjoint(voltage) @ ((r + _adjoint(r)) / 2) @ voltage
            if not np.allclose(_wave_loss(core), absorbed, rtol=1e-9, atol=1e-10):
                raise CircuitNumericalError('core_power_balance', 'Core power waves fail nodal power balance')
        full = _cascade(_cascade(self.pre[indices], core, check_power=check_power), self.post[indices], check_power=check_power)
        return power_response(full, self.source_ohms, self.load_ohms, check_power=check_power)


def build_rf_model(definition, policy):
    """One physical stamp builder, no RF-ID-specific forward classes.

    Trial opt-in is performed by load_constraint(..., allow_trial=True).
    Only that exact approved resolved policy is accepted here.
    Design bounds/SPD acceptance remains search.component_constraints' job.
    """
    if not isinstance(definition, CircuitDefinition) or not isinstance(policy, dict):
        raise TypeError('Expected CircuitDefinition and resolved policy')
    cid = policy.get('active_constraint_id')
    if cid not in ('RF-F003', 'RF-T005', 'RF-T006', 'RF-T007', 'RF-T008'):
        raise ValueError('Unsupported current physical model')
    approved = load_constraint(cid, allow_trial=True)
    fingerprint = constraint_fingerprint(policy)
    if policy.get('schema_version') != 2 or fingerprint != constraint_fingerprint(approved):
        raise ValueError('Policy differs from approved current schema/model')
    d, p = definition, definition.capacitor_placement
    _, _, lq = checked_inductor_metadata(policy, d.inductor_tree, d.inductor_types, d.physical_order)
    types = checked_fixed_c_types(p.fixed_edges, d.fixed_c_types)
    roles = audit_variable_connection_roles(d.inductor_tree, p.variable_edges, d.variable_roles)
    if not roles.as_dict()['all_declared_roles_supported_by_l_tree']:
        raise ValueError('Connection role not proven by L tree')
    variable = policy_edges(p.variable_edges, roles=d.variable_roles)
    validate_variable_c_connections(variable, policy)
    constants, extra_edges, extra_q = (), (), ()
    if 'trial_ic_fixed_c_by_connection' in policy:
        layout = RFT008CapacitorLayout.for_policy(policy, p,
            tuple(i for i, t in enumerate(types) if t == 'GJM01'), variable_roles=d.variable_roles)
        edges, cq = p.edges, layout.q
    else:
        if p.ic_fixed_edges:
            raise ValueError('IC fixed C requires explicit physical model')
        if 'trial_shunt_dtc_parasitic' in policy:
            extras = shunt_dtc_parasitic_branches(policy, variable)
            constants = tuple(float(e['capacitance_pf']) for e in extras)
            extra_edges = tuple((int(e['node'])-1, -1) for e in extras)
            extra_q = tuple(float(e['q']) for e in extras)
        if types.count('PCB_PATTERN_C') > policy['components']['PCB_PATTERN_C']['max_count']:
            raise ValueError('Too many PCB capacitors')
        cq = tuple(float(policy['components'][t]['q']) for t in types)
        cq += (float(policy['components']['IC_VARIABLE_C']['q']),)*len(p.variable_edges) + extra_q
        edges = p.fixed_edges + p.variable_edges + extra_edges
    topology = CoupledLCTopology(d.inductor_tree, d.coupling_pairs, lq, edges, cq)
    schema = ParameterVectorSchema(len(d.inductor_tree.edges), len(p.fixed_edges),
        len(d.coupling_pairs), len(p.ic_fixed_edges), len(p.variable_edges), constants)
    return RFModel(d, topology, schema, json.dumps(policy, sort_keys=True, allow_nan=False),
                   cid, fingerprint)
