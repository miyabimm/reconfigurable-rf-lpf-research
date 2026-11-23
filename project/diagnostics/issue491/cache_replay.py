#!/usr/bin/env python3
"""Replay one 100k trace and expose the otherwise unsaved plain L/k counters."""
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
spec = importlib.util.spec_from_file_location('issue487_measure', ROOT/'project/diagnostics/issue487/measure.py')
measure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measure)
from lpf.rf_core.model import RFModel
original = RFModel.evaluator
search = []
def capture(self, grid, **kwargs):
    evaluator = original(self, grid, **kwargs)
    if kwargs.get('cache_mode') == 'lk':
        search.append(evaluator)
    return evaluator
with patch.object(RFModel, 'evaluator', capture):
    measure.child(sys.argv[1], 100000, Path(sys.argv[2]), trace=True)
assert len(search) == 1
print(json.dumps(dict(search_cache=search[0].cache_stats)))
