#!/usr/bin/env python3
"""Separate non-timed 100k replay: hash ordered optimizer progress callbacks."""
import hashlib
import json
import struct
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
from lpf.search import _development_runner as runner, _development_worker as worker

mode, output = sys.argv[1:]
config = json.loads((ROOT/'project/diagnostics/issue470/config.json').read_text())
starts = json.loads((ROOT/'project/diagnostics/issue470/starts.json').read_text())
batch, partial = {'A': (False, False), 'B': (True, False), 'C': (True, True)}[mode]
config['arms'][0]['steps'][0]['options'].update(max_search_forwards=100000, batch_fd=batch, partial_fd=partial)
config['budget'] = dict(rf_samples=70*100024+476, rf_forwards=100025, independent_mna_samples=2)
original = worker.hybrid_minimize
full = hashlib.sha256(); prefix = hashlib.sha256(); counter = [0]

def capture(*args, **kw):
    key = 'progress_callback' if batch else 'objective_callback'
    progress = kw[key]
    def observe(x, f, *extra):
        counter[0] += 1
        data = struct.pack('<'+'d'*len(x)+'d', *x, f)
        full.update(data)
        if counter[0] <= 100000: prefix.update(data)
        progress(x, f, *extra)
    kw[key] = observe
    return original(*args, **kw)

with patch.object(worker, 'hybrid_minimize', capture):
    runner.run(config, starts, output, root=ROOT, spot_checks={'terminal':[0,111]},
               checkpoint_interval=1000, rf_cache_mode='lk')
print(json.dumps(dict(mode=mode, callbacks=counter[0], sha256=full.hexdigest(), prefix_100000_sha256=prefix.hexdigest())))
