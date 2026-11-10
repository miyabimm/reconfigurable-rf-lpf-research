"""Non-RF supervision contract for py-spy child-launch profiling."""
import io
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from lpf.search.monitor import supervise


class ProfileChildTests(unittest.TestCase):
    def make_profiler(self, tmp, body=None):
        fake = Path(tmp)/'py-spy'
        fake.write_text('#!' + sys.executable + '\n' + (body or '''
import subprocess, sys
print('profiler message', flush=True)
subprocess.run(sys.argv[sys.argv.index('--')+1:], close_fds=False)
sys.exit(0)  # Deliberately discard the scientific exit code, like py-spy.
'''))
        fake.chmod(0o755)
        return str(fake)

    def test_scientific_exits_and_logs_are_separate(self):
        with tempfile.TemporaryDirectory(prefix='issue381-exits-') as tmp:
            fake = self.make_profiler(tmp)
            for code in (0, 2, 3, 4):
                logs = Path(tmp)/str(code)
                marker = Path(tmp)/f'called-{code}'
                work = (f"from pathlib import Path; import sys; Path({str(marker)!r}).write_text('once'); "
                        f"print('scientific stdout'); print('scientific stderr', file=sys.stderr); sys.exit({code})")
                with patch('lpf.search.monitor.shutil.which', return_value=fake):
                    self.assertEqual(supervise([sys.executable, '-c', work], logs, None,
                                               profile=True, root=ROOT, interval=.01), code)
                summary = json.loads((logs/'monitor-summary.json').read_text())
                self.assertEqual(summary['exit_code'], code)
                self.assertEqual(summary['profile']['exit_code'], 0)
                self.assertFalse(summary['profile']['available'])
                self.assertEqual((logs/'stdout.txt').read_text(), 'scientific stdout\n')
                self.assertEqual((logs/'stderr.txt').read_text(), 'scientific stderr\n')
                self.assertIn('profiler message', (logs/'profile-stderr.txt').read_text())
                self.assertEqual(marker.read_text(), 'once')

    def test_gate_does_not_run_science_if_reporter_dies_before_handoff(self):
        with tempfile.TemporaryDirectory(prefix='issue381-gate-') as tmp:
            gate_read, gate_write = os.pipe()
            status_read, status_write = os.pipe()
            marker = Path(tmp)/'must-not-run'
            work = f"from pathlib import Path; Path({str(marker)!r}).touch()"
            try:
                child = subprocess.Popen([sys.executable, str(ROOT/'src/lpf/search/_profile_child.py'),
                    '--gate', str(gate_read), str(status_write), sys.executable, '-c', work],
                    pass_fds=(gate_read, status_write))
                os.close(gate_read)
                gate_read = None
                os.close(gate_write)  # Reporter died before giving the go-ahead.
                gate_write = None
                self.assertEqual(child.wait(timeout=10), 2)
                self.assertFalse(marker.exists())
            finally:
                for fd in (gate_read, gate_write, status_read, status_write):
                    if fd is not None:
                        os.close(fd)

    def test_exec_failure_is_unknown_not_scientific_exit(self):
        with tempfile.TemporaryDirectory(prefix='issue381-exec-') as tmp:
            fake = self.make_profiler(tmp)
            with patch('lpf.search.monitor.shutil.which', return_value=fake):
                with self.assertRaisesRegex(RuntimeError, 'scientific CLI exit unknown: exec'):
                    supervise([str(Path(tmp)/'nonexistent')], Path(tmp)/'logs', None,
                              profile=True, root=ROOT, interval=.01)

    def test_profiler_failure_after_cli_exit_is_separate(self):
        with tempfile.TemporaryDirectory(prefix='issue381-spy-fail-') as tmp:
            fake = self.make_profiler(tmp, '''
import subprocess, sys
subprocess.run(sys.argv[sys.argv.index('--')+1:], close_fds=False)
sys.exit(17)
''')
            logs = Path(tmp)/'logs'
            with patch('lpf.search.monitor.shutil.which', return_value=fake):
                self.assertEqual(supervise([sys.executable, '-c', 'raise SystemExit(4)'], logs, None,
                                           profile=True, root=ROOT, interval=.01), 4)
            summary = json.loads((logs/'monitor-summary.json').read_text())
            self.assertEqual(summary['exit_code'], 4)
            self.assertEqual(summary['profile']['exit_code'], 17)
            self.assertFalse(summary['profile']['available'])

    def test_save_failure_after_known_exit_and_no_retry(self):
        with tempfile.TemporaryDirectory(prefix='issue381-save-') as tmp:
            fake = self.make_profiler(tmp)
            logs, marker = Path(tmp)/'logs', Path(tmp)/'calls'
            cmd = [sys.executable, '-c', f"from pathlib import Path; Path({str(marker)!r}).open('a').write('x'); raise SystemExit(4)"]
            original = Path.write_text
            def write(path, *args, **kwargs):
                if path.name == 'monitor-summary.json':
                    raise OSError('summary failure')
                return original(path, *args, **kwargs)
            error = io.StringIO()
            with patch('lpf.search.monitor.shutil.which', return_value=fake), \
                 patch.object(Path, 'write_text', write), redirect_stderr(error):
                self.assertEqual(supervise(cmd, logs, None, profile=True, root=ROOT, interval=.01), 4)
            self.assertEqual(marker.read_text(), 'x')
            self.assertIn('monitoring incomplete', error.getvalue())

    def test_reporter_dies_waits_for_scientific_child_and_exit_unknown(self):
        with tempfile.TemporaryDirectory(prefix='issue381-unknown-') as tmp:
            ready, done = Path(tmp)/'ready', Path(tmp)/'done'
            body = f'''
import os, signal, subprocess, sys, time
p = subprocess.Popen(sys.argv[sys.argv.index('--')+1:], close_fds=False)
while not os.path.exists({str(ready)!r}): time.sleep(.01)
os.kill(p.pid, signal.SIGKILL)
p.wait()
'''
            fake = self.make_profiler(tmp, body)
            work = f"from pathlib import Path; import time; Path({str(ready)!r}).touch(); time.sleep(.5); Path({str(done)!r}).touch()"
            with patch('lpf.search.monitor.shutil.which', return_value=fake):
                with self.assertRaisesRegex(RuntimeError, 'scientific CLI exit unknown'):
                    supervise([sys.executable, '-c', work], Path(tmp)/'logs', None,
                              profile=True, root=ROOT, interval=.01)
            self.assertTrue(done.exists(), 'must not abandon the still-running scientific child')

    def test_sigint_forwarded_to_cli_group(self):
        with tempfile.TemporaryDirectory(prefix='issue381-int-') as tmp:
            self.make_profiler(tmp)
            logs, ready = Path(tmp)/'logs', Path(tmp)/'ready'
            work = f"from pathlib import Path; import time; Path({str(ready)!r}).touch(); time.sleep(30)"
            code = ("import sys; sys.path.insert(0,sys.argv[1]); from lpf.search.monitor import supervise; "
                    f"sys.exit(supervise([sys.executable,'-c',{work!r}],sys.argv[2],None,profile=True,root=sys.argv[3],interval=.02))")
            env = dict(os.environ, PATH=tmp+os.pathsep+os.environ['PATH'])
            process = subprocess.Popen([sys.executable, '-c', code, str(ROOT/'src'), str(logs), str(ROOT)],
                                       env=env, start_new_session=True)
            try:
                deadline = time.monotonic()+10
                while not ready.exists():
                    if process.poll() is not None or time.monotonic() > deadline:
                        self.fail('CLI did not start')
                    time.sleep(.01)
                os.killpg(process.pid, signal.SIGINT)
                self.assertEqual(process.wait(timeout=10), 254)
                summary = json.loads((logs/'monitor-summary.json').read_text())
                self.assertEqual(summary['exit_code'], -signal.SIGINT)
                self.assertEqual(summary['profile']['exit_code'], 0)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGINT)
                    process.wait(timeout=10)


