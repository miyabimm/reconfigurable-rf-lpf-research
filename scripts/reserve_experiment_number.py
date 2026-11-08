#!/usr/bin/env python3
"""Compatibility entry point for the main EXP number reservation writer."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / 'src'))
from lpf.cli.reserve_experiment_number import main

if __name__ == '__main__':
    main()
