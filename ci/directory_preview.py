#!/usr/bin/env python3
"""Unwired directory-CI preview; mixed project/data paths fail closed.

This does not run checks and is not a replacement for the current workflow.
"""
import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ci.classify_storage_ci import index_rows
from lpf.experiment_id_registry import read_ledger

OID = re.compile(r'[0-9a-f]{40}\Z')
TEST = re.compile(r'tests/test_[A-Za-z0-9_]+\.py\Z')
EXPERIMENT = re.compile(r'experiments/(?:chatgpt_topology_search|matching_limit)/runs/(EXP-\d{3,})/.+\Z')
ROOT_NONE = {'README.md', 'AGENTS.md', 'LICENSE-STATUS.md', '.gitignore'}
MAX_BYTES = 256_000
MAX_PATHS = 1000
MAX_LEDGER_BYTES = 10_000_000
INDEX = 'data/experiment_index.csv'
REGISTRY = 'data/experiment_number_registry.csv'


def git(*args):
    return subprocess.check_output(['git', *args], stderr=subprocess.PIPE, timeout=30)


def classify(path):
    if '/' not in path:
        return 'NONE' if path in ROOT_NONE else 'FULL'
    directory = path.split('/', 1)[0]
    # Mixed historical inputs/evidence preclude unconditional DOC/EXP.
    return {'rf': 'INPUT', 'src': 'CODE', 'tests': 'CODE',
            'experiments': 'EXP', 'project': 'FULL', 'data': 'FULL',
            'ci': 'FULL', '.github': 'FULL'}.get(directory, 'FULL')


def ledger_delta(path, base, head):
    """Identify changed rows, not G0/G4 approval; malformed data fails closed."""
    old_raw, new_raw = (git('show', f'{rev}:{path}') for rev in (base, head))
    if max(len(old_raw), len(new_raw)) > MAX_LEDGER_BYTES:
        raise ValueError('ledger exceeds inspection limit')
    if path == INDEX:
        old_rows, new_rows = index_rows(old_raw), index_rows(new_raw)
        if old_rows[0][1] != new_rows[0][1]:
            raise ValueError('index header changed')
        before = [(values[0], record) for values, record in old_rows[1:]]
        after = [(values[0], record) for values, record in new_rows[1:]]
    elif path == REGISTRY:
        before = [(row['experiment_id'], row) for row in read_ledger(old_raw.decode('utf-8'))]
        after = [(row['experiment_id'], row) for row in read_ledger(new_raw.decode('utf-8'))]
    else:
        raise ValueError('unknown ledger')
    old, new = dict(before), dict(after)
    common = set(old) & set(new)
    if ([ident for ident, _ in before if ident in common] !=
            [ident for ident, _ in after if ident in common]):
        raise ValueError('ledger rows reordered')
    changed = {ident for ident in set(old) | set(new) if old.get(ident) != new.get(ident)}
    if not changed and old_raw != new_raw:
        raise ValueError('unattributed ledger byte change')
    return changed, set(old) - set(new)


