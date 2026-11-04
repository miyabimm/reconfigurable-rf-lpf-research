"""Read-only partial input check for the proposed four-arm comparison.

This does not freeze G1, inspect remote evidence, or authorize an experiment.
"""
import csv
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import sys

from lpf.checkpoint_io import canonical_config_hash
from lpf.constraint_versions import constraint_fingerprint, load_constraint, rf_input_file
from ._grid import validated_band_segments

_RF_SHA = '7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4'
_BANDS_SHA = '1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe'
_DEFINITION_SHA = 'bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068'
_DEFINITION_FILE_SHA = '07e64095710452a12c1f71f84feaabad35ad4613e6f68646e4a27ce5cb3ccff0'
_CHECKPOINT_SHA = '4fbd86e8b46ad7bcb550ba327672b0983e8b58e9ce4b2a9364f8c6557a812b4b'


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _required(path, expected):
    actual = _hash(path)
    if actual != expected:
        raise ValueError(f'Input SHA mismatch: {path}')
    return actual


def comparison_readiness(root, *, allow_trial):
    """Validate available immutable bytes; always report production not ready."""
    if allow_trial is not True:
        raise ValueError('Explicit RF-T008 trial opt-in required')
    root = Path(root).resolve()
    policy = load_constraint('RF-T008', root=root, allow_trial=True)
    if constraint_fingerprint(policy) != _RF_SHA:
        raise ValueError('RF-T008 effective SHA mismatch')
    bands = rf_input_file(root, policy['bands_file'])
    _required(bands, _BANDS_SHA)
    with bands.open(newline='', encoding='utf-8') as stream:
        segments = validated_band_segments(list(csv.DictReader(stream)))
    parasitics = {}
    for key in ('input_parasitic', 'output_parasitic'):
        entry = policy['external_port_parasitics'][key]
        parasitics[key] = _required(rf_input_file(root, entry['path']), entry['sha256'])
    definition = root / 'project/experiments/issue270-definition.json'
    _required(definition, _DEFINITION_FILE_SHA)
    if canonical_config_hash(json.loads(definition.read_text(encoding='utf-8'))) != _DEFINITION_SHA:
        raise ValueError('Definition SHA mismatch')
    checkpoint = root / 'experiments/chatgpt_topology_search/runs/EXP-062/checkpoints/a6_best.json'
    checkpoint_status = 'not_checked'
    if checkpoint.is_file():
        _required(checkpoint, _CHECKPOINT_SHA)
        checkpoint_status = 'local_file_sha_matches_only'
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=root, text=True).strip()
    return {
        'production_readiness': 'not_ready', 'g0_g1_g2': 'not_run',
        'rf': {'id': 'RF-T008', 'effective_sha256': _RF_SHA, 'trial_opt_in': True,
               'objective': 'full_lpf', 'bands_sha256': _BANDS_SHA,
               'settings': len({s[0] for s in segments}), 'intervals': len(segments),
               's2p_sha256': parasitics},
        'definition_sha256': _DEFINITION_SHA,
        'checkpoint': checkpoint_status,
        'source_manifest_and_remote_readback': 'not_checked',
        'source': {'head': git('rev-parse', 'HEAD'),
                   'working_tree_dirty': bool(git('status', '--porcelain', '--untracked-files=normal')),
                   'uv_lock_sha256': _hash(root / 'uv.lock')},
        'environment': {'python': sys.version, 'platform': platform.platform()},
        'seed_vectors_grid_weights_budget_storage': 'not_frozen',
        'anytime_production_and_storage_integration': 'not_implemented',
    }
