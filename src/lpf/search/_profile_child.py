"""Private py-spy child: report the actual CLI PID and wait status on a pipe.

This process is intentionally not the scientific CLI. py-spy --subprocesses
samples its CLI child; the supervisor receives its status independently.
"""
import os
from pathlib import Path
import subprocess
import sys


def main():
    if sys.argv[1] == '--gate':
        gate_fd, status_fd = map(int, sys.argv[2:4])
        # Never execute scientific work unless the reporter has first sent the
        # PID. If it dies before handoff, EOF closes the gate without a run.
        if os.read(gate_fd, 1) != b'1':
            return 2
        os.close(gate_fd)
        os.set_inheritable(status_fd, False)
        try:
            os.execvpe(sys.argv[4], sys.argv[4:], os.environ)
        except OSError as exc:
            os.write(status_fd, f'error exec {type(exc).__name__}: {exc}\n'.encode())
            return 2
    status_fd, stdout_fd, stderr_fd = map(int, sys.argv[1:4])
    gate_read, gate_write = os.pipe()
    try:
        try:
            child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--gate',
                                      str(gate_read), str(status_fd), *sys.argv[4:]],
                                     stdout=stdout_fd, stderr=stderr_fd, start_new_session=True,
                                     pass_fds=(gate_read, status_fd))
        except OSError as exc:
            os.write(status_fd, f'error {type(exc).__name__}: {exc}\n'.encode())
            return 2
        os.close(gate_read)
        gate_read = None
        os.write(status_fd, f'pid {child.pid}\n'.encode())
        os.write(gate_write, b'1')
    finally:
        if gate_read is not None:
            os.close(gate_read)
        os.close(gate_write)
    code = child.wait()
    os.write(status_fd, f'exit {code}\n'.encode())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
