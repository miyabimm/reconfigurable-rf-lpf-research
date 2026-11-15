"""One development-only Worker invocation; not a production or EXP runner."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from lpf.constraint_versions import constraint_fingerprint, load_constraint
from ._development_worker import DevelopmentWorker, _save_checkpoint
from ._job_evaluation import source_identity
from .plan import ROOT, load_preflight
from .proposals import definition_from_data
from .starts import load_explicit
from .storage import canonical, sha, vector_sha


def run_development_worker(config, starts, seed, arm, output, *, root=ROOT,
                           checkpoint_interval=100, spot_checks=None):
    """Run exactly one seed/arm, preserving input and append-only Worker events.

    No budget ledger, retry, resume, or formal experiment protection is provided.
    Exceptions propagate, including failures to save or read back the result.
    """
    root = Path(root).resolve()
    output = Path(output).expanduser().resolve()
    if (not output.is_relative_to(Path(tempfile.gettempdir()).resolve()) or
            output.is_relative_to(root) or not output.parent.is_dir()):
        raise ValueError('Fresh system temporary output outside Git checkout required')
    probe = subprocess.run(['git', '-C', str(output.parent), 'rev-parse', '--is-inside-work-tree'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if probe.returncode == 0:
        raise ValueError('Output must be outside Git checkouts')
    plan = load_preflight(config, root=root)
    cfg = plan.data['config']
    ref = cfg['definition']
    if ref is None:
        raise ValueError('Explicit complete definition required')
    data = ref if 'inductor_tree' in ref else json.loads((root / ref['path']).read_bytes())
    definition = definition_from_data(data)
    policy = load_constraint(cfg['rf']['constraint_id'], root=root, allow_trial=cfg['rf']['allow_trial'])
    entries = load_explicit(starts)
    if type(seed) is not int or seed not in cfg['seeds'] or seed not in entries:
        raise ValueError('Seed must occur in Plan and explicit starts')
    if not any(a['name'] == arm for a in cfg['arms']):
        raise ValueError('Arm must occur in Plan')
    start = entries[seed]
    if not isinstance(start, dict) or set(start) != {'vector', 'vector_sha256'} or vector_sha(start['vector']) != start['vector_sha256']:
        raise ValueError('Explicit start vector/SHA mismatch')
    source = source_identity(root)
    script = root / 'scripts/run_development_worker.py'
    source['files']['scripts/run_development_worker.py'] = hashlib.sha256(script.read_bytes()).hexdigest()
    record = dict(kind='development_worker_input_v1', plan=plan.data, plan_sha256=plan.sha256,
                  definition=asdict(definition), definition_sha256=sha(asdict(definition)),
                  policy_id=cfg['rf']['constraint_id'], policy_fingerprint=constraint_fingerprint(policy),
                  seed=seed, arm=arm, start=start, checkpoint_interval=checkpoint_interval,
                  spot_checks=spot_checks, source=source, source_sha256=sha(source))
    # mkdir itself is exclusive: neither an existing job nor its files are touched.
    output.mkdir(exist_ok=False)
    _save_checkpoint(output / 'input.json', record)
    worker = DevelopmentWorker(plan, definition, policy, arm, seed, start['vector'], start['vector_sha256'],
                               root=root, checkpoint=output / 'checkpoints',
                               checkpoint_interval=checkpoint_interval, spot_checks=spot_checks)
    result = worker.run()
    _save_checkpoint(output / 'result.json', result)
    if canonical(json.loads((output / 'result.json').read_text())) != canonical(result):
        raise ValueError('Result readback mismatch')
    return result
