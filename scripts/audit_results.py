#!/usr/bin/env python3
"""Compatibility entry point for the read-only candidate and provenance audit."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / 'src'))
from lpf.cli import audit_results as implementation

if __name__ == '__main__':
    implementation.main()
else:
    # Existing callers patch module globals such as ROOT; preserve that contract.
    sys.modules[__name__] = implementation
