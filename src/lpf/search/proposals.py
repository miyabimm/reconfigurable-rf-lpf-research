"""Data-only topology proposals; no execution authority or second circuit DSL."""
from dataclasses import asdict, fields as dataclass_fields
import re

import yaml

from lpf.topology_management import CircuitDefinition, InductorTree, CapacitorPlacement
from .plan import Loader, fields
from .storage import sha


def definition_from_data(data):
    """Strictly decode the existing dataclasses, retaining branch/slot order."""
    def exact(value, cls):
        fields(value, ' '.join(f.name for f in dataclass_fields(cls)))

    exact(data, CircuitDefinition)
    tree, caps = data['inductor_tree'], data['capacitor_placement']
    exact(tree, InductorTree)
    exact(caps, CapacitorPlacement)
    for key in ('inductor_types', 'fixed_c_types', 'variable_roles'):
        if not isinstance(data[key], list) or any(type(v) is not str for v in data[key]):
            raise ValueError(f'Expected string list: {key}')
    for key in ('physical_order',):
        if not isinstance(data[key], list) or any(type(v) is not int for v in data[key]):
            raise ValueError(f'Expected integer list: {key}')
    for value, keys in ((tree, ('edges',)), (caps, ('fixed_edges', 'variable_edges', 'ic_fixed_edges')),
                        (data, ('coupling_pairs',))):
        for key in keys:
            if (not isinstance(value[key], list) or any(not isinstance(pair, list) or len(pair) != 2
                    or any(type(v) is not int for v in pair) for pair in value[key])):
                raise ValueError(f'Expected ordered integer pairs: {key}')
    return CircuitDefinition(**{**data, 'inductor_tree': InductorTree(**tree),
                                'capacitor_placement': CapacitorPlacement(**caps)})


def normalize_proposal(data):
    # The issue's "4 keys" means the four payload keys plus schema_version.
    fields(data, 'schema_version proposal_id based_on_state_sha256 reason definition')
    if type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise ValueError('Proposal schema_version must be 1')
    if (type(data['proposal_id']) is not str or not data['proposal_id'].isidentifier() or
            type(data['reason']) is not str or not data['reason'].strip()):
        raise ValueError('Proposal identifier and nonempty reason required')
    if (type(data['based_on_state_sha256']) is not str or
            not re.fullmatch('[0-9a-f]{64}', data['based_on_state_sha256'])):
        raise ValueError('Actual canonical state SHA-256 required')
    definition = definition_from_data(data['definition'])
    normalized = {**data, 'definition': asdict(definition)}
    return normalized, definition, sha(normalized), sha(asdict(definition))


def load_proposal(path):
    """SafeLoader rejects tags/duplicate keys; exact decoding rejects NaN/types."""
    with open(path) as stream:
        data = yaml.load(stream, Loader=Loader)
    normalized, _, _, _ = normalize_proposal(data)
    # JSON-shaped data is the sole public input, not mutable circuit objects.
    from .storage import plain
    return plain(normalized)
