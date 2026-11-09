"""Optional external development supervisor. Scientific files are read-only here."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

import psutil


def _external_fresh(path, root, output):
    path = Path(path).expanduser().resolve()
    if path == Path(root).resolve() or path.is_relative_to(Path(root).resolve()):
        raise ValueError('monitor directory must be outside the checkout')
    if output:
        raw = Path(output).expanduser().resolve()
        if path == raw or path.is_relative_to(raw) or raw.is_relative_to(path):
            raise ValueError('monitor and scientific output must be separate')
    parent = path.parent
    if not parent.is_dir():
        raise ValueError('monitor parent directory must exist')
    check = subprocess.run(['git', '-C', str(parent), 'rev-parse', '--is-inside-work-tree'],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    if check.returncode == 0:
        raise ValueError('monitor directory must be outside Git repositories')
    path.mkdir(exist_ok=False)
    return path


def _observe(output):
    if not output:
        return {'available': False, 'reason': 'output not specified'}
    output = Path(output)
    try:
        parent = json.loads((output / 'run.json').read_bytes())
        jobs = []
        for row in parent['jobs']:
            job = {k: row.get(k) for k in ('job_id', 'seed', 'arm', 'status', 'requested', 'completed', 'reserved')}
            job['checkpoint'] = None
            try:
                raw = json.loads((output / row['raw_path']).read_bytes())
                if raw.get('kind') == 'development_forward_window_v1':
                    job['checkpoint'] = {k: raw.get(k) for k in ('checkpoint_number', 'confirmed', 'uncertain_upper', 'window')}
            except (OSError, ValueError, KeyError):
                pass
            jobs.append(job)
        return {'available': True, 'plan_sha256': parent.get('plan_sha256'),
                'source_sha256': parent.get('source_sha256'), 'status': parent.get('status'), 'jobs': jobs}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {'available': False, 'reason': str(exc)}


def _sample(proc, start, output):
    processes = []
    try:
        children = proc.children(recursive=True)
    except psutil.Error:
        children = []
    for p in [proc, *children]:
        try:
            with p.oneshot():
                cpu = p.cpu_times()
                processes.append(dict(pid=p.pid, parent_pid=p.ppid(), role='cli' if p.pid == proc.pid else 'descendant',
                                      user_s=cpu.user, system_s=cpu.system, rss_bytes=p.memory_info().rss))
        except psutil.Error:
            pass
    return dict(event='sample', monotonic_s=time.monotonic(), elapsed_s=time.monotonic()-start,
                processes=processes, progress=_observe(output))


def _wait_and_sample(child, proc, start, output, interval, stream, errors):
    def interrupt(_signum, _frame):
        errors.append('SIGINT forwarded to CLI process group; awaiting exit')
        try:
            os.killpg(child.pid, signal.SIGINT)
        except ProcessLookupError:
            pass
    previous = signal.signal(signal.SIGINT, interrupt)
    try:
        while True:
            try:
                row = _sample(proc, start, output)
                stream.write(json.dumps(row, sort_keys=True) + '\n')
                stream.flush()
            except (OSError, ValueError, psutil.Error) as exc:
                errors.append(str(exc))
            if child.poll() is not None:
                break
            try:
                child.wait(timeout=interval)
            except subprocess.TimeoutExpired:
                pass
        return child.wait()
    finally:
        signal.signal(signal.SIGINT, previous)


def supervise(command, directory, output, *, profile=False, root, interval=1.0):
    logs = _external_fresh(directory, root, output)
    env = os.environ.copy()
    env['LPF_DEVELOP_MONITOR_EVENTS'] = str(logs / 'optimizer-events.jsonl')
    (logs / 'optimizer-events.jsonl').touch(exist_ok=False)
    start = time.monotonic()
    profiler = None
    profile_status = {'requested': profile, 'available': False, 'rate_hz': 100,
                      'mode': 'py-spy default CPU sampling; no idle, no native, no subprocesses',
                      'target': 'CLI PID', 'sample_count': None, 'exit_code': None}
    samples_error = []
    with (logs / 'stdout.txt').open('x') as stdout, (logs / 'stderr.txt').open('x') as stderr, \
         (logs / 'process.jsonl').open('x', buffering=1) as stream:
        child = subprocess.Popen(command, stdout=stdout, stderr=stderr, env=env, start_new_session=True)
        proc = psutil.Process(child.pid)
        if profile:
            executable = shutil.which('py-spy')
            if executable:
                try:
                    profile_log = (logs / 'profile-stderr.txt').open('x')
                    profiler = subprocess.Popen([executable, 'record', '--pid', str(child.pid), '--rate', '100',
                        '--format', 'speedscope', '--output', str(logs / 'profile.speedscope.json')],
                        stdout=subprocess.DEVNULL, stderr=profile_log)
                except OSError as exc:
                    profile_status['error'] = str(exc)
            else:
                profile_status['error'] = 'py-spy not installed'
        exit_code = _wait_and_sample(child, proc, start, output, interval, stream, samples_error)
        child_wall = time.monotonic() - start
        if profiler:
            if profiler.poll() is None:
                try:
                    profiler.send_signal(signal.SIGINT)
                except ProcessLookupError:
                    pass
            profile_status['exit_code'] = profiler.wait()
            profile_log.close()
        stdout.flush(); stderr.flush(); stream.flush()
    if profile and profiler:
        try:
            data = json.loads((logs / 'profile.speedscope.json').read_bytes())
            profiles = data['profiles']
            profile_status['sample_count'] = sum(len(p.get('samples', [])) for p in profiles)
            profile_status['available'] = profile_status['exit_code'] == 0 and profile_status['sample_count'] > 0
            if profile_status['available']:
                frames = data['shared']['frames']
                counts = {}
                for p in profiles:
                    for stack in p.get('samples', []):
                        # Inclusive counts count each function at most once per sample.
                        for index in set(stack):
                            frame = frames[index]
                            key = (frame.get('name'), frame.get('file'), frame.get('line'))
                            counts[key] = counts.get(key, 0) + 1
                stats = [dict(name=k[0], file=k[1], line=k[2], inclusive_samples=v)
                         for k, v in sorted(counts.items(), key=lambda item: -item[1])]
                (logs / 'profile-functions.json').write_text(json.dumps(stats, indent=2) + '\n')
            else:
                profile_status['error'] = 'py-spy did not produce a successful nonempty profile'
        except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
            profile_status['available'] = False
            profile_status['error'] = str(exc)
    rows = []
    try:
        rows = [json.loads(line) for line in (logs / 'process.jsonl').read_text().splitlines()]
    except (OSError, ValueError) as exc:
        samples_error.append(f'process readback: {exc}')
    events = []
    try:
        events = [json.loads(line) for line in (logs / 'optimizer-events.jsonl').read_text().splitlines()]
    except (OSError, ValueError) as exc:
        samples_error.append(f'optimizer readback: {exc}')
    elapsed = child_wall
    end_events = [e for e in events if e.get('event') == 'local_run_end']
    peak = max((sum(p['rss_bytes'] for p in r['processes']) for r in rows), default=None)
    last = rows[-1] if rows else None
    cpu_rows = [r['processes'] for r in rows if r['processes']]
    last_cpu = cpu_rows[-1] if cpu_rows else []
    progress = last['progress'] if last else {'available': False}
    checkpoints = [j['checkpoint'] for j in progress.get('jobs', [])]
    try:
        forwards = sum(c['confirmed']['forwards'] for c in checkpoints) if checkpoints and all(checkpoints) else None
    except (KeyError, TypeError):
        forwards = None
        samples_error.append('invalid or incomplete checkpoint counts')
    summary = dict(command=command, child_pid=child.pid, exit_code=exit_code, wall_s=elapsed,
        interval_s=interval, peak_observed_rss_bytes=peak,
        last_observed_process_tree_user_s=sum(p['user_s'] for p in last_cpu) if last_cpu else None,
        last_observed_process_tree_system_s=sum(p['system_s'] for p in last_cpu) if last_cpu else None,
        last_observed_process_tree_cpu_s=sum(p['user_s'] + p['system_s'] for p in last_cpu) if last_cpu else None,
        confirmed_forwards=forwards, confirmed_forwards_per_wall_s=forwards/elapsed if forwards is not None and elapsed else None,
        final_observed_progress=progress, optimizer_start_count=sum(e.get('event') == 'local_run_start' for e in events),
        optimizer_end_count=len(end_events), optimizer_wall_s=sum(e['wall_s'] for e in end_events),
        optimizer_cpu_s=sum(e['cpu_s'] for e in end_events), profile=profile_status, errors=samples_error,
        limitations=['RSS is a sampled peak, not an instantaneous maximum.',
                     'Process tree CPU is a snapshot; exited short-lived descendants may be missing.',
                     'Checkpoint counts are observed durable values, not interpolated; parent reservation is authoritative.',
                     'Unpaired optimizer starts are incomplete; optimizer time is separate from total process time.'])
    (logs / 'monitor-summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    return exit_code
