#!/usr/bin/env python3
"""Synthetic timer overhead calibration: no RF calls, no scientific search."""
import hashlib
import json
from pathlib import Path
import platform
import statistics
import time

from lpf.timing import TimerCollector
from issue401_timing import _wrap


def noop():
    return None


def measure(mode, count):
    timer = TimerCollector()
    function = noop
    if mode in ('wrapped', 'nested'):
        function = _wrap(timer, 'inner', function)
    if mode == 'nested':
        function = _wrap(timer, 'outer', function)
    wall, cpu = time.perf_counter_ns(), time.process_time_ns()
    for _ in range(count):
        function()
    wall, cpu = time.perf_counter_ns() - wall, time.process_time_ns() - cpu
    snapshot = timer.snapshot()
    assert all(row['count'] == count and row['failed'] == 0 for row in snapshot.values())
    return dict(mode=mode, wall_ns=wall, cpu_ns=cpu, count=count, regions=snapshot)


def main():
    count, repeats = 20000, 10
    warmup = [measure(mode, count) for mode in ('plain', 'wrapped', 'nested')]
    rows = []
    for i in range(repeats):
        order = ('plain', 'wrapped', 'nested') if i % 2 == 0 else ('nested', 'wrapped', 'plain')
        rows.append({mode: measure(mode, count) for mode in order})
    deltas = {mode: [(row[mode]['wall_ns'] - row['plain']['wall_ns']) / count for row in rows]
              for mode in ('wrapped', 'nested')}
    print(json.dumps(dict(kind='synthetic_only', count=count, warmup=warmup, runs=rows,
        delta_ns_per_call=deltas,
        median_delta_ns_per_call={k: statistics.median(v) for k, v in deltas.items()},
        script_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        python=platform.python_version(), platform=platform.platform(),
        limitations='loop and clock overhead included; shared host; not a measurement of RF-path overhead'),
        sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
