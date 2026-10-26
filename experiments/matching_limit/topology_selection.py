"""Compatibility facade: implementation lives in src/lpf/legacy_graph_search.py.

Historical P2/P3/P4 source is recoverable at main SHA
70fd9d74103077efeee540fdb37c0be5ea0afb7d.
"""
from pathlib import Path
import sys

# Keep historical direct-file imports working without installing an editable package.
_SRC = str(Path(__file__).resolve().parents[2] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from lpf.legacy_graph_search import (  # noqa: E402
    COST, area_thirds, has_signal_path, has_unproductive_internal_leaf,
    topology_signature, select_balanced,
)
