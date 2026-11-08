#!/usr/bin/env python3
"""Conservative CI optimization only; never substitutes for the storage audit."""
import csv
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.experiment_id_registry import PATH, read_ledger

RUN = re.compile(r"experiments/(?:chatgpt_topology_search|matching_limit)/runs/(EXP-\d{3,})/(.+)\Z")
MAX_DIFF_BYTES = 256_000
MAX_PATHS = 1000
MAX_TOTAL_BYTES = 10_000_000
INDEX = 'data/experiment_index.csv'
INDEX_HEADER = ('experiment_id', 'constraint_class', 'constraint_id',
                'effective_constraint_sha256', 'objective', 'execution_status',
                'numerical_validation', 'independent_validation', 'manifest', 'purpose')


def git(*args):
    return subprocess.check_output(['git', *args], stderr=subprocess.PIPE, timeout=30)


def index_rows(raw):
    """Parse logical CSV records while retaining their exact original bytes."""
    text = raw.decode('utf-8')
    lines = list(io.StringIO(text, newline=''))
    if not lines or not text.endswith('\n'):
        raise ValueError('incomplete index')
    reader = csv.reader(io.StringIO(text, newline=''), strict=True)
    entries = []
    start = 0
    for values in reader:
        end = reader.line_num
        record = ''.join(lines[start:end])
        start = end
        if len(values) != len(INDEX_HEADER):
            raise ValueError('invalid index record')
        entries.append((values, record))
    if start != len(lines) or not entries or tuple(entries[0][0]) != INDEX_HEADER:
        raise ValueError('invalid index header')
    ids = [values[0] for values, _ in entries[1:]]
    if (any(not re.fullmatch(r'EXP-\d{3,}', ident) for ident in ids)
            or len(ids) != len(set(ids))):
        raise ValueError('invalid index identities')
    return entries


def index_change_is_target_only(before, after, exp):
    old, new = index_rows(before), index_rows(after)
    if old[0][1] != new[0][1]:
        return False
    old_ids = [row[0][0] for row in old[1:]]
    new_ids = [row[0][0] for row in new[1:]]
    if new_ids.count(exp) != 1 or old_ids.count(exp) > 1:
        return False
    if exp in old_ids:
        if new_ids != old_ids:
            return False
    else:
        # New entries must preserve all others and be in numerical EXP order.
        if new_ids != sorted(new_ids, key=lambda ident: int(ident[4:])):
            return False
    return ([record for values, record in old[1:] if values[0] != exp]
            == [record for values, record in new[1:] if values[0] != exp])


def classify(event, base, head, base_ref):
    # Only immutable full object IDs supplied by the event are accepted.
    if event not in {'pull_request', 'push'} or base_ref != 'main' or any(
        not re.fullmatch(r'[0-9a-f]{40}', x or '') or x == '0' * 40 for x in (base, head)
    ):
        return False
    if git('rev-parse', 'HEAD').strip().decode() != head:
        return False
    if event == 'pull_request':
        base = git('merge-base', base, head).strip().decode()
    elif subprocess.run(['git', 'merge-base', '--is-ancestor', base, head],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30).returncode:
        return False
    # Disable external diff/textconv; copy/rename detection must not disguise a deletion.
    diff = git('-c', 'diff.renames=copies', 'diff', '--no-ext-diff', '--no-textconv',
               '--find-renames', '--find-copies', '--find-copies-harder', '-l0',
               '--name-status', '-z', base, head, '--')
    if not diff or len(diff) > MAX_DIFF_BYTES:
        return False
    fields = diff.split(b'\0')
    if fields.pop() != b'' or len(fields) % 2 or len(fields) // 2 > MAX_PATHS:
        return False
    paths = []
    index_changed = False
    total_bytes = 0
    for status, raw in zip(fields[::2], fields[1::2]):
        if status not in (b'A', b'M'):
            return False
        name = raw.decode('utf-8')
        match = RUN.fullmatch(name)
        if name == INDEX:
            if status != b'M' or index_changed:
                return False
            index_changed = True
        else:
            if not match or int(match[1][4:]) < 50:
                return False
            # JSON A/B evidence only; other formats use the full suite.
            parts = PurePosixPath(match[2]).parts
            if (not parts or any(not re.fullmatch(r'[A-Za-z0-9_.-]+', p)
                                 or p in {'.', '..'} or p.startswith('.') for p in parts)
                    or not name.endswith('.json')):
                return False
            if status == b'M' and match[2] not in {'manifest.json', 'storage_record.json'}:
                return False
        # Reject symlinks, executable files and huge diffs without reading blobs.
        for revision in ((head, base) if status == b'M' else (head,)):
            tree = git('ls-tree', '-l', '-z', revision, '--', name)
            entry = tree.rstrip(b'\0').split(b'\t', 1)
            if len(entry) != 2 or entry[1] != raw:
                return False
            metadata = entry[0].split()
            if len(metadata) != 4 or metadata[0:2] != [b'100644', b'blob']:
                return False
            total_bytes += int(metadata[3])
            if total_bytes > MAX_TOTAL_BYTES:
                return False
        if match:
            paths.append((match[1], name))
    ids = {item[0] for item in paths}
    roots = {name.split('/runs/')[0] for _, name in paths}
    if len(ids) != 1 or len(roots) != 1:
        return False
    exp = next(iter(ids))
    if index_changed and not index_change_is_target_only(
            git('show', f'{base}:{INDEX}'), git('show', f'{head}:{INDEX}'), exp):
        return False
    ledger = read_ledger(git('show', f'{base}:{PATH}').decode('utf-8'))
    if not any(row['experiment_id'] == exp and row['state'] in {'reserved', 'active'}
               for row in ledger):
        return False
    run = f'{next(iter(roots))}/runs/{exp}'
    # Require a pre-existing G1 record on the baseline, not a historical or
    # already finalized EXP. Audit remains responsible for all A/B validation.
    record = json.loads(git('show', f'{base}:{run}/storage_record.json'))
    return (record.get('experiment_id') == exp and record.get('policy') == 'phase2-git-only-v1'
            and record.get('stage') in {'planned', 'running'})


def main():
    try:
        result = classify(os.getenv('CI_EVENT'), os.getenv('CI_BASE'), os.getenv('CI_HEAD'),
                          os.getenv('CI_BASE_REF'))
    except (OSError, ValueError, UnicodeError, csv.Error, subprocess.SubprocessError, TypeError, AttributeError):
        result = False
    print('storage_only=' + str(result).lower())
    return 0


if __name__ == '__main__':
    sys.exit(main())
