"""Opt-in diagnostics must not alter the scientific path."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_issue458_profile import Profile458Tests
from lpf.search import _development_runner as runner
from lpf.search.plan import ROOT


class TimingTests(unittest.TestCase):
    def setUp(self):
        fixture = Profile458Tests()
        fixture.setUp()
        self.cfg, self.starts = fixture.cfg, fixture.starts

    def test_plain_timed_identity_and_isolation(self):
        self.cfg['seeds'] = [23, 24]
        self.starts['24'] = self.starts['23']
        self.cfg['budget'] = {k: 2*v for k, v in self.cfg['budget'].items()}
        with tempfile.TemporaryDirectory(prefix='issue468-test-') as tmp:
            base = Path(tmp)
            args = dict(root=ROOT, spot_checks={'terminal': [0, 57]}, checkpoint_interval=1,
                        rf_cache_mode='off')
            with patch('lpf.search._development_worker.search_rf_timing', side_effect=AssertionError('unexpected L3')):
                plain = runner.run(self.cfg, self.starts, base/'plain', **args)
                timed = runner.run(self.cfg, self.starts, base/'timed', timing_output=base/'timing.json', **args)
            deep = runner.run(self.cfg, self.starts, base/'deep', timing_output=base/'deep.json', timing_level='deep', **args)
            self.assertEqual(plain, timed)
            self.assertEqual(plain, deep)
            deep_diag = json.loads((base/'deep.json').read_text())
            self.assertEqual(deep_diag['level'], 'deep')
            diag = json.loads((base/'timing.json').read_text())
            self.assertEqual(diag['status'], 'completed')
            self.assertEqual(diag['plan_sha256'], plain['plan_sha256'])
            for i, job in enumerate(diag['jobs'], 1):
                self.assertEqual(job['seed'], 22+i)
                self.assertEqual(job['status'], 'completed')
                a = json.loads((base/f'plain/job-{i:04d}/result.json').read_text())
                b = json.loads((base/f'timed/job-{i:04d}/result.json').read_text())
                self.assertEqual(a, b)
                self.assertEqual(a, json.loads((base/f'deep/job-{i:04d}/result.json').read_text()))
                step = a['steps'][0]
                regions = deep_diag['jobs'][i-1]['regions']
                for name, factor in [('decode', 1), ('port_admittance', 1), ('node_admittance', 1),
                                     ('matrices', 1), ('cascade', 2), ('power_response', 1)]:
                    self.assertEqual(regions[f'demo/coarse/rf/{name}']['count'], factor * step['forward_count'])
                for name in ('matrices/build', 'matrices/build_h_incidence', 'matrices/spd_eigvalsh',
                             'matrices/inductor_solve', 'node/l_expand', 'node/c_stamping',
                             'port/reorder', 'port/schur_solve', 'port/schur_update',
                             'y_to_s_solve', 'response_build', 'power/wave_build',
                             'power/wave_solve', 'power/db_metrics'):
                    row = regions[f'demo/coarse/rf/{name}']
                    self.assertEqual(row['count'], step['forward_count'], name)
                    self.assertEqual(row['failed'], 0, name)
                    self.assertGreater(row['wall_ns'], 0, name)
                self.assertEqual(regions['demo/coarse/evaluator_setup']['count'], 1)
                self.assertEqual(job['regions']['demo/coarse/evaluator_setup']['count'], 1)
                self.assertFalse(any('/rf/' in name for name in job['regions']))
                self.assertFalse(any(name.startswith('terminal/rf/') for name in regions))
                self.assertEqual(len(step['local_run_details']), step['local_runs'])
                self.assertEqual(sum(r['evaluations'] for r in step['local_run_details']), step['forward_count'])
                self.assertEqual(job['regions']['demo/coarse/rf_evaluate']['count'], step['forward_count'])
                self.assertEqual(job['regions']['terminal/rf_evaluate']['count'], 1)
                self.assertEqual(job['regions']['job']['count'], 1)
                self.assertEqual(len(job['steps']['coarse']['local_runs']), step['local_runs'])

    def test_paths_and_failed_write(self):
        with tempfile.TemporaryDirectory(prefix='issue468-path-') as tmp:
            base = Path(tmp)
            out = base/'run'
            args = dict(root=ROOT, spot_checks={'terminal': [0, 57]}, checkpoint_interval=1)
            (base/'exists').write_text('keep')
            for path in (out, out/'inside', base, base/'exists', ROOT/'timing.json'):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    runner.run(self.cfg, self.starts, out, timing_output=path, **args)
            original_open = Path.open
            def fail_timing(path, *args, **kwargs):
                if path == base/'timing.json':
                    raise OSError('injected')
                return original_open(path, *args, **kwargs)
            with patch.object(Path, 'open', fail_timing):
                state = runner.run(self.cfg, self.starts, out, timing_output=base/'timing.json', **args)
            self.assertEqual(state['jobs'][0]['scientific_status'], 'not_converged')
            self.assertEqual((base/'exists').read_text(), 'keep')

    def test_cli_exit_codes_when_timing_write_fails(self):
        spec = importlib.util.spec_from_file_location('issue468_cli', ROOT/'scripts/run_rf_search.py')
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        with tempfile.TemporaryDirectory(prefix='issue468-cli-') as tmp:
            base = Path(tmp)
            (base/'config.json').write_text(json.dumps(self.cfg))
            (base/'starts.json').write_text(json.dumps(self.starts))
            argv = ['develop', '--config', str(base/'config.json'), '--starts', str(base/'starts.json'),
                    '--output', str(base/'run'), '--spot-checks', '{"terminal":[0,57]}',
                    '--timing-output', str(base/'timing.json')]
            original_open = Path.open
            def fail_timing(path, *args, **kwargs):
                if path == base/'timing.json':
                    raise OSError('injected')
                return original_open(path, *args, **kwargs)
            with patch.object(Path, 'open', fail_timing):
                self.assertEqual(cli.main(argv), 4)
                # Fresh output, then a scientific STOP; a diagnostic write failure must not mask it.
                argv[argv.index('--output') + 1] = str(base/'stopped')
                argv += ['--timing-level', 'deep']
                with patch('lpf.search._development_worker.lbfgsb_minimize', side_effect=ValueError('injected')):
                    self.assertEqual(cli.main(argv), 2)
            without_output = argv[:argv.index('--timing-output')] + ['--timing-level', 'deep']
            with self.assertRaises(SystemExit) as invalid:
                cli.main(without_output)
            self.assertEqual(invalid.exception.code, 2)
            with self.assertRaises(SystemExit) as help_exit:
                cli.main(['develop', '--help'])
            self.assertEqual(help_exit.exception.code, 0)

    def test_deep_exception_restores_functions(self):
        from lpf.rf_core import model, coupled_lc
        from lpf.rf_core.coupled_lc import CoupledLCTopology
        original = (model.RFEvaluator.evaluate, model.RFModel.decode, CoupledLCTopology.port_admittance,
                    CoupledLCTopology.node_admittance, CoupledLCTopology.matrices, model._cascade, model.power_response)
        with tempfile.TemporaryDirectory(prefix='issue470-stop-') as tmp:
            base = Path(tmp)
            with patch.object(CoupledLCTopology, 'matrices', side_effect=ValueError('RF injected')):
                injected = CoupledLCTopology.matrices
                with self.assertRaisesRegex(ValueError, 'RF injected'):
                    runner.run(self.cfg, self.starts, base/'run', root=ROOT, spot_checks={'terminal': [0, 57]},
                               timing_output=base/'timing.json', timing_level='deep')
                self.assertIs(CoupledLCTopology.matrices, injected)
            self.assertEqual(original, (model.RFEvaluator.evaluate, model.RFModel.decode, CoupledLCTopology.port_admittance,
                                        CoupledLCTopology.node_admittance, CoupledLCTopology.matrices, model._cascade, model.power_response))
            self.assertIsNone(model._deep_timing)
            self.assertIsNone(coupled_lc._deep_timing)
            diag = json.loads((base/'timing.json').read_text())
            self.assertEqual(diag['status'], 'incomplete')
            self.assertEqual(diag['jobs'][0]['regions']['demo/coarse/rf/matrices']['failed'], 1)

    def test_deep_subregion_failure_and_restoration(self):
        import numpy as np
        from lpf.minimax_profile import load_minimax_profile
        from lpf.rf_core import model, coupled_lc
        from lpf.search._rf_deep_timing import search_rf_timing
        from lpf.search.performance import build_evaluation_grid, compile_profile_grid
        from lpf.search.proposals import definition_from_data
        from lpf.timing import TimerCollector
        fixture = Profile458Tests()
        fixture.setUp()
        profile = load_minimax_profile('RF-T010', allow_trial=True)
        evaluator = profile.build_model(definition_from_data(fixture.data)).evaluator(
            build_evaluation_grid(compile_profile_grid(profile), 2))
        timer = TimerCollector()
        with self.assertRaisesRegex(ValueError, 'injected eig'):
            with search_rf_timing(timer, 'test'):
                with patch.object(np.linalg, 'eigvalsh', side_effect=ValueError('injected eig')):
                    evaluator.evaluate(fixture.x)
        self.assertEqual(timer.snapshot()['test/rf/matrices/spd_eigvalsh']['failed'], 1)
        self.assertEqual(timer.snapshot()['test/rf/matrices']['failed'], 1)
        self.assertIsNone(model._deep_timing)
        self.assertIsNone(coupled_lc._deep_timing)
        before = timer.snapshot()
        evaluator.evaluate(fixture.x)
        self.assertEqual(before, timer.snapshot())

    def test_stop_diagnostic(self):
        with tempfile.TemporaryDirectory(prefix='issue468-stop-') as tmp:
            base = Path(tmp)
            with patch('lpf.search._development_worker.lbfgsb_minimize', side_effect=ValueError('injected')):
                with self.assertRaisesRegex(ValueError, 'injected'):
                    runner.run(self.cfg, self.starts, base/'run', root=ROOT, spot_checks={'terminal': [0, 57]},
                               timing_output=base/'timing.json')
            diag = json.loads((base/'timing.json').read_text())
            self.assertEqual(diag['status'], 'incomplete')
            self.assertEqual(diag['jobs'][0]['status'], 'incomplete')
            self.assertEqual(diag['jobs'][0]['regions']['job']['failed'], 1)


if __name__ == '__main__':
    unittest.main()