def preview(event, base, head, ref, *, force=False):
    result = dict(classes=[], full=False, reasons=[], changed_tests=[],
                  changed_tests_complete=False, changed_experiments=[],
                  removed_ledger_experiments=[], experiment_scope_complete=False, changes=[])
    if force or event == 'workflow_dispatch':
        result.update(full=True, reasons=['manual FULL'])
        return result
    try:
        if event not in {'pull_request', 'push'} or ref != 'main' or any(
                not OID.fullmatch(x or '') or x == '0'*40 for x in (base, head)):
            raise ValueError('invalid event, branch or object ID')
        if git('rev-parse', 'HEAD').strip().decode('ascii') != head:
            raise ValueError('HEAD mismatch')
        if event == 'pull_request':
            base = git('merge-base', base, head).strip().decode('ascii')
        elif subprocess.run(['git', 'merge-base', '--is-ancestor', base, head],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            timeout=30).returncode:
            raise ValueError('push is not fast-forward')
        raw = git('-c', 'diff.renames=copies', 'diff', '--raw', '-z', '--no-ext-diff',
                  '--no-textconv', '--find-renames', '--find-copies', '--find-copies-harder',
                  '-l0', base, head, '--')
        if not raw or len(raw) > MAX_BYTES or not raw.endswith(b'\0'):
            raise ValueError('empty, oversized or malformed diff')
        fields = raw[:-1].split(b'\0')
        records = []
        i = 0
        while i < len(fields):
            header = fields[i].decode('ascii').split()
            i += 1
            if len(header) != 5 or not header[0].startswith(':'):
                raise ValueError('malformed raw diff header')
            old_mode, new_mode, _, _, status = header
            old_mode = old_mode[1:]
            kind = status[:1]
            if kind not in {'A', 'M', 'D', 'R', 'C', 'T'} or (kind in {'R', 'C'} and
                    not re.fullmatch(r'[RC]\d{1,3}', status)) or (kind not in {'R', 'C'} and len(status) != 1):
                raise ValueError('unsupported diff status')
            count = 2 if kind in {'R', 'C'} else 1
            if i + count > len(fields):
                raise ValueError('truncated raw diff')
            paths = [v.decode('utf-8') for v in fields[i:i+count]]
            i += count
            if any(not p or p.startswith('/') or '..' in p.split('/') for p in paths):
                raise ValueError('unsafe diff path')
            records.append(dict(status=status, old_mode=old_mode, new_mode=new_mode, paths=paths))
            if len(records) > MAX_PATHS:
                raise ValueError('too many changed paths')
        groups, experiment_ids, removed_ids = set(), set(), set()
        experiment_scope_complete = True
        for change in records:
            kind = change['status'][0]
            old_mode, new_mode = change['old_mode'], change['new_mode']
            if ((kind != 'A' and old_mode != '100644') or
                    (kind != 'D' and new_mode != '100644') or kind in {'C', 'T'}):
                result['full'] = True
                result['reasons'].append('unsafe mode or copy: ' + ', '.join(change['paths']))
            for path in change['paths']:
                if path.startswith('experiments/'):
                    match = EXPERIMENT.fullmatch(path)
                    if match:
                        experiment_ids.add(match.group(1))
                    else:
                        experiment_scope_complete = False
                elif path.startswith('data/'):
                    if path in {INDEX, REGISTRY} and kind == 'M':
                        try:
                            changed, removed = ledger_delta(path, base, head)
                            experiment_ids.update(changed)
                            removed_ids.update(removed)
                        except (ValueError, UnicodeError, csv.Error, OSError, subprocess.SubprocessError) as exc:
                            experiment_scope_complete = False
                            result['reasons'].append('ledger comparison unavailable: ' + str(exc))
                    else:
                        experiment_scope_complete = False
                group = classify(path)
                if group == 'FULL':
                    result['full'] = True
                    result['reasons'].append('mixed or unrecognized path: ' + path)
                elif group != 'NONE':
                    groups.add(group)
            if kind != 'D':
                destination = change['paths'][-1]
                if TEST.fullmatch(destination):
                    result['changed_tests'].append(destination)
        if not experiment_scope_complete:
            result['full'] = True
            result['reasons'].append('experiment or ledger scope requires additional inspection')
        result['classes'] = [x for x in ('DOC', 'INPUT', 'EXP', 'CODE') if x in groups]
        result['changed_tests'] = sorted(set(result['changed_tests']))
        result['changed_tests_complete'] = True
        result['changed_experiments'] = sorted(experiment_ids)
        result['removed_ledger_experiments'] = sorted(removed_ids)
        result['experiment_scope_complete'] = experiment_scope_complete
        result['changes'] = records
    except (ValueError, UnicodeError, OSError, subprocess.SubprocessError) as exc:
        result.update(full=True, reasons=['comparison unavailable: ' + str(exc)])
    return result


def main():
    event = os.getenv('CI_EVENT')
    print(json.dumps(preview(event, os.getenv('CI_BASE'), os.getenv('CI_HEAD'),
                             os.getenv('CI_BASE_REF'), force=os.getenv('CI_FULL') == 'true'),
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
