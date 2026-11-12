"""Timing instrumentation follows Hybrid's private callback, not public APIs."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import numpy as np
from lpf.search.plan import ROOT
from lpf.timing import TimerCollector
from lpf.search import _minimal_worker_timing as timing
from test_issue389_minimal_worker import MinimalWorkerTests


class TimingTests(unittest.TestCase):
    setUp = MinimalWorkerTests.setUp
    setup_model = MinimalWorkerTests.setup_model
    prepare = MinimalWorkerTests.prepare

    def test_retained_start_input_byte_identity(self):
        import hashlib
        starts = ROOT / 'project/diagnostics/issue401_starts_1002.json'
        self.assertEqual(hashlib.sha256(starts.read_bytes()).hexdigest(),
                         '63b671ea269656843df118230b7d920e91515188235809b6dd0efd667ac997ab')

    def test_solver_path_and_plain_equivalence(self):
        _, _, _, _, plain = self.prepare()
        _, _, _, _, timed = self.prepare()
        expected = plain.solve()
        timer = TimerCollector()
        with timing.instrument(timed, timer), \
             patch.object(timed, 'evaluate', side_effect=AssertionError('public evaluate used')), \
             patch.object(timed, 'residuals', side_effect=AssertionError('public residuals used')):
            actual = timed.solve()
        self.assertEqual(actual.nfev, expected.nfev)
        self.assertEqual(actual.stop_reason, expected.stop_reason)
        self.assertEqual(actual.best_fun, expected.best_fun)
        np.testing.assert_array_equal(actual.best_x, expected.best_x)
        rows = timer.snapshot()
        for region in ('solver_callback', 'rf_forward', 'requirements', 'residual'):
            self.assertEqual(rows[region]['count'], actual.nfev)
            self.assertEqual(rows[region]['failed'], 0)
        self.assertEqual(rows['solve_total']['count'], 1)
        self.assertEqual(rows['hybrid_minimize']['count'], 1)
        self.assertEqual(rows['postsolve_validation']['count'], 2)

    def test_deep_regions_follow_rf_path(self):
        _, _, _, _, worker = self.prepare()
        timer = TimerCollector()
        with timing.instrument(worker, timer, deep=True):
            result = worker.solve()
        rows = timer.snapshot()
        for name in ('l3_port_admittance', 'l3_node_admittance', 'l3_matrices', 'l3_power_response',
                     'l3_decode', 'l3_encode', 'l3_y_to_s_solve'):
            self.assertEqual(rows[name]['count'], result.nfev)
            self.assertEqual(rows[name]['failed'], 0)
        self.assertEqual(rows['l3_cascade']['count'], 2 * result.nfev)
        self.assertEqual(rows['l3_cascade']['failed'], 0)

    def test_benchmark_modes_separate_postsolve_forward(self):
        spec = importlib.util.spec_from_file_location('benchmark_minimal_worker', ROOT / 'scripts/benchmark_minimal_worker.py')
        bench = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bench)
        reports = []
        for mode in ('plain', 'timed', 'deep'):
            plan, definition, policy, vector, worker = self.prepare()
            output = io.StringIO()
            argv = ['benchmark', '--config', 'unused', '--starts',
                    str(ROOT / 'project/diagnostics/issue401_starts_1002.json'),
                    '--arm', 'demo', '--seed', '23', '--mode', mode]
            with patch.object(bench, 'source_identity', return_value={'fixture': True}), \
                 patch.object(bench, 'load_preflight', return_value=plan), \
                 patch.object(bench, 'definition_from_data', return_value=definition), \
                 patch.object(bench, 'load_constraint', return_value=policy), \
                 patch.object(bench, 'load_explicit', return_value={23: {'vector': vector, 'vector_sha256': 'fixture'}}), \
                 patch.object(bench, 'MinimalWorker', return_value=worker), \
                 patch('sys.argv', argv), patch('sys.stdout', output):
                bench.main()
            report = json.loads(output.getvalue())
            reports.append(report)
            self.assertEqual(report['mode'], mode)
            self.assertEqual(report['solver']['nfev'], 3)
            self.assertEqual(report['observation_forward_count'], 1)
            if mode == 'plain':
                self.assertEqual(report['timers'], {})
            else:
                self.assertEqual(report['timers']['rf_forward']['count'], 3)
                self.assertEqual('l3_port_admittance' in report['timers'], mode == 'deep')
        self.assertEqual(reports[0]['solver'], reports[1]['solver'])
        self.assertEqual(reports[0]['solver'], reports[2]['solver'])

    def test_failure_propagates_and_counts(self):
        _, _, _, _, worker = self.prepare()
        timer = TimerCollector()
        with patch.object(type(worker.evaluator), 'evaluate', side_effect=ArithmeticError('RF failed')):
            with timing.instrument(worker, timer):
                with self.assertRaisesRegex(ArithmeticError, 'RF failed'):
                    worker.solve()
        rows = timer.snapshot()
        for name in ('rf_forward', 'solver_callback', 'hybrid_minimize', 'solve_total'):
            self.assertEqual(rows[name]['failed'], 1)
        self.assertNotIn('requirements', rows)


if __name__ == '__main__':
    unittest.main()
