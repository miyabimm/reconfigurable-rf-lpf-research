"""Single strict YAML schema; read-only preflight is not G0/G1 approval."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import yaml

from lpf.constraint_versions import rf_input_file
from .problem import build, nominal_area
from .starts import physical_box
from .storage import canonical, sha

ROOT = Path(__file__).resolve().parents[3]


class Loader(yaml.SafeLoader):
    pass


def mapping(loader, node):
    result = {}
    for k, v in node.value:
        key = loader.construct_object(k)
        if key in result:
            raise ValueError(f'Duplicate YAML key: {key}')
        result[key] = loader.construct_object(v)
    return result


Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)


def fields(value, names):
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise ValueError(f'Expected exactly: {names}')


def positive(value):
    if type(value) is not int or value < 1:
        raise ValueError('Positive integer required')


@dataclass(frozen=True)
class Plan:
    frozen_json: str
    sha256: str

    @property
    def data(self):
        return json.loads(self.frozen_json)


def load(path, root=ROOT):
    root = Path(root).resolve()
    with Path(path).open() as stream:
        d = yaml.load(stream, Loader=Loader)
    fields(d, 'schema_version rf objective definition seeds arms max_trial_requested_samples selection validation storage anytime_samples')
    if type(d['schema_version']) is not int or d['schema_version'] != 1 or d['objective'] != 'full_lpf':
        raise ValueError('Only schema 1 / full_lpf supported')
    fields(d['definition'], 'path source_sha256 definition_sha256')
    ref = d['definition']
    source = (root / ref['path']).resolve()
    if not source.is_relative_to(root):
        raise ValueError('Definition must be repository-local')
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ref['source_sha256']:
        raise ValueError('Definition source SHA mismatch')
    definition = json.loads(raw)
    c = build(definition, d['rf'])
    from dataclasses import asdict
    if sha(asdict(c.definition)) != ref['definition_sha256']:
        raise ValueError('Definition canonical SHA mismatch')
    seeds = d['seeds']
    if (not isinstance(seeds, list) or not seeds or
            any(type(s) is not int or s < 0 for s in seeds) or len(set(seeds)) != len(seeds)):
        raise ValueError('Unique nonnegative Sobol seeds required')
    if d['selection'] != {'rule': 'strict_vmax_vsum_il_sha', 'top_k': 1, 'points_per_interval': 3}:
        raise ValueError('Only fixed fine3 strict best-1 selector supported')
    if d['validation'] != {'terminal_points': 17, 'dense_points': 1001, 'production': 'not_ready'}:
        raise ValueError('Validation boundary must remain explicit not_ready')
    if d['storage'] != {'policy': 'phase2-git-only-v1', 'retain': 'all_fixture_raw', 'production': 'not_ready'}:
        raise ValueError('Unsupported storage policy')
    positive(d['max_trial_requested_samples'])
    milestones = d['anytime_samples']
    if (not isinstance(milestones, list) or any(type(v) is not int or v < 1 for v in milestones) or
            milestones != sorted(set(milestones))):
        raise ValueError('Anytime milestones must be increasing positive samples')
    arms = d['arms']
    if not isinstance(arms, list) or not arms:
        raise ValueError('Named fixed arms required')
    names = set()
    for arm in arms:
        fields(arm, 'name steps max_requested_samples')
        if (not isinstance(arm['name'], str) or not arm['name'].isidentifier() or arm['name'] in names):
            raise ValueError('Unique identifier arm names required')
        names.add(arm['name'])
        positive(arm['max_requested_samples'])
        if arm['max_requested_samples'] < 476:
            raise ValueError('Terminal476 reservation required')
        steps = arm['steps']
        if not isinstance(steps, list) or [s.get('solver') for s in steps] not in (
                ['slsqp'], ['hybrid'], ['slp'], ['hybrid', 'slp']):
            raise ValueError('Unsupported fixed solver sequence')
        for step in steps:
            fields(step, 'name solver aggregation points_per_interval max_requested_samples options')
            if not isinstance(step['name'], str) or not step['name'].isidentifier():
                raise ValueError('Named steps required')
            positive(step['max_requested_samples'])
            if step['points_per_interval'] not in (2, 3) or type(step['points_per_interval']) is not int:
                raise ValueError('Search supports only explicit coarse2/fine3')
            solver, agg, options = step['solver'], step['aggregation'], step['options']
            if solver == 'hybrid':
                if agg not in ('sum', 'max'):
                    raise ValueError('Hybrid requires squared sum/max')
                fields(options, 'maxiter max_restarts max_evaluations restart_sigma')
                positive(options['maxiter'])
                if type(options['max_restarts']) is not int or options['max_restarts'] < 0:
                    raise ValueError('Invalid restart count')
                sigma = options['restart_sigma']
                if type(sigma) not in (int, float) or not 0 < sigma <= 1:
                    raise ValueError('Invalid restart sigma')
            else:
                if agg not in (('sum', 'max') if solver == 'slsqp' else ('signed_max',)):
                    raise ValueError('Unsupported solver/objective: signed max is not squared max')
                fields(options, 'max_iterations max_evaluations')
                positive(options['max_iterations'])
            positive(options['max_evaluations'])
            # Freeze the generic solver defaults as reconstruction data too.
            if solver == 'slsqp':
                options.update(tolerance=1e-9, constraint_tolerance=1e-7)
            elif solver == 'slp':
                options.update(initial_step=.25, min_step=1e-8, fd_step=1e-6,
                               tolerance=1e-7, constraint_tolerance=1e-7)
            if step['max_requested_samples'] > arm['max_requested_samples'] - 476:
                raise ValueError('Stage allowance invades terminal reservation')
        if len({s['name'] for s in steps}) != len(steps):
            raise ValueError('Duplicate step names')
    if sum(a['max_requested_samples'] for a in arms) > d['max_trial_requested_samples']:
        raise ValueError('Trial cannot reserve all fixed jobs')
    if any(m >= min(a['max_requested_samples'] for a in arms) - 476 for m in milestones):
        raise ValueError('Anytime milestones invade terminal reservation')
    p = c.resolved_policy
    inputs = fingerprints(c, root)
    bounds, opened = physical_box(c)
    frozen = {'config': d, 'definition': asdict(c.definition), 'rf_inputs': inputs,
              'nominal_area': nominal_area(c),
              'box': bounds, 'open_lower': opened,
              'working_stop_db': p['evaluation']['full_phase2']['minimum_h2_h3_db'],
              'mathematics': {'scale_db': 1., 'weights': 'all_one',
                              'residuals': '[IL_pass, max(0,target-IL_stop)]',
                              'errors': 'IL_pass', 'constraints': 'IL_stop-target >= 0'},
              'gates': {'G0_G1': 'not_ready', 'G2_G5': 'not_ready'}}
    return Plan(canonical(frozen), sha(frozen))


def fingerprints(circuit, root=ROOT):
    p = circuit.resolved_policy
    inputs = {'bands': hashlib.sha256(rf_input_file(root, p['bands_file']).read_bytes()).hexdigest()}
    for key in ('input_parasitic', 'output_parasitic'):
        spec = p['external_port_parasitics'][key]
        actual = hashlib.sha256(rf_input_file(root, spec['path']).read_bytes()).hexdigest()
        if actual != spec['sha256']:
            raise ValueError('Fixed S2P SHA mismatch')
        inputs[key] = actual
    return inputs
