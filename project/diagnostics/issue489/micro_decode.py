#!/usr/bin/env python3
"""Fixed 25-candidate decode microbenchmark, one independent process per side."""
import hashlib
import json
from pathlib import Path
import sys
import time

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root/'src'))
import numpy as np
from lpf.rf_core.coupled_lc import ParameterVectorSchema

x = np.array(json.loads((root/'project/diagnostics/issue470/starts.json').read_text())['1013']['baseline']['vector'])
vectors = np.tile(x, (25, 1))
for i in range(25):
    vectors[i, i] += 1e-6
schema = ParameterVectorSchema(4, 4, 3, 2, 2)
if hasattr(schema, 'decode_batch'):
    decode = lambda: schema.decode_batch(vectors)
else:
    def decode():
        values = [schema.decode(row) for row in vectors]
        return (np.asarray([v.inductances_nh for v in values]),
                np.asarray([v.coupling_k for v in values]),
                np.asarray([v.capacitors_pf_by_setting for v in values]))
for _ in range(100):
    decode()
t = time.perf_counter()
for _ in range(2000):
    result = decode()
elapsed = time.perf_counter() - t
print(json.dumps(dict(seconds=elapsed, iterations=2000, input_sha256=hashlib.sha256(vectors.tobytes()).hexdigest(),
                      output_sha256=hashlib.sha256(b''.join(a.tobytes() for a in result)).hexdigest())))
