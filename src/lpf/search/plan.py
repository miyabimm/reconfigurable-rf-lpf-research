"""Single strict YAML schema; read-only preflight is not G0/G1 approval."""
from dataclasses import dataclass
import json
import math
from pathlib import Path
import yaml

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


def validate_solver(step):
    solver, agg, options = step['solver'], step['aggregation'], step['options']
    if solver == 'hybrid':
        fields(options, 'max_search_forwards' + ''.join(
            f' {name}' for name in ('restart_sigma', 'batch_fd', 'partial_fd')
            if isinstance(options, dict) and name in options))
        positive(options['max_search_forwards'])
        if 'batch_fd' in options and type(options['batch_fd']) is not bool:
            raise ValueError('batch_fd must be boolean')
        if 'partial_fd' in options and type(options['partial_fd']) is not bool:
            raise ValueError('partial_fd must be boolean')
        if options.get('partial_fd', False) and not options.get('batch_fd', True):
            raise ValueError('partial_fd requires batch_fd')
        if 'restart_sigma' in options:
            sigma = options['restart_sigma']
            try:
                valid = type(sigma) in (int, float) and math.isfinite(sigma) and sigma > 0
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError('restart_sigma must be finite and positive')
    elif solver == 'trf':
        fields(options, 'max_evaluations')
        if step.get('objective') != 'signed_margin_db':
            raise ValueError('TRF requires signed_margin_db')
    elif solver in ('slsqp', 'slp'):
        fields(options, 'max_iterations max_evaluations')
        positive(options['max_iterations'])
    else:
        raise ValueError('Unknown solver')
    if agg not in (('signed_max',) if solver == 'slp' else ('sum',) if solver == 'trf' else ('sum', 'max')):
        raise ValueError('Unknown solver aggregation')
    if solver != 'hybrid':
        positive(options['max_evaluations'])


def grid_from_record(record):
    from ..rf_core.model import EvaluationGrid
    from .performance import grid_fingerprint
    grid = EvaluationGrid(record['frequency_hz'], record['setting'], record['segment'])
    if grid_fingerprint(grid) != record['sha256']:
        raise ValueError('Frozen grid SHA mismatch')
    return grid


@dataclass(frozen=True)
class Plan:
    frozen_json: str
    sha256: str

    @property
    def data(self):
        return json.loads(self.frozen_json)

    def requested_grid(self, name):
        """Reconstruct a Stage-4A request independently of any RF response."""
        return grid_from_record(self.data['grids'][name])


def load_preflight(path, root=ROOT):
    """Stage-4A static schema2 YAML API.

    See project/diagnostics/issue313_preflight.md for the single new schema.
    No circuit construction, solver execution, EXP storage or gate approval.
    """
    from .preflight import freeze
    with Path(path).open() as stream:
        config = yaml.load(stream, Loader=Loader)
    frozen = freeze(config, Path(root).resolve())
    return Plan(canonical(frozen), sha(frozen))
