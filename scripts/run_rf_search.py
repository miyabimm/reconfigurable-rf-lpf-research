#!/usr/bin/env python3
"""Schema2 development run only; no EXP or production authorization."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import json
from lpf.search.plan import load_preflight, ROOT
from lpf.search.runner import run_development, finalize_development
from lpf.search.starts import load_explicit
from lpf.search.storage import canonical


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('develop',))
    parser.add_argument('--config', required=True)
    parser.add_argument('--mode', choices=('fixture', 'production'), default='fixture')
    parser.add_argument('--output')
    parser.add_argument('--starts', help='JSON seed→{vector, vector_sha256}')
    parser.add_argument('--spot-checks', help='JSON stage→sample-index list')
    parser.add_argument('--storage-mode', choices=('legacy', 'window100'), default='legacy',
                        help='window100 is opt-in development-only; requires a persistent Git-external output')
    parser.add_argument('--debug-forward-history', action='store_true',
                        help='window100 only: persist compact search history at checkpoints')
    args = parser.parse_args(argv)
    try:
        if args.mode == 'production':
            print('STOP: production_not_authorized: G0/G1 and G2-G5 not connected', file=sys.stderr)
            return 3
        if not args.output or not args.starts:
            raise ValueError('develop requires --starts and a fresh system tmp --output')
        plan = load_preflight(args.config)
        config = plan.data['config']
        if config['definition'] is None:
            raise ValueError('develop requires an explicit complete definition')
        from lpf.constraint_versions import load_constraint
        from lpf.topology_management import CircuitDefinition, InductorTree, CapacitorPlacement
        definition = json.loads((ROOT / config['definition']['path']).read_bytes())
        definition['inductor_tree'] = InductorTree(**definition['inductor_tree'])
        definition['capacitor_placement'] = CapacitorPlacement(**definition['capacitor_placement'])
        definition = CircuitDefinition(**definition)
        policy = load_constraint(config['rf']['constraint_id'], allow_trial=config['rf']['allow_trial'])
        starts = load_explicit(args.starts)
        spots = json.loads(args.spot_checks) if args.spot_checks else None
        state = run_development(plan, definition, policy, starts, args.output, spot_checks=spots,
                                storage_mode=args.storage_mode, debug_forward_history=args.debug_forward_history)
        summary = finalize_development(state, args.output)
        print(canonical(summary))
        return summary['exit_code']
    except (Exception, KeyboardInterrupt) as exc:
        print(f'STOP: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
