#!/usr/bin/env python3
"""Unwired runner for explicit changed unittest files; fail on stale/unsafe inputs."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OID = re.compile(r'[0-9a-f]{40}\Z')
MODULE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')
RUN = '''\
import sys, unittest
suite = unittest.TestLoader().discover(start_dir=sys.argv[1], pattern=sys.argv[2])
if suite.countTestCases() == 0:
    raise SystemExit('changed test module contains no discoverable tests')
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
'''


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], stderr=subprocess.PIPE)


def validate(head, paths):
    if not OID.fullmatch(head or '') or head == '0'*40:
        raise ValueError('expected HEAD must be a full nonzero object ID')
    if git('rev-parse', 'HEAD').strip().decode('ascii') != head:
        raise ValueError('HEAD mismatch')
    if len(paths) != len(set(paths)):
        raise ValueError('duplicate changed test path')
    root = ROOT.resolve()
    for path in paths:
        parts = path.split('/')
        name = parts[-1]
        if (len(parts) < 2 or parts[0] != 'tests' or not name.endswith('.py')
                or not (name.startswith('test') or name.endswith('_test.py'))
                or not all(MODULE.fullmatch(x) for x in parts[1:-1] + [name[:-3]])):
            raise ValueError('unsupported changed test path: ' + path)
        file = root.joinpath(*parts)
        if file.resolve() != file or not file.is_file():
            raise ValueError('changed test missing or symlinked: ' + path)
        entry = git('ls-tree', '-z', head, '--', path).split(b'\0')
        if len(entry) != 2 or entry[1] or b'\t' not in entry[0]:
            raise ValueError('changed test not uniquely tracked: ' + path)
        metadata, name_bytes = entry[0].split(b'\t', 1)
        if metadata.split()[:2] != [b'100644', b'blob'] or name_bytes != path.encode('utf-8'):
            raise ValueError('changed test has unsafe Git mode: ' + path)
        if file.read_bytes() != git('show', f'{head}:{path}'):
            raise ValueError('changed test differs from HEAD: ' + path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--head', required=True)
    parser.add_argument('paths', nargs='*')
    args = parser.parse_args()
    validate(args.head, args.paths)
    env = dict(os.environ)
    env['PYTHONPATH'] = str(ROOT/'tests') + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    for path in args.paths:
        parent, name = path.rsplit('/', 1)
        print('Running changed test:', path, flush=True)
        subprocess.run([sys.executable, '-c', RUN, parent, name], cwd=ROOT, env=env, check=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        raise SystemExit('FAIL changed tests: ' + str(exc))
