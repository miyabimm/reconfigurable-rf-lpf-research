#!/usr/bin/env python3
"""Read-only, bounded preflight for tracked rf/ YAML inputs; no EXP or solver."""
import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from lpf.search.plan import Loader, load_preflight

MAX_BYTES = 256_000
MAX_TOKENS = 50_000
MAX_GRIDS = 16
MAX_POINTS = 1001
MAX_SEEDS = 32
OID = re.compile(r'[0-9a-f]{40}\Z')


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE, timeout=30)


def bounded_config(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError('RF YAML exceeds CI preflight byte limit')
    try:
        for count, token in enumerate(yaml.scan(raw), 1):
            if count > MAX_TOKENS or isinstance(token, (yaml.tokens.AnchorToken, yaml.tokens.AliasToken)):
                raise ValueError('RF YAML aliases or excessive tokens require review')
        config = yaml.load(raw, Loader=Loader)
        if not isinstance(config, dict) or type(config.get('schema_version')) is not int or config['schema_version'] != 2:
            raise ValueError('RF YAML must be schema2 or receive separate review')
        seeds, arms = config['seeds'], config['arms']
        if (not isinstance(seeds, list) or len(seeds) > MAX_SEEDS or
                not isinstance(arms, list) or len(arms) > MAX_GRIDS):
            raise ValueError('RF YAML exceeds CI preflight seed/arm limit')
        points = [config['selection']['points_per_interval'], config['validation']['terminal_points'],
                  config['validation']['dense_points'], config['anytime_points_per_interval']]
        for arm in arms:
            if not isinstance(arm['steps'], list) or len(arm['steps']) > MAX_GRIDS:
                raise ValueError('RF YAML exceeds CI preflight stage limit')
            for step in arm['steps']:
                points.append(step['points_per_interval'])
                if 'stop_points_per_interval' in step:
                    points.append(step['stop_points_per_interval'])
        if len(points) > MAX_GRIDS or any(type(n) is not int or not 2 <= n <= MAX_POINTS for n in points):
            raise ValueError('RF YAML exceeds CI preflight grid limit')
        return config
    except (yaml.YAMLError, KeyError, TypeError) as exc:
        raise ValueError('invalid or unsupported RF YAML: ' + str(exc)) from exc


def check(root, head):
    root = Path(root).resolve()
    if not isinstance(head, str) or not OID.fullmatch(head) or head == '0'*40:
        raise ValueError('HEAD mismatch or invalid expected object ID')
    if git(root, 'rev-parse', 'HEAD').strip().decode('ascii') != head:
        raise ValueError('HEAD mismatch')
    entries = git(root, 'ls-tree', '-r', '-z', '--full-tree', head, '--', 'rf/').split(b'\0')
    results = []
    for entry in entries:
        if not entry:
            continue
        meta, name = entry.split(b'\t', 1)
        path = name.decode('utf-8')
        if not path.lower().endswith(('.yaml', '.yml')):
            continue
        if meta.split()[:2] != [b'100644', b'blob']:
            raise ValueError('unsafe RF YAML mode: ' + path)
        file = root/path
        if file.resolve() != file or not file.is_file():
            raise ValueError('missing or symlinked RF YAML: ' + path)
        raw = file.read_bytes()
        if raw != git(root, 'show', f'{head}:{path}'):
            raise ValueError('RF YAML differs from HEAD: ' + path)
        config = bounded_config(raw)
        try:
            plan = load_preflight(file, root=root)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            raise ValueError('RF schema2 preflight failed for ' + path + ': ' + str(exc)) from exc
        if file.read_bytes() != raw or plan.data['config'] != config:
            raise ValueError('RF YAML changed during preflight: ' + path)
        results.append({'path': path, 'plan_sha256': plan.sha256})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--head', required=True)
    args = parser.parse_args()
    import json
    print(json.dumps({'schema2_preflights': check(ROOT, args.head),
                      'limitations': 'YAML only; no EXP, solver, G0/G1 or physical approval'}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        raise SystemExit('FAIL RF schema2 checks: ' + str(exc))
