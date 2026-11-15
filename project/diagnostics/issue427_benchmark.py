"""Bounded timing diagnostic only; no formal EXP, no recoverable solver state."""
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
from time import perf_counter
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
import numpy as np
import scipy
from lpf.constraint_versions import load_constraint
from lpf.search import _worker_next, _development_worker
from lpf.search._development_worker import DevelopmentWorker
from lpf.search._worker_next import MinimalWorker
from lpf.search._job_evaluation import source_identity
from lpf.search.plan import load_preflight
from lpf.search.proposals import definition_from_data
from lpf.search.starts import load_explicit
from lpf.search.storage import sha, vector_sha


def main():
    plan = load_preflight(ROOT/'project/diagnostics/issue377/baseline.yaml')
    cfg = plan.data['config']
    definition = definition_from_data(json.loads((ROOT/cfg['definition']['path']).read_bytes()))
    policy = load_constraint(cfg['rf']['constraint_id'], root=ROOT, allow_trial=True)
    start = load_explicit(ROOT/'project/diagnostics/issue401_starts_1002.json')[1002]
    identity = source_identity(ROOT)
    results = []
    with tempfile.TemporaryDirectory(prefix='issue427-benchmark-') as tmp:
        for index, kind in enumerate(('minimal', 'development', 'development', 'minimal',
                                      'minimal', 'development')):
            t = perf_counter()
            args = (plan, definition, policy, 'hybrid', 1002, start['vector'], start['vector_sha256'])
            worker = (MinimalWorker(*args, root=ROOT) if kind == 'minimal' else
                      DevelopmentWorker(*args, root=ROOT, checkpoint=Path(tmp)/f'{index}-checkpoints'))
            ready = perf_counter()
            clock = {'solver': 0., 'checkpoint_io': 0., 'writes': 0}
            real_solver, real_save = _worker_next.hybrid_minimize, _development_worker._save_checkpoint
            def solver(*a, **kw):
                t0 = perf_counter()
                try:
                    return real_solver(*a, **kw)
                finally:
                    clock['solver'] += perf_counter()-t0
            def save(*a, **kw):
                t0 = perf_counter()
                try:
                    return real_save(*a, **kw)
                finally:
                    clock['checkpoint_io'] += perf_counter()-t0
                    clock['writes'] += 1
            if kind == 'minimal':
                out = worker.solve()
                solver_s = perf_counter()-ready
                count, best = out.nfev, vector_sha(out.best_x)
                reason = out.stop_reason
            else:
                with patch.object(_worker_next, 'hybrid_minimize', solver), patch.object(_development_worker, '_save_checkpoint', save):
                    out = worker.run()
                solver_s = clock['solver']
                count = out['steps'][0]['forward_count']
                best = vector_sha(out['steps'][0]['solver_result']['best_x'])
                reason = out['steps'][0]['stop_reason']
            end = perf_counter()
            results.append(dict(kind=kind, warmup=index < 2, setup_s=ready-t,
                                solver_s=solver_s, checkpoint_io_s=clock['checkpoint_io'],
                                checkpoint_writes=clock['writes'], total_s=end-t,
                                forward_count=count, solver_best_sha256=best, stop_reason=reason))
    print(json.dumps(dict(head=identity['head'], source_sha256=sha(identity), source_identity=identity,
          plan_sha256=plan.sha256, policy_id=policy['active_constraint_id'],
          policy_fingerprint=plan.data['requirements']['policy_fingerprint'],
          rf_inputs=plan.data['rf_inputs'], grid=plan.data['grids']['hybrid/coarse'],
          initial_vector_sha256=start['vector_sha256'], seed=1002, interval=100,
          environment=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__,
                           threads={k: os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')}),
          runs=results, limitations='Development total includes Selection/Terminal; Minimal total does not. Solver regions include checkpoint I/O only for development; timing hooks on development only. No continuous or RF compliance claim.'), sort_keys=True))


if __name__ == '__main__':
    main()
