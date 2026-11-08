#!/usr/bin/env python3
"""Compatibility entry point for the read-only research catalog audit."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / 'src'))
from lpf.cli.audit_research_catalog import *  # noqa: F403
from lpf.cli.audit_research_catalog import _csv, _json, _path, _source_metrics, main

if __name__ == '__main__':
    main()
