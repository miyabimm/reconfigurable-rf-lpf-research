#!/usr/bin/env python3
"""Read-only, bounded preflight for tracked rf/ YAML inputs; no EXP or solver."""
import argparse
import hashlib
import json
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
MAX_RF_FILES = 1000
MAX_RF_FILE_BYTES = 10_000_000
MAX_RF_TOTAL_BYTES = 50_000_000
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


def rf_head_files(root, head):
    """Bind the entire tracked RF input tree, not just YAML, to HEAD."""
    entries = git(root, 'ls-tree', '-r', '-l', '-z', '--full-tree', head, '--', 'rf/').split(b'\0')
    files, total = {}, 0
    for entry in entries:
        if not entry:
            continue
        meta, name = entry.split(b'\t', 1)
        fields = meta.split()
        path = name.decode('utf-8')
        if len(fields) != 4 or fields[:2] != [b'100644', b'blob']:
            raise ValueError('unsafe RF input mode: ' + path)
        size = int(fields[3])
        total += size
        if size > MAX_RF_FILE_BYTES or total > MAX_RF_TOTAL_BYTES or len(files) >= MAX_RF_FILES:
            raise ValueError('RF input tree exceeds CI preflight size limit')
        file = root/path
        if file.resolve() != file or not file.is_file():
            raise ValueError('missing or symlinked RF input: ' + path)
        if file.stat().st_size != size:
            raise ValueError('RF input differs from HEAD: ' + path)
        raw = file.read_bytes()
        if raw != git(root, 'show', f'{head}:{path}'):
            raise ValueError('RF input differs from HEAD: ' + path)
        files[path] = raw
    return files


def rf_path(logical):
    if not isinstance(logical, str):
        raise ValueError('invalid RF input reference')
    path = ('rf/' + logical[5:]) if logical.startswith('data/') else logical
    if (not path.startswith('rf/') or not re.fullmatch(r'[A-Za-z0-9_./-]+', path) or
            any(part in ('', '.', '..') for part in path.split('/'))):
        raise ValueError('unsafe RF input reference: ' + logical)
    return path


def definition_source(root, head, ref):
    name = ref.get('path')
    if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_./-]+', name) or
            any(part in ('', '.', '..') for part in name.split('/'))):
        raise ValueError('unsafe definition source path')
    entries = [x for x in git(root, 'ls-tree', '-l', '-z', '--full-tree', head, '--', name).split(b'\0') if x]
    if len(entries) != 1 or b'\t' not in entries[0]:
        raise ValueError('definition source missing from HEAD: ' + name)
    meta, listed = entries[0].split(b'\t', 1)
    fields = meta.split()
    if listed.decode('utf-8') != name or len(fields) != 4 or fields[:2] != [b'100644', b'blob']:
        raise ValueError('unsafe definition source at HEAD: ' + name)
    size = int(fields[3])
    if size > MAX_RF_FILE_BYTES:
        raise ValueError('definition source exceeds CI preflight size limit')
    file = root/name
    if file.resolve() != file or not file.is_file() or file.stat().st_size != size:
        raise ValueError('definition source differs from HEAD: ' + name)
    raw = file.read_bytes()
    if raw != git(root, 'show', f'{head}:{name}') or hashlib.sha256(raw).hexdigest() != ref['source_sha256']:
        raise ValueError('definition source differs from HEAD: ' + name)
    return name, raw


def check(root, head):
    root = Path(root).resolve()
    if not isinstance(head, str) or not OID.fullmatch(head) or head == '0'*40:
        raise ValueError('HEAD mismatch or invalid expected object ID')
    if git(root, 'rev-parse', 'HEAD').strip().decode('ascii') != head:
        raise ValueError('HEAD mismatch')
    files = rf_head_files(root, head)
    registry = files.get('rf/constraints/registry.json')
    if registry is None:
        raise ValueError('RF registry missing from HEAD')
    try:
        registered = json.loads(registry)
        for kind in ('formal', 'trial'):
            for entry in registered[kind].values():
                path = rf_path(entry['file'])
                if path not in files:
                    raise ValueError('registered RF input absent from HEAD: ' + path)
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise ValueError('invalid RF registry references: ' + str(exc)) from exc
    results, sources = [], {}
    for path, raw in files.items():
        if not path.lower().endswith(('.yaml', '.yml')):
            continue
        file = root/path
        config = bounded_config(raw)
        try:
            plan = load_preflight(file, root=root)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            raise ValueError('RF schema2 preflight failed for ' + path + ': ' + str(exc)) from exc
        data = plan.data
        if file.read_bytes() != raw or data['config'] != config:
            raise ValueError('RF YAML changed during preflight: ' + path)
        ref = config['definition']
        if isinstance(ref, dict) and 'inductor_tree' not in ref:
            name, source_raw = definition_source(root, head, ref)
            sources[name] = source_raw
        inputs = data.get('rf_inputs')
        if not isinstance(inputs, dict) or set(inputs) != {'bands', 'input_parasitic', 'output_parasitic'}:
            raise ValueError('incomplete frozen RF input references: ' + path)
        for value in inputs.values():
            name = rf_path(value['path'])
            if name not in files or hashlib.sha256(files[name]).hexdigest() != value['sha256']:
                raise ValueError('frozen RF input absent or mismatched at HEAD: ' + name)
        results.append({'path': path, 'plan_sha256': plan.sha256})
    for name, raw in files.items():
        file = root/name
        if file.resolve() != file or not file.is_file() or file.read_bytes() != raw:
            raise ValueError('RF input changed during preflight: ' + name)
    for name, raw in sources.items():
        file = root/name
        if file.resolve() != file or not file.is_file() or file.read_bytes() != raw:
            raise ValueError('definition source changed during preflight: ' + name)
    if git(root, 'rev-parse', 'HEAD').strip().decode('ascii') != head:
        raise ValueError('HEAD changed during RF preflight')
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--head', required=True)
    args = parser.parse_args()
    print(json.dumps({'schema2_preflights': check(ROOT, args.head),
                      'limitations': 'schema preflight is YAML only; RF tree checked for HEAD byte identity; '
                                     'no EXP, solver, G0/G1 or physical approval'}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        raise SystemExit('FAIL RF schema2 checks: ' + str(exc))
