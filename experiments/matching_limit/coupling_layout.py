"""Compatibility facade: canonical coupling-layout code is in src/lpf."""
from pathlib import Path
import sys

# Keep historical direct-file imports working without installing an editable package.
_SRC = str(Path(__file__).resolve().parents[2] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from lpf.coupling_layout import (  # noqa: E402
    admissible_matrix, validate_coupling_matrix, adjacent_patterns,
)
