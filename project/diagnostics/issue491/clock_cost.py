#!/usr/bin/env python3
"""Illustrative clock/accumulator micro-cost, not an RF timing correction."""
import json
from pathlib import Path
import sys
from time import perf_counter_ns

sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'src'))
from lpf.timing import TimerCollector

N = 300_000
rows = []
for _ in range(5):
    row = {}
    for mode in ('loop', 'clock_pair', 'clock_pair_add'):
        timer = TimerCollector()
        start = perf_counter_ns()
        for i in range(N):
            if mode == 'clock_pair':
                a = perf_counter_ns(); elapsed = perf_counter_ns() - a
            elif mode == 'clock_pair_add':
                a = perf_counter_ns(); elapsed = perf_counter_ns() - a
                timer.add('sample', elapsed, failed=False)
        row[mode+'_ns_per_iteration'] = (perf_counter_ns() - start) / N
    rows.append(row)
print(json.dumps(dict(iterations=N, rows=rows), indent=2))
