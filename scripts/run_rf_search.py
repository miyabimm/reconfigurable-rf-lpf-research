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


def _timing_path(value, output):
    import subprocess
    path = Path(value).expanduser().resolve()
    if not path.parent.is_dir() or path.exists():
        raise ValueError('timing output must be a fresh file in an existing directory')
    if output:
        raw = Path(output).expanduser().resolve()
        if path == raw or path.is_relative_to(raw) or raw.is_relative_to(path):
            raise ValueError('timing output and scientific output must be separate')
    check = subprocess.run(['git', '-C', str(path.parent), 'rev-parse', '--is-inside-work-tree'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if check.returncode == 0:
        raise ValueError('timing output must be outside Git repositories')
    return path


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
    parser.add_argument('--monitor-dir', help='fresh Git-external monitoring directory')
    parser.add_argument('--profile', action='store_true', help='use optional py-spy child profiling (requires --monitor-dir)')
    parser.add_argument('--timing-output', help='fresh Git-external JSON file for internal inclusive timings')
    args = parser.parse_args(argv)
    if args.profile and not args.monitor_dir:
        parser.error('--profile requires --monitor-dir')
    if args.timing_output and args.monitor_dir:
        parser.error('--timing-output and --monitor-dir are separate modes')
    timing_path = None
    timing_jobs = []
    timing_status = 'incomplete'
    timing_summary = None
    try:
        if args.timing_output:
            from time import perf_counter_ns
            timing_path = _timing_path(args.timing_output, args.output)
            timing_start = perf_counter_ns()
        if args.monitor_dir:
            from lpf.search.monitor import supervise
            raw = list(sys.argv[1:] if argv is None else argv)
            forwarded = []
            i = 0
            while i < len(raw):
                token = raw[i]
                option, separator, _ = token.partition('=')
                # argparse accepts unique long-option abbreviations as well as =.
                if option.startswith('--') and len(option) > 2 and '--monitor-dir'.startswith(option):
                    i += 1 if separator else 2
                elif option.startswith('--') and len(option) > 2 and '--profile'.startswith(option):
                    i += 1
                else:
                    forwarded.append(raw[i])
                    i += 1
            return supervise([sys.executable, str(Path(__file__).resolve()), *forwarded],
                             args.monitor_dir, args.output, profile=args.profile, root=ROOT)
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
        options = {'timing_jobs': timing_jobs} if timing_path is not None else {}
        state = run_development(plan, definition, policy, starts, args.output, spot_checks=spots,
                                storage_mode=args.storage_mode, debug_forward_history=args.debug_forward_history,
                                **options)
        summary = finalize_development(state, args.output)
        timing_summary = {k: summary.get(k) for k in ('exit_code', 'development_flow', 'plan_sha256', 'source_sha256')}
        timing_status = 'completed' if summary['development_flow'] == 'completed' else 'incomplete'
        print(canonical(summary))
        return summary['exit_code']
    except (Exception, KeyboardInterrupt) as exc:
        print(f'STOP: {exc}', file=sys.stderr)
        return 2
    finally:
        if timing_path is not None:
            elapsed = perf_counter_ns() - timing_start
            try:
                jobs = [{**{k: v for k, v in job.items() if k != 'timer'},
                         'regions': job['timer'].snapshot()} for job in timing_jobs]
                report = dict(kind='development_internal_timing_v1', status=timing_status,
                    summary=timing_summary, total_wall_ns=elapsed,
                    total=dict(count=1, wall_ns=elapsed, mean_wall_ns=elapsed), jobs=jobs,
                    missing='Absent regions were not observed; Hybrid events are unverified; '
                            'forced termination may leave no file',
                    containment='Inclusive: total excludes diagnostic JSON save and contains jobs; '
                                'job_worker contains solver; solver contains solver_callback; '
                                'solver_callback contains evaluation; evaluation contains physical_validation, '
                                'rf_forward, requirements and some checkpoint work. '
                                'window_checkpoint_save contains source_contract and can also occur outside evaluation; '
                                'Hybrid local runs/restarts are inside solver. Regions overlap: do not sum.')
                with timing_path.open('x', encoding='utf-8') as stream:
                    json.dump(report, stream, sort_keys=True, allow_nan=False)
                    stream.write('\n')
            except Exception as exc:
                print(f'internal timing incomplete: {exc}', file=sys.stderr)


if __name__ == '__main__':
    raise SystemExit(main())
