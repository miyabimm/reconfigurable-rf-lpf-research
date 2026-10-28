"""Stage 5A synthetic plan preflight; not a scientific experiment runner.

Plans are bound to current code, RF inputs, environment and complete vectors.
This module does not start an optimizer or write experiment evidence.
"""
from dataclasses import asdict
import base64
import hashlib
import json
import re
import subprocess

from lpf.checkpoint_io import canonical_config_hash
from lpf.slsqp_budget import STANDARD_SLSQP_BUDGET, TERMINATION_AWARE_POLICY_ID
from ._grid import ROOT
from .limited_candidate_evidence import _identity
from .problem_seed import definition_fingerprint, vector_fingerprint
from .sampled_epigraph import SampledEpigraph
from .staged_optimization import _grid


def _copy(value):
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def _source():
    # Include tracked staged and unstaged changes and untracked file content.
    # Identity additionally fingerprints all src/lpf Python files and RF inputs.
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    tracked = subprocess.check_output(['git', 'diff', '--binary', 'HEAD', '--'], cwd=ROOT)
    names = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=ROOT)
    digest = hashlib.sha256(tracked)
    untracked = []
    for raw in sorted(filter(None, names.split(b'\0'))):
        path = ROOT / raw.decode('utf-8')
        digest.update(len(raw).to_bytes(8, 'big'))
        digest.update(raw)
        content = path.read_bytes()
        digest.update(hashlib.sha256(content).digest())
        untracked.append({'path': raw.decode('utf-8'), 'content_base64': base64.b64encode(content).decode('ascii')})
    return {'git_head': head, 'dirty_patch_sha256': digest.hexdigest(),
            'tracked_diff_base64': base64.b64encode(tracked).decode('ascii'),
            'untracked': untracked, 'dirty': bool(tracked or names)}


def make_synthetic_plan(circuit, starts, *, run_id, coarse_points, fine_points,
                        input_source):
    """Build a preflighted JSON plan, with explicit content-bound input origin.

    Each start supplies id, vector, vector_sha256, seed and jitter_fraction.
    Only tiny diagnostic grids are accepted; v2 budget is imported unchanged.
    Input source is a synthetic fixture containing policy and per-start vectors;
    its content is retained and hashed, not asserted to originate from an EXP.
    """
    if not isinstance(run_id, str) or not re.fullmatch(r'synthetic-[A-Za-z0-9_-]+', run_id):
        raise ValueError('A synthetic-prefixed run ID is required')
    if (not isinstance(input_source, dict) or set(input_source) != {'kind', 'policy_id', 'vectors'} or
            input_source['kind'] != 'synthetic' or input_source['policy_id'] != circuit.policy_id or
            not isinstance(input_source['vectors'], dict)):
        raise ValueError('Explicit matching synthetic input source is required')
    input_source = _copy(input_source)
    input_source_sha256 = canonical_config_hash(input_source)
    if (type(coarse_points) is not int or type(fine_points) is not int or
            coarse_points not in (1, 2, 3) or fine_points not in (1, 2, 3) or
            fine_points < coarse_points):
        raise ValueError('Expected ordered diagnostic grids of 1/2/3 points')
    if not isinstance(starts, (tuple, list)) or not 1 <= len(starts) <= 8:
        raise ValueError('Synthetic diagnostics require 1..8 explicit starts')
    coarse = SampledEpigraph(circuit, coarse_points)
    fine = SampledEpigraph(circuit, fine_points)
    source_before = _source()
    prepared, ids = [], set()
    for start in starts:
        if not isinstance(start, dict) or set(start) != {'id', 'vector', 'vector_sha256', 'seed', 'jitter_fraction'}:
            raise ValueError('Incomplete start')
        sid = start['id']
        if not isinstance(sid, str) or not sid or sid in ids:
            raise ValueError('Start IDs must be nonempty and unique')
        ids.add(sid)
        if sid not in input_source['vectors'] or _copy(start['vector']) != input_source['vectors'][sid]:
            raise ValueError('Start vector differs from input source')
        seed = coarse.seed(start['vector'], policy_id=circuit.policy_id,
                           policy_fingerprint=circuit.policy_fingerprint,
                           definition_sha256=definition_fingerprint(circuit.definition),
                           input_sha256=start['vector_sha256'], seed=start['seed'],
                           jitter_fraction=start['jitter_fraction'])
        prepared.append({'id': sid, 'seed_record': seed})
    if set(input_source['vectors']) != ids:
        raise ValueError('Input source start IDs do not match plan')
    identity = _identity(circuit, starts[0]['vector'])
    # _identity validates approved policy, reconstruction, actual S2P SHA, HEAD,
    # source files and environment. Vector binding is per start above.
    if _source() != source_before:
        raise ValueError('Source changed during preflight')
    plan = _copy({'schema': 'synthetic-run-plan-v1', 'kind': 'synthetic',
                  'run_id': run_id, 'policy_id': circuit.policy_id,
                  'policy_sha256': circuit.policy_fingerprint,
                  'definition': asdict(circuit.definition),
                  'definition_sha256': definition_fingerprint(circuit.definition),
                  'starts': prepared, 'grids': {'coarse': _grid(coarse), 'fine': _grid(fine)},
                  'budget': {**STANDARD_SLSQP_BUDGET.as_dict(), 'policy_id': TERMINATION_AWARE_POLICY_ID},
                  'source': source_before, 'input_source': input_source,
                  'input_source_sha256': input_source_sha256,
                  'identity': identity, 'candidate_promotion_blocked': True})
    return {'plan': plan, 'fingerprint': canonical_config_hash(plan)}
