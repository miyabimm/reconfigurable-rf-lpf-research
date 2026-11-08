#!/usr/bin/env python3
"""Read-only targeted ledger consistency check; this does not authorize an EXP."""
import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ci.classify_storage_ci import INDEX_HEADER, index_rows
from lpf.experiment_id_registry import RESERVED, read_ledger
from lpf.experiment_manifest import experiment_index

ID = re.compile(r'EXP-\d{3,}\Z')
MANIFEST = re.compile(r'experiments/(?:chatgpt_topology_search|matching_limit)/runs/(EXP-\d{3,})/manifest\.json\Z')


def committed_bytes(root, name):
    root = Path(root).resolve()
    path = root/name
    if path.resolve() != path or not path.is_file():
        raise ValueError('target missing or symlinked: ' + name)
    try:
        committed = subprocess.check_output(['git', '-C', str(root), 'show', 'HEAD:' + name],
                                            stderr=subprocess.PIPE, timeout=30)
    except subprocess.SubprocessError as exc:
        raise ValueError('target not committed at HEAD: ' + name) from exc
    raw = path.read_bytes()
    if raw != committed:
        raise ValueError('target differs from HEAD: ' + name)
    return raw


def check(root, ids, *, require_committed=False):
    if (not ids or not all(isinstance(x, str) and ID.fullmatch(x) for x in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError('target IDs must be nonempty, valid and unique')
    root = Path(root)
    def read(name):
        return committed_bytes(root, name) if require_committed else (root/name).read_bytes()
    entries = index_rows(read('data/experiment_index.csv'))
    index = {values[0]: dict(zip(INDEX_HEADER, values)) for values, _ in entries[1:]}
    ledger = {row['experiment_id']: row for row in
              read_ledger(read('data/experiment_number_registry.csv').decode('utf-8'))}
    result = []
    for ident in sorted(ids):
        row = ledger.get(ident)
        indexed = index.get(ident)
        if row is None:
            raise ValueError('target missing from reservation ledger: ' + ident)
        if int(ident[4:]) >= 42 and row['state'] not in RESERVED:
            raise ValueError('invalid reservation state for target: ' + ident)
        if indexed and int(ident[4:]) >= 42:
            if indexed['constraint_id'] != row['constraint_id']:
                raise ValueError('index/registry constraint mismatch: ' + ident)
            m = MANIFEST.fullmatch(indexed['manifest'])
            if not m or m.group(1) != ident:
                raise ValueError('index manifest identity mismatch: ' + ident)
        result.append(dict(experiment_id=ident, registry_state=row['state'],
                           index_present=indexed is not None))
    return result


def check_index_manifests(root, ids):
    """Compare only indexed target rows with their committed manifest projections."""
    root = Path(root).resolve()
    entries = index_rows(committed_bytes(root, 'data/experiment_index.csv'))
    index = {values[0]: values for values, _ in entries[1:]}
    for ident in ids:
        if ident not in index:
            raise ValueError('target missing from index: ' + ident)
        path = index[ident][INDEX_HEADER.index('manifest')]
        match = MANIFEST.fullmatch(path)
        if not match or match.group(1) != ident:
            raise ValueError('index manifest identity mismatch: ' + ident)
        try:
            manifest = json.loads(committed_bytes(root, path), parse_constant=lambda v: (_ for _ in ()).throw(
                ValueError('non-finite JSON value: ' + v)))
            expected = index_rows(experiment_index([(path, manifest)]).encode('utf-8'))[1][0]
        except (KeyError, TypeError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError('invalid target manifest: ' + ident) from exc
        if index[ident] != expected:
            raise ValueError('target index differs from manifest: ' + ident)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('experiment_id', nargs='+')
    args = parser.parse_args()
    print(json.dumps({'targets': check(ROOT, args.experiment_id),
                      'g0_g5': 'not_certified'}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, csv.Error, OSError) as exc:
        raise SystemExit('FAIL changed ledger: ' + str(exc))
