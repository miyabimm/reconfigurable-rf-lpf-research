"""Policy-frozen RF model and power-wave response at the external ports.

Peak phasors, currents INTO both ports. Kurokawa waves:
 a=(V+Z I)/(2 sqrt(Re Z)), b=(V-conj(Z) I)/(2 sqrt(Re Z)).
With the specified Thevenin source and load, a2=0, GT=|S21|²;
GA=GT/(1-|S22|²) allows conjugate output matching with the source held
fixed. IL=-10 log10(GT), APL=-10 log10(GA), RL=-20 log10(|Sii|).
Exact zero gain/reflection gives +inf dB (not a numerical failure or floor).
"""
from dataclasses import dataclass, field
import json
import numpy as np

from lpf.constraint_versions import load_constraint, constraint_fingerprint
from lpf.port_parasitics import get_two_port_s
from lpf.phase2_models.api import CircuitDefinition
from lpf.phase2_models.coupled_lc import (
    CoupledLCTopology, ParameterVectorSchema, CircuitValues, _fixed_port_impedance,
)
from lpf.phase2_models.nominal_parts import checked_inductor_metadata, checked_fixed_c_types
from lpf.phase2_models.role_audit import audit_variable_connection_roles
from lpf.phase2_models.rft008_layout import RFT008CapacitorLayout, policy_edges
from lpf.constraint_versions import validate_variable_c_connections
from lpf.trial_shunt_dtc import shunt_dtc_parasitic_branches
from lpf.phase2_models.numerical_diagnostics import CircuitNumericalError


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


def power_response(s, zs, zl):
    """Renormalize original real-50-ohm S without changing Touchstone data."""
    s = np.asarray(s, dtype=np.complex128)
    if s.ndim != 3 or s.shape[1:] != (2, 2) or not np.all(np.isfinite(s)):
        raise ValueError('Expected finite S[N,2,2]')
    z = np.asarray([zs, zl], complex)
    if not np.all(np.isfinite(z)) or np.any(z.real <= 0):
        raise ValueError('Non-passive reference impedance')
    eye = np.eye(2)
    v = np.sqrt(50.) * (eye + s)
    i = (eye - s) / np.sqrt(50.)
    a = (v + z[None, :, None] * i) / (2*np.sqrt(z.real)[None, :, None])
    b = (v - z.conj()[None, :, None] * i) / (2*np.sqrt(z.real)[None, :, None])
    try:
        result = np.linalg.solve(a.transpose(0, 2, 1), b.transpose(0, 2, 1)).transpose(0, 2, 1)
    except np.linalg.LinAlgError as exc:
        raise CircuitNumericalError('wave_singular', 'Singular power-wave conversion') from exc
    if not np.all(np.isfinite(result)):
        raise CircuitNumericalError('wave_nonfinite', 'Non-finite power waves')
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
    if any(np.any(np.isnan(m)) for m in metrics):
        raise CircuitNumericalError('db_invalid', 'Undefined dB response')
    return (result, *metrics)


def _cascade(a, b):
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
    return s


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

    def evaluator(self, grid):
        return RFEvaluator(self, grid)


@dataclass(frozen=True)
class RFEvaluator:
    model: RFModel
    grid: EvaluationGrid
    pre: np.ndarray = field(init=False, repr=False)
    post: np.ndarray = field(init=False, repr=False)

    def __post_init__(self):
        if not isinstance(self.grid, EvaluationGrid):
            raise TypeError('Expected frozen EvaluationGrid')
        policy = self.model.resolved_policy
        for name, key in [('pre', 'input_parasitic'), ('post', 'output_parasitic')]:
            s = [get_two_port_s(policy, key, float(f)) for f in self.grid.frequency_hz]
            object.__setattr__(self, name, _frozen(s, np.complex128))

    def evaluate(self, x):
        m, g = self.model, self.grid
        values = x if isinstance(x, CircuitValues) else m.decode(x)
        m.encode(values)
        r = m.topology.port_admittance(values, 2*np.pi*g.frequency_hz, g.setting)
        eye = np.eye(2)
        try:
            core = np.linalg.solve(eye + 50*r, eye - 50*r)
        except np.linalg.LinAlgError as exc:
            raise CircuitNumericalError('s_singular', 'Singular Y-to-S conversion') from exc
        full = _cascade(_cascade(self.pre, core), self.post)
        p = m.resolved_policy
        data = power_response(full, _fixed_port_impedance(p, 'source_ohms'),
                              _fixed_port_impedance(p, 'load_ohms'))
        arrays = [_frozen(a, np.complex128 if j == 0 else np.float64)
                  for j, a in enumerate(data)]
        return RFResponse(g, m.policy_id, m.policy_fingerprint, *arrays)


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
