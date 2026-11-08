#!/usr/bin/env python3
"""Compatibility entry point for the curated Pareto report CLI."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / 'src'))
from lpf.cli.report_research_pareto import *  # noqa: F403
from lpf.cli.report_research_pareto import _rows, main

if __name__ == '__main__':
    main()
