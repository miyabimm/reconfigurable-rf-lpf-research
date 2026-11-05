"""Read-only historical evidence identity checks, NOT an execution RF loader.

Never resolves trial overrides, converts schemas, promotes an ID, or supplies
constraints to a new run. Current execution uses constraint_versions only.
"""
import hashlib
import json
from pathlib import Path


def archived_binding(constraint_id, digest, *, root):
    archive = Path(root) / 'rf/constraints/history/pre-issue-307'
    if not archive.is_dir():
        return None  # No archival identity: caller must still validate current binding.
    metadata = json.loads((archive/'provenance.json').read_text())
    if metadata['resolved_effective_sha256'].get(constraint_id) != digest:
        return None
    # Verify the archive's original bytes before trusting its identity table.
    for relative, expected in metadata['snapshot_file_sha256'].items():
        path = (archive/relative).resolve()
        if not path.is_relative_to(archive.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Historical constraint archive byte mismatch')
    registry = json.loads((archive/'registry.json').read_text())
    for kind in ('formal', 'trial'):
        if constraint_id in registry[kind]:
            entry = registry[kind][constraint_id]
            return {'class': kind, 'base_constraint_id': entry.get('base_constraint_id')}
    raise ValueError('Historical digest lacks archive registration')


def archived_evidence_file(relative, digest, *, root):
    """Locate original RF snapshot bytes referenced by an old evidence record."""
    prefix = 'data/constraints/'
    if not relative.startswith(prefix):
        return None
    suffix = relative[len(prefix):]
    archive = Path(root)/'rf/constraints/history/pre-issue-307'
    metadata = json.loads((archive/'provenance.json').read_text())
    if metadata['snapshot_file_sha256'].get(suffix) != digest:
        raise ValueError('Unknown historical RF snapshot evidence SHA')
    path = (archive/suffix).resolve()
    if not path.is_relative_to(archive.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('Historical RF snapshot evidence byte mismatch')
    return path


def archived_formal_evidence(constraint_id, digest, *, root):
    if digest is None:
        metadata = json.loads((Path(root)/'rf/constraints/history/pre-issue-307/provenance.json').read_text())
        digest = metadata['resolved_effective_sha256'].get(constraint_id)
    binding = archived_binding(constraint_id, digest, root=root)
    if binding != {'class': 'formal', 'base_constraint_id': None}:
        raise ValueError('Unknown historical formal evidence binding')
    return json.loads((Path(root)/'rf/constraints/history/pre-issue-307/formal'/
                       f'{constraint_id}.json').read_text())
