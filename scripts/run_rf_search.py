#!/usr/bin/env python3
"""Run a bounded RF profile development plan; not an EXP entry point."""
import argparse
import json
from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.search._development_runner import run
from lpf.search.plan import Loader, ROOT
from lpf.search.storage import canonical


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('develop',))
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--starts', required=True, type=Path, help='JSON seed→arm→{vector, vector_sha256}')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--spot-checks', required=True, help='JSON stage→sample-index list')
    parser.add_argument('--search-bounds', type=Path, help='One complete vector-order JSON box for all Jobs')
    parser.add_argument('--checkpoint-interval-forwards', type=int, default=1000)
    parser.add_argument('--timing-output', type=Path, help='Fresh non-Git JSON file for opt-in inclusive timing')
    parser.add_argument('--timing-level', choices=('timed', 'deep'), help='Requires --timing-output; deep adds Search RF timings')
    parser.add_argument('--rf-cache-mode', choices=('off', 'lk', 'response', 'both'), default='off',
                        help='Search evaluator cache (default: off); Terminal is always uncached')
    args = parser.parse_args(argv)
    if args.timing_level is not None and args.timing_output is None:
        parser.error('--timing-level requires --timing-output')
    try:
        config = yaml.load(args.config.read_text(), Loader=Loader)
        starts = json.loads(args.starts.read_text(), object_pairs_hook=_unique)
        spots = json.loads(args.spot_checks, object_pairs_hook=_unique)
        bounds = json.loads(args.search_bounds.read_text()) if args.search_bounds else None
        state = run(config, starts, args.output, root=ROOT, spot_checks=spots, search_bounds=bounds,
                    checkpoint_interval=args.checkpoint_interval_forwards, timing_output=args.timing_output,
                    timing_level=args.timing_level, rf_cache_mode=args.rf_cache_mode)
        print(canonical(dict(status=state['status'], plan_sha256=state['plan_sha256'],
                             output=str(args.output.resolve()), rf_compliance_certified=False)))
        return 0 if all(j['scientific_status'] == 'converged' for j in state['jobs']) else 4
    except (Exception, KeyboardInterrupt) as exc:
        print(f'STOP: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
