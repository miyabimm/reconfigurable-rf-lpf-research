"""Standalone checks for external formal experiment management."""
import hashlib
import subprocess
import sys
from pathlib import Path

from .source import source_identity


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


def verify_import_origins(root):
    """Bind loaded project modules and package search paths to tracked source.

    This is an accidental checkout-mixup check, not an import-hook sandbox.
    Dependencies remain covered by the existing environment binding.
    """
    root = Path(root).resolve()
    bases = {'lpf': root/'src/lpf', 'scripts': root/'scripts'}
    for base in bases.values():
        if base.resolve() != base or not base.is_dir():
            raise ValueError('Checkout import root redirects or is missing: ' + str(base))
    tracked = set(subprocess.check_output(['git', 'ls-files', '-z', '--', 'src/lpf', 'scripts'], cwd=root).decode().split('\0'))
    files = source_identity(root)['files']
    for name, module in tuple(sys.modules.items()):
        top = name.split('.')[0]
        if top not in bases:
            continue
        base = bases[top]
        target = base.joinpath(*name.split('.')[1:])
        spec = getattr(module, '__spec__', None)
        if getattr(spec, 'name', None) != name:
            raise ValueError('Checkout import spec mismatch: ' + name)
        origin = getattr(spec, 'origin', None)
        file = getattr(module, '__file__', None)
        paths = getattr(module, '__path__', None)
        locations = getattr(spec, 'submodule_search_locations', None)
        if paths is not None or locations is not None:
            if paths is None or locations is None or not target.is_dir():
                raise ValueError('Checkout import package path missing: ' + name)
            for entries in (paths, locations):
                if not entries or any(Path(p).resolve() != target for p in entries):
                    raise ValueError('Checkout import package path mismatch: ' + name)
        # A real namespace package has no source file, but its search paths
        # must still resolve only to the expected package directory.
        if origin is None and file is None and paths is not None and not (target/'__init__.py').exists():
            continue
        expected = target/'__init__.py' if paths is not None else target.with_suffix('.py')
        if (not origin or not file or Path(origin).resolve() != expected or
                Path(file).resolve() != expected or not expected.is_file()):
            raise ValueError('Checkout import origin mismatch: ' + name)
        relative = expected.relative_to(root).as_posix()
        if relative not in tracked or (top == 'lpf' and
                files.get(relative) != hashlib.sha256(expected.read_bytes()).hexdigest()):
            raise ValueError('Checkout import source untracked or unknown: ' + name)


def verify_checkout(root, constraint_id, expected_sha256, *, allow_trial=False):
    """Check clean, complete checkout and RF identity; not run authorization."""
    from lpf.constraint_versions import constraint_fingerprint, load_constraint, rf_input_file
    from .performance import compile_requirements

    root = Path(root).resolve()
    _complete_checkout(root)
    main = _fresh_main(root)
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=root).strip():
        raise ValueError('Formal checks require a clean checkout')
    if subprocess.run(['git', 'merge-base', '--is-ancestor', main, 'HEAD'], cwd=root).returncode:
        raise ValueError('Checkout does not contain latest main')
    verify_import_origins(root)
    policy = load_constraint(constraint_id, root=root, allow_trial=allow_trial)
    if constraint_fingerprint(policy) != expected_sha256:
        raise ValueError('Constraint effective SHA mismatch')
    bands = rf_input_file(root, policy['bands_file'])
    requirements = compile_requirements(policy, bands)
    inputs = {'bands': hashlib.sha256(bands.read_bytes()).hexdigest()}
    for role in ('input_parasitic', 'output_parasitic'):
        info = policy['external_port_parasitics'][role]
        inputs[role] = hashlib.sha256(rf_input_file(root, info['path']).read_bytes()).hexdigest()
        if inputs[role] != info['sha256']:
            raise ValueError('Fixed S2P SHA mismatch')
    return dict(main=main, constraint_id=constraint_id, effective_sha256=expected_sha256,
                requirements_sha256=requirements.fingerprint, rf_input_sha256=inputs,
                source=source_identity(root))
