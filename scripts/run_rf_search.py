#!/usr/bin/env python3
"""Read-only preflight or bounded synthetic fixture run; no EXP execution."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.search.plan import load
from lpf.search.runner import run
from lpf.search.storage import canonical


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('preflight', 'run'))
    parser.add_argument('--config', required=True)
    parser.add_argument('--mode', choices=('fixture', 'production'), default='fixture')
    parser.add_argument('--output')
    args = parser.parse_args(argv)
    try:
        plan = load(args.config)
        if args.command == 'preflight':
            print(canonical({'plan_sha256': plan.sha256, 'plan': plan.data,
                             'execution_authorized': False}))
            return 0
        if not args.output:
            parser.error('run requires a fresh --output directory')
        state = run(plan, args.output, mode=args.mode)
        print(canonical({'status': state['status'], 'output': args.output}))
        return 0 if state['status'] == 'completed' else 1
    except (ValueError, OSError) as exc:
        print(f'STOP: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
