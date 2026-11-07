"""Single strict YAML schema; read-only preflight is not G0/G1 approval."""
from dataclasses import dataclass
import json
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


@dataclass(frozen=True)
class Plan:
    frozen_json: str
    sha256: str

    @property
    def data(self):
        return json.loads(self.frozen_json)

    def requested_grid(self, name):
        """Reconstruct a Stage-4A request independently of any RF response."""
        from ..rf_core.model import EvaluationGrid
        from .performance import grid_fingerprint
        record = self.data['grids'][name]
        grid = EvaluationGrid(record['frequency_hz'], record['setting'], record['segment'])
        if grid_fingerprint(grid) != record['sha256']:
            raise ValueError('Frozen grid SHA mismatch')
        return grid


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
