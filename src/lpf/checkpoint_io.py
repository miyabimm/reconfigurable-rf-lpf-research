"""Shared deterministic run-configuration hashes and crash-safe JSON writes.

No P4-A-specific checkpoint schema, shard counters or RF result policy lives
here. Format and file durability are preserved from legacy p4_sharding.py.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

def canonical_config_hash(config) -> str:
    encoded = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def atomic_write_json(path, payload) -> None:
    """Write a JSON checkpoint with fsync plus same-directory atomic replace."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, target)
        try:
            directory_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            # The file itself is already durable enough for platforms without
            # directory fsync support.
            pass
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


