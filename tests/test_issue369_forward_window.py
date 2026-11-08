"""Issue 369 reservation arithmetic; no RF calls or persistent records."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lpf.search._forward_window import reserve_forward_window
from lpf.search.storage import atomic_verified, canonical


class ForwardWindowTests(unittest.TestCase):
    def reserve(self, **changes):
        args = dict(first_forward=0, samples_per_forward=70, step_remaining=8000,
                    job_remaining=12000, trial_remaining=15000,
                    job_reserved=3000, trial_reserved=6000)
        args.update(changes)
        return reserve_forward_window(**args)

    def test_100_then_short_tail(self):
        first = self.reserve()
        self.assertEqual((first.first_forward, first.end_forward, first.reserved_samples),
                         (0, 100, 7000))
        tail = self.reserve(first_forward=100, step_remaining=1000,
                            job_remaining=5000, trial_remaining=8000)
        self.assertEqual((tail.first_forward, tail.end_forward, tail.reserved_samples),
                         (100, 114, 980))
        self.assertIsNone(self.reserve(first_forward=114, step_remaining=20))

    def test_other_reservations_bound_window(self):
        self.assertEqual(self.reserve(job_remaining=3071).forward_count, 1)
        self.assertEqual(self.reserve(trial_remaining=6070).forward_count, 1)
        self.assertIsNone(self.reserve(job_remaining=3069))
        with self.assertRaises(ValueError):
            self.reserve(job_remaining=2999)
        with self.assertRaises(ValueError):
            self.reserve(trial_remaining=5999)

    def test_invalid_counts_fail_closed(self):
        for change in (dict(first_forward=-1), dict(samples_per_forward=0),
                       dict(samples_per_forward=True), dict(step_remaining=1.5),
                       dict(job_reserved=-1)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.reserve(**change)


class VerifiedStorageTests(unittest.TestCase):
    def test_exact_readback_and_io_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'raw.json'
            value = {'window': [0, 100], 'requested_lower': 0, 'requested_upper': 7000}
            record = atomic_verified(path, value)
            data = (canonical(value) + '\n').encode()
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(record, dict(sha256=hashlib.sha256(data).hexdigest(),
                write_calls=1, written_bytes=len(data), read_calls=1, read_bytes=len(data)))

    def test_corrupt_readback_and_save_failure_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'raw.json'
            with patch.object(Path, 'read_bytes', return_value=b'wrong'):
                with self.assertRaisesRegex(ValueError, 'readback mismatch'):
                    atomic_verified(path, {'unknown': True})
            with patch('lpf.search.storage.os.replace', side_effect=OSError('disk error')):
                with self.assertRaisesRegex(OSError, 'disk error'):
                    atomic_verified(path, {'unknown': False})
            self.assertEqual(path.read_bytes(), b'{"unknown":true}\n')
