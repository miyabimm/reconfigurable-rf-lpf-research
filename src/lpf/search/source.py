"""Source and environment identity for bounded development Runs."""
import hashlib
import os
import platform
import subprocess

import numpy as np
import scipy


def source_identity(root):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args])
    names = sorted(str(p.relative_to(root)) for p in (root/'src').rglob('*.py'))
    names += ['pyproject.toml', 'uv.lock', 'scripts/run_rf_search.py']
    files = {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names}
    return dict(head=git('rev-parse', 'HEAD').decode().strip(), files=files,
                environment=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__,
                    threads={k: os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')}),
                dirty_patch_sha256=hashlib.sha256(git('diff', 'HEAD', '--', 'src', 'pyproject.toml', 'uv.lock', 'scripts/run_rf_search.py')).hexdigest())
