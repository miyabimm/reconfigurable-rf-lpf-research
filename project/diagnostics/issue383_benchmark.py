"""Non-RF descriptive timer overhead benchmark; no scientific output."""
import json
from pathlib import Path
import statistics
import sys
from time import perf_counter_ns

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from lpf.timing import TimerCollector

CHUNKS = 1500
ITERATIONS = 2000
REPEATS = 5


def workload():
    x = 1
    for i in range(ITERATIONS):
        x = (x * 17 + i) % 65521
    return x


def sample(enabled):
    total_start = perf_counter_ns()
    timer = TimerCollector() if enabled else None
    start = perf_counter_ns()
    checksum = 0
    for _ in range(CHUNKS):
        if timer is None:
            checksum += workload()
        else:
            checksum += timer.call('work', workload)
    body = perf_counter_ns() - start
    regions = {} if timer is None else timer.snapshot()
    total = perf_counter_ns() - total_start
    return dict(body_ns=body, total_ns=total, checksum=checksum,
                iterations=CHUNKS * ITERATIONS, timer_region_calls=regions.get('work', {}).get('count', 0),
                timer_clock_calls=2 * regions.get('work', {}).get('count', 0))


def main():
    rows = {'off': [], 'on': []}
    for i in range(REPEATS):
        for enabled in ([False, True] if i % 2 == 0 else [True, False]):
            rows['on' if enabled else 'off'].append(sample(enabled))
    for samples in rows.values():
        assert len({r['checksum'] for r in samples}) == 1
    assert rows['on'][0]['checksum'] == rows['off'][0]['checksum']
    stats = {}
    for name, samples in rows.items():
        stats[name] = {field: dict(median=statistics.median(r[field] for r in samples),
                                   minimum=min(r[field] for r in samples),
                                   maximum=max(r[field] for r in samples))
                       for field in ('body_ns', 'total_ns')}
    print(json.dumps(dict(chunks=CHUNKS, iterations_per_chunk=ITERATIONS, repeats=REPEATS,
                          samples=rows, statistics=stats), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
