#!/usr/bin/env python3
"""Run one development-only Worker job; not a formal EXP or production entry."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.search._development_runner import run_development_worker


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--starts', required=True)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--arm', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--checkpoint-interval', type=int, default=100)
    parser.add_argument('--spot-checks', help='JSON object mapping stage to sample-index list')
    args = parser.parse_args(argv)
    try:
        result = run_development_worker(args.config, args.starts, args.seed, args.arm, args.output,
                                        checkpoint_interval=args.checkpoint_interval,
                                        spot_checks=json.loads(args.spot_checks) if args.spot_checks else None)
        print(json.dumps({'status': result['status'], 'output': str(Path(args.output).resolve())}))
        return 0 if result['status'] == 'converged' else 4
    except (Exception, KeyboardInterrupt) as exc:
        print(f'STOP: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
