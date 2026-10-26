"""Compatibility facade for historical P4-A graph-to-MNA imports.

The canonical implementation lives in src/lpf/legacy_graph_builder.py.
Historical graph labels, electrical nodes and Q semantics are unchanged.
"""
from pathlib import Path
import sys

_SRC = str(Path(__file__).resolve().parents[2] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from lpf.legacy_graph_builder import (  # noqa: E402
    Q, DEFAULT, AREA_THIRDS, CAP_TYPES,
    branch_q, check_graph, _fixed_parts, _build_settings,
    build_settings, build_grounded_settings,
)
