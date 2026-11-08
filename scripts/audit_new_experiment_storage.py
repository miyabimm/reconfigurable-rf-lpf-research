#!/usr/bin/env python3
"""Compatibility entry point for the EXP storage audit."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / 'src'))
from lpf.experiment_storage_audit import *  # noqa: F403
from lpf.experiment_storage_audit import main

if __name__ == '__main__':
    main()
