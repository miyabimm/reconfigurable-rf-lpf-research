"""Shared full-evidence checkout and remote-main checks for campaign gates."""
import subprocess
from pathlib import Path


def _complete_checkout(root):
    root = Path(root)
    for name in ('data/experiment_number_registry.csv', 'data/phase2_git_storage_budget.json',
                 'experiments', 'rf/bands.csv'):
        if not (root / name).exists():
            raise ValueError('Full checkout required; missing ' + name)
    sparse = subprocess.run(['git', 'config', '--bool', 'core.sparseCheckout'], cwd=root,
                            capture_output=True, text=True)
    if sparse.stdout.strip() == 'true':
        raise ValueError('Full checkout required; sparse checkout is not sufficient')
    tracked = subprocess.check_output(['git', 'ls-files', '-z', '--', 'data', 'experiments'], cwd=root)
    for name in filter(None, tracked.split(b'\0')):
        path = root / name.decode('utf-8')
        if not path.exists():
            raise ValueError('Full checkout required; missing tracked evidence: ' + name.decode('utf-8'))


def _fresh_main(root):
    local = subprocess.check_output(['git', 'rev-parse', 'refs/remotes/origin/main'], cwd=root, text=True).strip()
    remote = subprocess.check_output(['git', 'ls-remote', '--exit-code', 'origin', 'refs/heads/main'],
                                     cwd=root, text=True).split()
    if len(remote) != 2 or remote[0] != local or remote[1] != 'refs/heads/main':
        raise ValueError('origin/main is stale or unavailable; fetch and recheck')
    return local
