"""Development-only minimum-path equivalence and failure checks."""
import copy
import importlib.util
import io
import json
from dataclasses import dataclass, replace
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import test_issue315_fixed_stage as fixtures
from lpf.optimizers.hybrid import hybrid_minimize
from lpf.search._worker_next import MinimalWorker
from lpf.search.storage import vector_sha, canonical, sha
from lpf.search.plan import ROOT


class MinimalWorkerTests(unittest.TestCase):
    setUp = fixtures.FixedStageTests.setUp
    setup_model = fixtures.FixedStageTests.setup_model
    evaluator = fixtures.FixedStageTests.evaluator

    def prepare(self):
        def configure(c):
            c['arms'][0]['steps'][0].update(solver='hybrid', aggregation='sum',
                options=dict(maxiter=3, max_restarts=0, max_evaluations=3, restart_sigma=.1))
        plan, d, p, x = self.setup_model('RF-T008', mutate=configure)
        worker = MinimalWorker(plan, d, p, 'demo', 23, x, vector_sha(x), root=ROOT)
        return plan, d, p, x, worker

    def test_real_rf_saved_equivalence_and_solver(self):
        plan, d, p, x, worker = self.prepare()
        old = self.evaluator(plan, d, p)
        vectors = [x.copy()]
        y = x.copy()
        lo, hi = worker.bounds[0]
        y[0] = (x[0] + hi) / 2
        vectors.append(y)
        for vector in vectors:
            saved = old.evaluate(vector)
            response, assessment = worker.evaluate(vector)
            row = old.rows[-1]
            np.testing.assert_array_equal(response.s.real, row['response']['s_real'])
            np.testing.assert_array_equal(response.s.imag, row['response']['s_imag'])
            for name in ('il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
                np.testing.assert_array_equal(getattr(response, name), row['response'][name])
            self.assertEqual(assessment['worst_il_db'], saved['assessment']['worst_il_db'])
            np.testing.assert_array_equal(assessment['mandatory_g'], saved['assessment']['mandatory_g'])
            expected = np.r_[np.sqrt(assessment['worst_il_db']), np.maximum(0., -np.asarray(assessment['mandatory_g']))]
            np.testing.assert_array_equal(worker.residuals(vector), expected)
        def legacy(v):
            a = old.evaluate(v)['assessment']
            return np.r_[np.sqrt(a['worst_il_db']), np.maximum(0., -np.asarray(a['mandatory_g']))]
        expected = hybrid_minimize(legacy, x, worker.bounds, seed=23, aggregation='sum', **worker.step['options'])
        with patch('builtins.open', side_effect=AssertionError('unexpected I/O')), \
             patch.object(Path, 'open', side_effect=AssertionError('unexpected I/O')):
            actual = worker.solve()
        self.assertEqual(actual.nfev, expected.nfev)
        self.assertEqual(actual.stop_reason, expected.stop_reason)
        self.assertEqual(actual.best_fun, expected.best_fun)
        np.testing.assert_array_equal(actual.best_x, expected.best_x)
        self.assertEqual(actual.nfev, 3)

    def test_bad_inputs_and_failures(self):
        plan, d, p, x, worker = self.prepare()
        with self.assertRaises(ValueError):
            MinimalWorker(replace(plan, sha256='0'*64), d, p, 'demo', 23, x, vector_sha(x), root=ROOT)
        changed = plan.data
        changed['requirements']['mode'] = 'matching_only'
        with self.assertRaises(ValueError):
            MinimalWorker(replace(plan, frozen_json=canonical(changed), sha256=sha(changed)), d, p, 'demo', 23, x, vector_sha(x), root=ROOT)
        wrong = copy.deepcopy(p); wrong['source_ohms']['real'] += 1
        with self.assertRaises(ValueError):
            MinimalWorker(plan, d, wrong, 'demo', 23, x, vector_sha(x), root=ROOT)
        for value in (np.full_like(x, np.nan), np.full_like(x, 1e30)):
            with self.assertRaises(ValueError): worker.evaluate(value)
        with patch.object(type(worker.model.topology), 'matrices', side_effect=ValueError('non-SPD')):
            with self.assertRaisesRegex(ValueError, 'non-SPD'): worker.evaluate(x)
        with patch.object(type(worker.evaluator), 'evaluate', side_effect=ArithmeticError('RF failure')):
            with self.assertRaisesRegex(ArithmeticError, 'RF failure'): worker.evaluate(x)
        with patch.object(worker, 'evaluate', return_value=(None, {'worst_il_db': float('nan'), 'mandatory_g': []})):
            with self.assertRaises(ValueError): worker.residuals(x)


class SourceBoundaryTests(unittest.TestCase):
    def test_identity_once_and_mismatch_stops_before_preflight(self):
        spec = importlib.util.spec_from_file_location('benchmark_minimal_worker', ROOT / 'scripts/benchmark_minimal_worker.py')
        bench = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bench)
        identity = {'head': 'test', 'files': {'src/test.py': 'digest'}, 'dirty_patch_sha256': 'dirty', 'environment': {}}
        with patch.object(bench, 'source_identity', return_value=identity) as source:
            actual, source_sha, script_sha = bench.freeze_source(None, None)
            self.assertEqual(actual, identity)
            self.assertEqual(source_sha, sha(identity))
            self.assertEqual(len(script_sha), 64)
            source.assert_called_once_with(ROOT)
        for source_expected, script_expected in (('wrong', script_sha), (source_sha, 'wrong')):
            argv = ['benchmark', '--config', 'unused', '--starts', 'unused', '--arm', 'demo', '--seed', '23',
                    '--expected-source-sha256', source_expected, '--expected-script-sha256', script_expected]
            with patch.object(bench, 'source_identity', return_value=identity) as source, \
                 patch.object(bench, 'load_preflight') as preflight, patch('sys.argv', argv):
                with self.assertRaisesRegex(ValueError, 'SHA mismatch'):
                    bench.main()
                source.assert_called_once_with(ROOT)
                preflight.assert_not_called()
        with patch.object(bench, 'source_identity', return_value=identity) as source:
            self.assertEqual(bench.freeze_source(source_sha, script_sha), (identity, source_sha, script_sha))
            source.assert_called_once_with(ROOT)

    def test_report_contains_start_identity_without_rf(self):
        spec = importlib.util.spec_from_file_location('benchmark_minimal_worker', ROOT / 'scripts/benchmark_minimal_worker.py')
        bench = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bench)
        identity = {'head': 'start', 'files': {'src/test.py': 'digest'}, 'dirty_patch_sha256': 'dirty', 'environment': {}}
        @dataclass
        class Output:
            best_x: object = None
        worker = SimpleNamespace(step={'name': 'coarse', 'options': {'max_evaluations': 1, 'max_restarts': 0}},
            model=SimpleNamespace(policy_id='fixture', policy_fingerprint='fixture'), solve=lambda: Output())
        plan = SimpleNamespace(data={'config': {'definition': {}, 'rf': {'constraint_id': 'fixture', 'allow_trial': True}},
            'rf_inputs': {}, 'grids': {'demo/coarse': {'sha256': 'grid'}}}, sha256='plan')
        argv = ['benchmark', '--config', 'unused', '--starts', 'unused', '--arm', 'demo', '--seed', '23']
        output = io.StringIO()
        with patch.object(bench, 'source_identity', return_value=identity) as source, \
             patch.object(bench, 'load_preflight', return_value=plan), \
             patch.object(bench, 'definition_from_data'), patch.object(bench, 'load_constraint'), \
             patch.object(bench, 'load_explicit', return_value={23: {'vector': [1.], 'vector_sha256': 'start'}}), \
             patch.object(bench, 'MinimalWorker', return_value=worker), \
             patch('sys.argv', argv), patch('sys.stdout', output):
            bench.main()
        report = json.loads(output.getvalue())
        self.assertEqual(report['source_identity'], identity)
        self.assertEqual(report['source_sha256'], sha(identity))
        self.assertEqual(len(report['benchmark_script_sha256']), 64)
        source.assert_called_once_with(ROOT)


if __name__ == '__main__':
    unittest.main()
