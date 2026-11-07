#!/usr/bin/env python3
"""Conservative CI optimization only; never substitutes for the storage audit."""
import json
import os
import re
import subprocess
import sys
from pathlib import PurePosixPath

from experiment_id_registry import PATH, read_ledger

RUN = re.compile(r"experiments/(?:chatgpt_topology_search|matching_limit)/runs/(EXP-\d{3,})/(.+)\Z")
MAX_DIFF_BYTES = 256_000
MAX_PATHS = 1000
MAX_TOTAL_BYTES = 10_000_000


def git(*args):
    return subprocess.check_output(['git', *args], stderr=subprocess.PIPE, timeout=30)


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
    total_bytes = 0
    for status, raw in zip(fields[::2], fields[1::2]):
        if status not in (b'A', b'M'):
            return False
        name = raw.decode('utf-8')
        match = RUN.fullmatch(name)
        if not match or int(match[1][4:]) < 50:
            return False
        # JSON A/B evidence only. Other formats, index edits and unusual names
        # conservatively use the full suite, even if the audit would accept them.
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
        paths.append((match[1], name))
    ids = {item[0] for item in paths}
    roots = {name.split('/runs/')[0] for _, name in paths}
    if len(ids) != 1 or len(roots) != 1:
        return False
    exp = next(iter(ids))
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
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError, TypeError, AttributeError):
        result = False
    print('storage_only=' + str(result).lower())
    return 0


if __name__ == '__main__':
    sys.exit(main())
