#!/usr/bin/env python3
"""Compatibility entry point for the read-only EXP reservation audit."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / 'src'))
from lpf.cli.audit_experiment_number_registry import main

if __name__ == '__main__':
    main()
