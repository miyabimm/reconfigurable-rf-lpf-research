#!/usr/bin/env python3
"""Unwired directory-CI preview; mixed project/data paths fail closed.

This does not run checks and is not a replacement for the current workflow.
"""
import json
import os
import re
import subprocess

OID = re.compile(r'[0-9a-f]{40}\Z')
TEST = re.compile(r'tests/test_[A-Za-z0-9_]+\.py\Z')
EXPERIMENT = re.compile(r'experiments/(?:chatgpt_topology_search|matching_limit)/runs/(EXP-\d{3,})/.+\Z')
ROOT_NONE = {'README.md', 'AGENTS.md', 'LICENSE-STATUS.md', '.gitignore'}
MAX_BYTES = 256_000
MAX_PATHS = 1000


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


def preview(event, base, head, ref, *, force=False):
    result = dict(classes=[], full=False, reasons=[], changed_tests=[],
                  changed_tests_complete=False, changed_experiments=[],
                  experiment_scope_complete=False, changes=[])
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
        groups, experiment_ids = set(), set()
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
                    # Ledger-only changes require a separate row-level diff.
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
