"""Atomic development raw records; never a replacement for EXP storage audits."""
from dataclasses import asdict, is_dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile

import numpy as np


def plain(value):
    if is_dataclass(value):
        return plain(asdict(value))
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list, np.ndarray)):
        return [plain(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def canonical(value):
    return json.dumps(plain(value), sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def vector_sha(x):
    a = np.asarray(x, dtype='<f8')
    if a.ndim != 1 or not np.all(np.isfinite(a)):
        raise ValueError('Expected complete finite physical vector')
    return hashlib.sha256(a.tobytes()).hexdigest()


def _atomic_data(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return hashlib.sha256(data).hexdigest()


def atomic(path, value):
    return _atomic_data(path, canonical(value).encode() + b'\n')


def atomic_verified(path, value):
    """Write once, fsync, then verify exact bytes and SHA before returning.

    The caller must treat any exception as STOP, retaining the preceding
    durable unknown reservation. Counters cover this file's payload write and
    readback, not filesystem metadata or parent-ledger writes.
    """
    data = canonical(value).encode() + b'\n'
    digest = _atomic_data(path, data)
    actual = Path(path).read_bytes()
    if actual != data or hashlib.sha256(actual).hexdigest() != digest:
        raise ValueError('Atomic checkpoint readback mismatch')
    return dict(sha256=digest, write_calls=1, written_bytes=len(data),
                read_calls=1, read_bytes=len(actual))
