#!/usr/bin/env python3
"""Read-only targeted ledger consistency check; this does not authorize an EXP."""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ci.classify_storage_ci import INDEX_HEADER, index_rows
from lpf.experiment_id_registry import RESERVED, read_ledger

ID = re.compile(r'EXP-\d{3,}\Z')
MANIFEST = re.compile(r'experiments/(?:chatgpt_topology_search|matching_limit)/runs/(EXP-\d{3,})/manifest\.json\Z')


def check(root, ids):
    if (not ids or not all(isinstance(x, str) and ID.fullmatch(x) for x in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError('target IDs must be nonempty, valid and unique')
    root = Path(root)
    entries = index_rows((root/'data/experiment_index.csv').read_bytes())
    index = {values[0]: dict(zip(INDEX_HEADER, values)) for values, _ in entries[1:]}
    ledger = {row['experiment_id']: row for row in
              read_ledger((root/'data/experiment_number_registry.csv').read_text(encoding='utf-8'))}
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