@unittest.skipUnless(os.environ.get('LPF_TEST_REAL_PYSPY') == '1' and shutil.which('py-spy'),
                     'explicit real py-spy check only')
class RealProfileTests(unittest.TestCase):
    def test_real_profiler_preserves_cli_exits_and_output(self):
        with tempfile.TemporaryDirectory(prefix='issue381-real-') as tmp:
            for code in (0, 2, 3, 4):
                logs = Path(tmp)/str(code)
                work = ("import os,sys,time; print('cli pid',os.getpid(),flush=True); "
                        "print('cli stderr',file=sys.stderr,flush=True); "
                        f"time.sleep(.4); sys.exit({code})")
                self.assertEqual(supervise([sys.executable, '-c', work], logs, None,
                                           profile=True, root=ROOT, interval=.02), code)
                summary = json.loads((logs/'monitor-summary.json').read_text())
                self.assertEqual(summary['exit_code'], code)
                self.assertEqual(summary['profile']['exit_code'], 0)
                self.assertEqual((logs/'stdout.txt').read_text(), f"cli pid {summary['child_pid']}\n")
                self.assertEqual((logs/'stderr.txt').read_text(), 'cli stderr\n')
                self.assertIn('py-spy>', (logs/'profile-stderr.txt').read_text())

    def test_real_profiler_sigint(self):
        with tempfile.TemporaryDirectory(prefix='issue381-real-int-') as tmp:
            logs, ready = Path(tmp)/'logs', Path(tmp)/'ready'
            work = f"from pathlib import Path; import time; Path({str(ready)!r}).touch(); time.sleep(30)"
            code = ("import sys; sys.path.insert(0,sys.argv[1]); from lpf.search.monitor import supervise; "
                    f"sys.exit(supervise([sys.executable,'-c',{work!r}],sys.argv[2],None,profile=True,root=sys.argv[3],interval=.02))")
            process = subprocess.Popen([sys.executable, '-c', code, str(ROOT/'src'), str(logs), str(ROOT)],
                                       start_new_session=True)
            try:
                deadline = time.monotonic()+10
                while not ready.exists():
                    if process.poll() is not None or time.monotonic() > deadline:
                        self.fail('real profiled CLI did not start')
                    time.sleep(.01)
                os.killpg(process.pid, signal.SIGINT)
                self.assertEqual(process.wait(timeout=10), 254)
                summary = json.loads((logs/'monitor-summary.json').read_text())
                self.assertEqual(summary['exit_code'], -signal.SIGINT)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGINT)
                    process.wait(timeout=10)


if __name__ == '__main__':
    unittest.main()
