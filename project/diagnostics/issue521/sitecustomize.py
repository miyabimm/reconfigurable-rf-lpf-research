"""Separate, opt-in diagnostic trace of Worker RF input vectors.

Activated only for CLI replay processes by ISSUE521_TRACE_OUTPUT. Never used in
plain or deep timing runs. No source, worker method or Runner API is patched.
"""
import atexit
import hashlib
import json
import os
import sys

output = os.environ.get('ISSUE521_TRACE_OUTPUT')
if output:
    h = hashlib.sha256()
    seen = []
    count = [0]
    files = set()
    def observe(frame, event, arg):
        if event == 'call' and frame.f_code.co_name == 'evaluate_with_jacobian':
            filename = frame.f_code.co_filename
            if filename.endswith('/lpf/search/_development_worker.py') and 'vector' in frame.f_locals:
                raw = frame.f_locals['vector'].tobytes()
                h.update(len(raw).to_bytes(8, 'big')); h.update(raw)
                count[0] += 1; files.add(filename)
                if len(seen) < 3:
                    seen.append(hashlib.sha256(raw).hexdigest())
    def finish():
        sys.setprofile(None)
        with open(output, 'x') as stream:
            json.dump({'count': count[0], 'sha256': h.hexdigest(), 'first_raw_sha256': seen,
                       'worker_sources': sorted(files)}, stream, indent=2)
            stream.write('\n')
    atexit.register(finish)
    sys.setprofile(observe)
