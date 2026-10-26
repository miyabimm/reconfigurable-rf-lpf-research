"""Compatibility facade for historical node-balanced topology sampling."""
from pathlib import Path
import sys

# Keep historical direct-file imports working without installing an editable package.
_SRC = str(Path(__file__).resolve().parents[2] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from lpf.legacy_graph_search import select_node_balanced  # noqa: E402
