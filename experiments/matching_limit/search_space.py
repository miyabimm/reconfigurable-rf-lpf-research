"""Compatibility facade for the original matching_limit search imports.

The implementations now live in src/lpf/variable_c_layouts.py. The historic
LQP02 alias is retained solely for reproducibility of old search settings.
"""
from pathlib import Path
import sys

_SRC = str(Path(__file__).resolve().parents[2] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from lpf.variable_c_layouts import (  # noqa: E402
    inductor_types,
    enumerate_variable_c_layouts,
)
