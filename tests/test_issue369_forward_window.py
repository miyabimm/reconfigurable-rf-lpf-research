"""Issue 369 reservation arithmetic; no RF calls or persistent records."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.search._forward_window import ForwardJournal, reserve_forward_window
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


class ForwardJournalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'raw.json'
        self.observations = []
        self.checks = []
        self.journal = ForwardJournal(self.path, identity={'job_sha256': 'a' * 64},
            validate_inputs=lambda: self.checks.append('checked'),
            snapshot=lambda: {'observations': list(self.observations)},
            budget=lambda: dict(samples_per_forward=70,
                step_remaining=203 * 70 - self.journal.requested,
                job_remaining=203 * 70 - self.journal.requested,
                trial_remaining=203 * 70 - self.journal.requested,
                job_reserved=0, trial_reserved=0))

    def record(self):
        return json.loads(self.path.read_bytes())

    def forward(self):
        self.journal.begin_forward()
        self.observations.append(len(self.observations))
        self.journal.complete_forward()

    def test_99_100_101_and_short_tail(self):
        self.journal.start()
        self.assertEqual(self.record()['uncertain_upper']['requested'], 7000)
        for _ in range(99):
            self.forward()
        self.assertEqual((self.journal.write_calls, len(self.checks)), (1, 1))
        self.assertEqual(self.record()['confirmed']['forwards'], 0)
        self.forward()
        saved = self.record()
        self.assertEqual((saved['confirmed']['forwards'], saved['uncertain_upper']['forwards']), (100, 200))
        self.assertEqual(len(saved['payload']['observations']), 100)
        self.assertEqual((self.journal.write_calls, len(self.checks)), (2, 2))
        self.forward()
        self.assertEqual(self.journal.write_calls, 2)
        for _ in range(99):
            self.forward()
        self.assertEqual(self.record()['window']['end_forward'], 203)
        self.assertEqual(self.record()['window']['reserved_samples'], 210)
        for _ in range(3):
            self.forward()
        self.assertIsNone(self.record()['window'])
        self.assertEqual(self.record()['confirmed']['requested'], 203 * 70)
        with self.assertRaisesRegex(RuntimeError, 'no persisted'):
            self.journal.begin_forward()

    def test_crash_and_exception_preserve_entire_durable_window(self):
        self.journal.start()
        saved = self.path.read_bytes()
        for _ in range(3):
            self.forward()
        self.journal.begin_forward()
        # A hard crash leaves the prior bytes and their full reservation intact.
        self.assertEqual(self.path.read_bytes(), saved)
        self.journal.abort('fixture exception')
        self.assertEqual(self.record()['termination']['status'], 'unknown')
        self.assertEqual(self.record()['confirmed']['requested'], 0)
        self.assertEqual(self.record()['uncertain_upper']['requested'], 7000)
        self.assertEqual(self.record()['payload'], json.loads(saved)['payload'])
        self.assertEqual(self.record()['payload']['observations'], [])
        with self.assertRaisesRegex(RuntimeError, 'no retry'):
            self.journal.boundary(reserve=False)
        other = ForwardJournal(self.path, identity={}, validate_inputs=lambda: None,
                               snapshot=lambda: {}, budget=lambda: {})
        with self.assertRaises(FileExistsError):
            other.start()

    def test_step_boundary_confirms_and_replaces_window(self):
        self.journal.start()
        for _ in range(7):
            self.forward()
        self.journal.boundary(reserve=True)
        self.assertEqual(self.record()['confirmed']['forwards'], 7)
        self.assertEqual(self.record()['window']['first_forward'], 7)
        self.forward()
        self.journal.boundary(reserve=False)
        self.assertEqual(self.record()['confirmed']['forwards'], 8)
        self.assertIsNone(self.record()['window'])

    def test_input_change_and_storage_error_stop_without_releasing(self):
        for failure in ('input', 'save'):
            with self.subTest(failure=failure):
                self.setUp()
                self.journal.start()
                before = self.path.read_bytes()
                self.forward()
                if failure == 'input':
                    self.journal.validate_inputs = lambda: (_ for _ in ()).throw(ValueError('changed'))
                    with self.assertRaisesRegex(ValueError, 'changed'):
                        self.journal.boundary(reserve=False)
                else:
                    with patch('lpf.search._forward_window.atomic_verified', side_effect=OSError('save failed')):
                        with self.assertRaisesRegex(OSError, 'save failed'):
                            self.journal.boundary(reserve=False)
                self.assertEqual(self.path.read_bytes(), before)
                with self.assertRaisesRegex(RuntimeError, 'no retry'):
                    self.journal.begin_forward()


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
