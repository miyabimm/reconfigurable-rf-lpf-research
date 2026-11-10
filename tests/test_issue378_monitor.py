from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import numpy as np
from scipy.optimize import OptimizeResult

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from lpf.search.monitor import supervise
from lpf.optimizers.hybrid import hybrid_minimize


class MonitorTests(unittest.TestCase):
    def test_exit_codes_and_missing_profiler(self):
        with tempfile.TemporaryDirectory(prefix='issue378-test-') as tmp:
            for code in (0, 2, 3, 4):
                with self.subTest(code=code), patch('lpf.search.monitor.shutil.which', return_value=None):
                    directory = Path(tmp) / str(code)
                    result = supervise([sys.executable, '-c', f'import sys; sys.exit({code})'],
                                       directory, None, profile=True, root=ROOT, interval=.02)
                    self.assertEqual(result, code)
                    summary = json.loads((directory / 'monitor-summary.json').read_text())
                    self.assertEqual(summary['exit_code'], code)
                    self.assertFalse(summary['profile']['available'])
                    self.assertEqual(summary['profile']['error'], 'py-spy not installed')
                    self.assertIsNone(summary['confirmed_forwards'])
                    self.assertEqual(summary['optimizer_event_status'], 'unverified')
                    self.assertTrue((directory / 'process.jsonl').read_text())
                    with self.assertRaises(FileExistsError):
                        supervise([sys.executable, '-c', 'pass'], directory, None, root=ROOT)

    def test_cli_delegation_and_option_validation(self):
        script = ROOT/'scripts/run_rf_search.py'
        with tempfile.TemporaryDirectory(prefix='issue378-cli-') as tmp:
            logs = Path(tmp)/'logs'
            args = [sys.executable, str(script), 'develop', '--config', 'missing', '--mode', 'production']
            plain = subprocess.run(args, capture_output=True, text=True)
            monitored = subprocess.run(args + ['--monitor-dir', str(logs)], capture_output=True, text=True)
            self.assertEqual((plain.returncode, monitored.returncode), (3, 3))
            self.assertIn('production_not_authorized', (logs/'stderr.txt').read_text())
            self.assertEqual(json.loads((logs/'monitor-summary.json').read_text())['exit_code'], 3)
            abbreviated = Path(tmp)/'abbreviated'
            result = subprocess.run(args + [f'--monitor-d={abbreviated}'], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 3)
            self.assertEqual(json.loads((abbreviated/'monitor-summary.json').read_text())['exit_code'], 3)
            invalid = subprocess.run(args + ['--profile'], capture_output=True, text=True)
            self.assertEqual(invalid.returncode, 2)
            self.assertIn('--profile requires --monitor-dir', invalid.stderr)

    def test_sampling_failure_does_not_retry_or_change_exit(self):
        with tempfile.TemporaryDirectory(prefix='issue378-failure-') as tmp:
            logs = Path(tmp)/'logs'
            marker = Path(tmp)/'calls'
            cmd = [sys.executable, '-c', f"from pathlib import Path; Path({str(marker)!r}).open('a').write('x'); raise SystemExit(4)"]
            with patch('lpf.search.monitor._sample', side_effect=OSError('sample failed')):
                self.assertEqual(supervise(cmd, logs, None, root=ROOT, interval=.02), 4)
            self.assertEqual(marker.read_text(), 'x')
            summary = json.loads((logs/'monitor-summary.json').read_text())
            self.assertIn('sample failed', summary['errors'])
            self.assertEqual(summary['exit_code'], 4)

    def test_post_run_log_failures_preserve_child_exit(self):
        from lpf.search import monitor
        real_write = Path.write_text
        real_open = Path.open
        real_wait = monitor._wait_and_sample
        with tempfile.TemporaryDirectory(prefix='issue378-post-failure-') as tmp:
            for code in (0, 4):
                for failure in ('summary', 'flush', 'close'):
                    with self.subTest(code=code, failure=failure):
                        logs = Path(tmp)/f'{code}-{failure}'
                        marker = Path(tmp)/f'{code}-{failure}-calls'
                        cmd = [sys.executable, '-c', f"from pathlib import Path; Path({str(marker)!r}).open('a').write('x'); raise SystemExit({code})"]
                        def write(path, *args, **kwargs):
                            if failure == 'summary' and path.name == 'monitor-summary.json':
                                raise OSError('summary write failed')
                            return real_write(path, *args, **kwargs)
                        def wait(child, proc, start, output, interval, stream, errors):
                            result = real_wait(child, proc, start, output, interval, stream, errors)
                            if failure == 'flush':
                                stream.flush = Mock(side_effect=OSError('final flush failed'))
                            return result
                        def open_file(path, *args, **kwargs):
                            stream = real_open(path, *args, **kwargs)
                            if failure == 'close' and path.name == 'process.jsonl' and args and args[0] == 'x':
                                class CloseFailure:
                                    def __enter__(self):
                                        return stream
                                    def __exit__(self, *args):
                                        stream.close()
                                        raise OSError('close failed')
                                return CloseFailure()
                            return stream
                        error = io.StringIO()
                        with patch.object(Path, 'write_text', write), patch.object(Path, 'open', open_file), \
                             patch.object(monitor, '_wait_and_sample', wait), redirect_stderr(error):
                            self.assertEqual(supervise(cmd, logs, None, root=ROOT, interval=.02), code)
                        self.assertEqual(marker.read_text(), 'x')
                        self.assertIn('monitoring incomplete', error.getvalue())
                        self.assertFalse((logs/'monitor-summary.json').exists())

    def test_unpaired_optimizer_event_is_incomplete(self):
        with tempfile.TemporaryDirectory(prefix='issue378-unpaired-') as tmp:
            logs = Path(tmp)/'logs'
            workload = "import os; open(os.environ['LPF_DEVELOP_MONITOR_EVENTS'], 'a').write('{\"event\":\"local_run_start\"}\\n')"
            self.assertEqual(supervise([sys.executable, '-c', workload], logs, None, root=ROOT, interval=.02), 0)
            summary = json.loads((logs/'monitor-summary.json').read_text())
            self.assertEqual((summary['optimizer_start_count'], summary['optimizer_end_count']), (1, 0))
            self.assertEqual(summary['optimizer_event_status'], 'incomplete')

    def test_missing_restart_event_is_incomplete(self):
        with tempfile.TemporaryDirectory(prefix='issue381-missing-') as tmp:
            logs = Path(tmp)/'logs'
            events = [dict(event='local_run_start', seed=9, run_index=1),
                      dict(event='local_run_end', seed=9, run_index=1, wall_s=1, cpu_s=1)]
            workload = ("import os; open(os.environ['LPF_DEVELOP_MONITOR_EVENTS'], 'a').write("
                        + repr(''.join(json.dumps(e) + '\n' for e in events)) + ")")
            self.assertEqual(supervise([sys.executable, '-c', workload], logs, None, root=ROOT, interval=.02), 0)
            summary = json.loads((logs/'monitor-summary.json').read_text())
            self.assertEqual(summary['restart_generated_count'], 0)
            self.assertEqual(summary['restart_missing_key_count'], 1)
            self.assertEqual(summary['optimizer_event_status'], 'incomplete')

    def test_profile_sampled_function_counts(self):
        with tempfile.TemporaryDirectory(prefix='issue378-spy-') as tmp:
            fake = Path(tmp)/'py-spy'
            fake.write_text('#!'+sys.executable+'\n' + '''
import json, subprocess, sys
out = sys.argv[sys.argv.index('--output')+1]
subprocess.run(sys.argv[sys.argv.index('--')+1:], close_fds=False)
with open(out, 'w') as f:
    json.dump({'shared': {'frames': [{'name':'f'}, {'name':'g'}]},
               'profiles': [{'name': 'Process ' + open(out+'.pid').read() + ' Thread 1',
                             'samples': [[0,1], [0], [0,0]]}]}, f)
''')
            fake.chmod(0o755)
            directory = Path(tmp)/'logs'
            with patch('lpf.search.monitor.shutil.which', return_value=str(fake)):
                pid_path = directory/'profile.speedscope.json.pid'
                workload = f'import os; from pathlib import Path; Path({str(pid_path)!r}).write_text(str(os.getpid()))'
                rc = supervise([sys.executable, '-c', workload],
                               directory, None, profile=True, root=ROOT, interval=.02)
            self.assertEqual(rc, 0)
            summary = json.loads((directory/'monitor-summary.json').read_text())
            self.assertTrue(summary['profile']['available'])
            self.assertTrue(summary['profile']['target_exec_samples_unverified'])
            self.assertEqual(summary['profile']['target_pid'], summary['child_pid'])
            self.assertEqual(summary['profile']['sample_count'], 3)
            stats = json.loads((directory/'profile-functions.json').read_text())
            self.assertEqual([(x['name'], x['inclusive_samples']) for x in stats], [('f',3),('g',1)])

    def test_progress_is_durable_snapshot_not_interpolation(self):
        from lpf.search.monitor import _observe
        with tempfile.TemporaryDirectory(prefix='issue378-progress-') as tmp:
            path = Path(tmp)
            (path / 'run.json').write_text(json.dumps({'plan_sha256':'abc', 'jobs':[
                {'job_id':'job', 'seed':1, 'status':'unknown', 'reserved':100, 'raw_path':'job.json'}]}))
            (path / 'job.json').write_text(json.dumps({'kind':'development_forward_window_v1',
                'checkpoint_number':2, 'confirmed':{'forwards':100, 'requested':300, 'completed':300},
                'uncertain_upper':{'forwards':200}, 'window':{'reserved_samples':300}}))
            job = _observe(path)['jobs'][0]
            self.assertEqual(job['reserved'], 100)
            self.assertEqual(job['checkpoint']['confirmed']['forwards'], 100)
            self.assertEqual(job['checkpoint']['uncertain_upper']['forwards'], 200)
            self.assertEqual(_observe(path)['plan_sha256'], 'abc')

    def test_reject_nested_or_git_directory(self):
        with tempfile.TemporaryDirectory(prefix='issue378-nested-') as tmp:
            with self.assertRaises(ValueError):
                supervise([sys.executable, '-c', 'pass'], Path(tmp)/'out'/'monitor', Path(tmp)/'out', root=ROOT)
            with self.assertRaises(ValueError):
                supervise([sys.executable, '-c', 'pass'], ROOT/'monitor-not-created', None, root=ROOT)

    def test_interrupt_preserves_exit(self):
        with tempfile.TemporaryDirectory(prefix='issue378-interrupt-') as tmp:
            directory = Path(tmp)/'logs'
            ready = Path(tmp)/'ready'
            workload = f"from pathlib import Path; import time; Path({str(ready)!r}).touch(); time.sleep(30)"
            code = ("import sys; sys.path.insert(0,sys.argv[1]); from lpf.search.monitor import supervise; "
                    f"sys.exit(supervise([sys.executable,'-c',{workload!r}],sys.argv[2],None,root=sys.argv[3],interval=.02))")
            process = subprocess.Popen([sys.executable, '-c', code, str(ROOT/'src'), str(directory), str(ROOT)],
                                       start_new_session=True)
            try:
                deadline = time.monotonic()+10
                while not ready.exists():
                    if time.monotonic() > deadline:
                        self.fail('child did not start')
                    time.sleep(.02)
                os.killpg(process.pid, signal.SIGINT)
                self.assertEqual(process.wait(timeout=10), 254)  # Python maps -SIGINT to shell status
                summary = json.loads((directory/'monitor-summary.json').read_text())
                self.assertEqual(summary['exit_code'], -signal.SIGINT)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGINT)
                    process.wait(timeout=10)

    def test_local_events_100_and_interruption(self):
        events = []
        def solver(objective, x, **kwargs):
            value = objective(x)
            return OptimizeResult(x=np.array(x), fun=value, success=True, status=0, message='ok', nit=0)
        options = dict(seed=1, maxiter=1, max_restarts=99, max_evaluations=1000, restart_sigma=.1)
        with patch('lpf.optimizers.hybrid.minimize', side_effect=solver):
            out = hybrid_minimize(lambda x: [x[0]], [.5], [(0,1)], event_callback=events.append, **options)
        self.assertEqual(len(out.runs), 100)
        restarts = [e for e in events if e['event'] == 'restart_start_generated']
        local_events = [e for e in events if e['event'] != 'restart_start_generated']
        self.assertEqual(len(restarts), 99)
        self.assertEqual([e['run_index'] for e in restarts], list(range(1, 100)))
        for event in restarts:
            self.assertEqual(event['seed'], 1)
            self.assertGreaterEqual(event['wall_s'], 0)
            self.assertGreaterEqual(event['cpu_s'], 0)
        self.assertEqual(len(local_events), 200)
        for i in range(100):
            start, end = local_events[2*i:2*i+2]
            self.assertEqual((start['run_index'], end['run_index']), (i, i))
            self.assertEqual((end['nfev'], end['nit'], end['success']), (1, 0, True))
            self.assertGreaterEqual(end['wall_s'], 0)
            self.assertGreaterEqual(end['cpu_s'], 0)
        with patch('lpf.optimizers.hybrid.minimize', side_effect=solver):
            baseline_many = hybrid_minimize(lambda x: [x[0]], [.5], [(0,1)], **options)
            failed_callback = hybrid_minimize(lambda x: [x[0]], [.5], [(0,1)],
                                              event_callback=Mock(side_effect=OSError('missing')), **options)
        from dataclasses import asdict
        self.assertEqual(asdict(out), asdict(baseline_many))
        self.assertEqual(asdict(out), asdict(failed_callback))
        events.clear()
        budget_options = dict(seed=1, maxiter=2, max_restarts=1, max_evaluations=1, restart_sigma=.1)
        baseline = hybrid_minimize(lambda x: [x[0]], [.5], [(0,1)], **budget_options)
        observed = hybrid_minimize(lambda x: [x[0]], [.5], [(0,1)], event_callback=events.append, **budget_options)
        from dataclasses import asdict
        self.assertEqual(asdict(baseline), asdict(observed))
        self.assertEqual(observed.stop_reason, 'evaluation_budget_exhausted')
        self.assertEqual(events[-1]['message'], 'evaluation_budget_exhausted')
        self.assertEqual(events[-1]['nfev'], 1)
        events.clear()
        with patch('lpf.optimizers.hybrid.minimize', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                hybrid_minimize(lambda x: [1], [.5], [(0,1)], event_callback=events.append, **options)
        self.assertTrue(events[-1]['interrupted'])
        self.assertIsNone(events[-1]['status'])


if __name__ == '__main__':
    unittest.main()
