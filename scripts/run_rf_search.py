#!/usr/bin/env python3
"""Compatibility entry point for the schema2 development CLI."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.cli.run_rf_search import main

if __name__ == '__main__':
    raise SystemExit(main())
