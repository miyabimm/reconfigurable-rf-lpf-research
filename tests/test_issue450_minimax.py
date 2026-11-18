"""Issue 450: bounded deterministic tests; no search or scientific EXP."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from lpf.constraint_versions import constraint_fingerprint, load_constraint
from lpf.minimax_profile import load_minimax_profile, signed_margins
from lpf.rf_core import EvaluationGrid
from lpf.rf_core.model import RFResponse
from lpf.rf_core.independent import validate_response
from lpf.rf_core._grid import validated_band_segments
from test_issue307_constraints import make

def grid(profile):
    segments = validated_band_segments(profile.records)
    return EvaluationGrid([v*1e6 for _, _, lo, hi in segments for v in (lo, hi)],
                          [s for s, _, _, _ in segments for _ in range(2)],
                          [i for i in range(28) for _ in range(2)])


def response(profile, g, offset=-.2):
    il = np.array([(0.8 + offset if profile.records[i]['type'] == 'pass' else 30 - offset)
                   for i in g.segment])
    s = np.zeros((len(il), 2, 2), complex)
    s[:, 1, 0] = 10**(-il/20)
    return RFResponse(g, 'RF-T009', profile.fingerprint, s, il, il, il, il)


def effective_fixture(cfg):
    # Keep #447's exact deterministic grids and solver inputs for numerical A/B.
    return dict(schema_version=1, rf=cfg['rf'], definition=cfg['definition'], seeds=cfg['seeds'],
                terminal_points=cfg['validation']['terminal_points'],
                budget=dict(rf_samples=10000, rf_forwards=100, independent_mna_samples=100),
                arms=[dict(name=arm['name'], steps=[{k: v for k, v in step.items() if k != 'max_requested_samples'}
                                                   for step in arm['steps']]) for arm in cfg['arms']])


def compile_fixture(cfg, x, *, checkpoint_interval=1000):
    from lpf.search.development_plan import freeze_run
    from lpf.search.storage import plain, vector_sha
    return freeze_run(effective_fixture(cfg), {'23': {'demo': dict(vector=plain(x), vector_sha256=vector_sha(x))}},
                      root=ROOT, spot_checks={'terminal': [0]}, search_bounds=None,
                      checkpoint_interval=checkpoint_interval)


def fixture_worker(compiled, path):
    from lpf.search._development_worker import DevelopmentWorker
    from lpf.search.source import source_identity
    return DevelopmentWorker(compiled, 0, source_identity(ROOT), root=ROOT, checkpoint=path)


class MinimaxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = load_minimax_profile('RF-T009', allow_trial=True)

    def test_identity_inputs_and_legacy(self):
        with self.assertRaises(ValueError): load_minimax_profile('RF-T009')
        with self.assertRaises(ValueError): load_constraint('RF-T009', allow_trial=True)
        old = load_constraint('RF-F003')
        new = self.p.profile
        self.assertEqual(new['source_ohms'], old['source_ohms'])
        self.assertEqual(new['load_ohms'], {k: old['load_ohms'][k] for k in ('real', 'imag')})
        for name in ('input', 'output'):
            a, b = new['external_s2p'][name], old['external_port_parasitics'][name+'_parasitic']
            self.assertEqual(a['sha256'], b['sha256'])
            self.assertEqual(a['path'], b['path'].replace('data/', 'rf/'))
        self.assertEqual(self.p.base_sha256, 'e12c42b11d12db7f20983c48cfa441ea96e362e533450d5862aa8a271c82af86')
        self.assertEqual(self.p.fingerprint, 'd1ebefaf4cb6735898467b9c2affcc57b9590d4a6c9f53a0dd84d1f1f2f8b18d')
        self.assertEqual(new['kind'], 'rf_performance_profile')
        self.assertNotIn('objective', new)
        self.assertEqual(len(new['limits_db']), 7)
        for limits in new['limits_db'].values():
            self.assertEqual(limits, dict(ul_il_max=0.8, dl_il_max=0.8, h2_atten_min=30, h3_atten_min=30))
        for cid in ('RF-T005', 'RF-T006', 'RF-T007', 'RF-T008'):
            self.assertEqual(load_constraint(cid, allow_trial=True)['active_constraint_id'], cid)

    def test_every_band_region_independent_and_shared_setting(self):
        p = self.p
        g = grid(p)
        r = response(p, g)
        _, baseline = signed_margins(p, g, r)
        keys = {'UL':'ul_il_max', 'DL':'dl_il_max', 'H2':'h2_atten_min', 'H3':'h3_atten_min'}
        with tempfile.TemporaryDirectory(prefix='issue450-limits-') as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT/'rf', root/'rf')
            path = root/'rf/constraints/trial/RF-T009.json'
            registry_path = root/'rf/constraints/registry.json'
            registry = json.loads(registry_path.read_text())
            entry = registry['minimax_profiles']['RF-T009']
            for i, row in enumerate(p.records):
                data = p.profile
                band = row['note'] or row['case']
                data['limits_db'][band][keys[row['region']]] += 1
                path.write_text(json.dumps(data))
                entry['effective_constraint_sha256'] = constraint_fingerprint({
                    'profile': data, 'base_constraint_sha256': p.base_sha256, 'bands_sha256': p.bands_sha256})
                registry_path.write_text(json.dumps(registry))
                changed = load_minimax_profile('RF-T009', allow_trial=True, root=root)
                _, margins = signed_margins(changed, g, replace(r, policy_fingerprint=changed.fingerprint))
                delta = margins - baseline
                expected = np.where(g.segment == i, -1 if row['type'] == 'pass' else 1, 0)
                np.testing.assert_allclose(delta, expected, atol=1e-12)
        self.assertEqual(set(g.setting[np.isin(g.segment, [12, 13, 14, 15, 16, 17, 18, 19])]), {3})

    def test_score_sign_boundary_max_and_invalid_grids(self):
        g = grid(self.p)
        for v in (-.5, 0., 1.):
            j, margins = signed_margins(self.p, g, response(self.p, g, v))
            self.assertAlmostEqual(j, v)
            np.testing.assert_allclose(margins, v, atol=1e-14)
        r = response(self.p, g)
        il, s = r.il_db.copy(), r.s.copy()
        il[17] += 2
        s[17, 1, 0] = 10**(-il[17]/20)
        self.assertAlmostEqual(signed_margins(self.p, g, replace(r, il_db=il, s=s))[0], 1.8)
        with self.assertRaises(ValueError): signed_margins(self.p, g, replace(r, il_db=il))
        with self.assertRaises(ValueError): signed_margins(self.p, g, replace(r, policy_id='RF-F003'))
        invalid_s = r.s.copy()
        invalid_s[0, 1, 0] = 2
        with self.assertRaises(ValueError): signed_margins(self.p, g, replace(r, s=invalid_s))
        # Exact zero transmission is a valid +inf dB attenuation, never floored.
        il, s = r.il_db.copy(), r.s.copy()
        il[4], s[4, 1, 0] = np.inf, 0
        self.assertAlmostEqual(signed_margins(self.p, g, replace(r, il_db=il, s=s))[0], -.2)
        il[0], s[0, 1, 0] = np.inf, 0
        self.assertEqual(signed_margins(self.p, g, replace(r, il_db=il, s=s))[0], np.inf)
        for f, st, seg in [(g.frequency_hz[:-1], g.setting[:-1], g.segment[:-1]),
                           (g.frequency_hz+1, g.setting, g.segment),
                           (g.frequency_hz, (g.setting+1)%6, g.segment)]:
            wrong = EvaluationGrid(f, st, seg)
            with self.assertRaises(ValueError): signed_margins(self.p, wrong, r)
            with self.assertRaises(ValueError): signed_margins(self.p, wrong, response(self.p, wrong))

    def test_profile_requirements_grid_without_optimizer_objective(self):
        from lpf.search.performance import compile_profile_grid, build_evaluation_grid, evaluate_requirements
        req = compile_profile_grid(self.p)
        self.assertEqual((req.policy_id, req.policy_fingerprint), ('RF-T009', self.p.fingerprint))
        self.assertEqual((len(req.intervals), len(req.limits)), (28, 0))
        g = build_evaluation_grid(req, 2)
        with self.assertRaisesRegex(ValueError, 'Grid-only'):
            evaluate_requirements(response(self.p, g), req, requested_grid=g)

    def test_profile_intervals_do_not_depend_on_base_performance(self):
        from unittest.mock import patch
        from lpf.search.performance import compile_profile_grid, compile_requirements, build_evaluation_grid
        base = compile_requirements(json.loads(self.p.base_json), self.p.records, 'full_lpf')
        # Physical base may carry unrelated legacy performance declarations. They
        # are not an input to RF-T009 interval or performance compilation.
        without_performance = replace(self.p, base_json='{}')
        with patch('lpf.search.performance.compile_requirements', side_effect=AssertionError('legacy performance')):
            req = compile_profile_grid(without_performance)
        self.assertEqual(req, compile_profile_grid(self.p))
        self.assertEqual(req.intervals, base.intervals)
        self.assertEqual(req.s2p_span_hz, base.s2p_span_hz)
        self.assertEqual(len(build_evaluation_grid(req, 2).frequency_hz), 56)

    def test_profile_worker_all_solvers_and_one_terminal(self):
        from dataclasses import asdict
        import yaml
        from lpf.search.storage import plain, vector_sha
        policy, definition, _, _, x = make('RF-F003')
        for solver in ('slsqp', 'slp', 'hybrid'):
            with self.subTest(solver=solver), tempfile.TemporaryDirectory(prefix='issue446-profile-') as tmp:
                cfg = yaml.safe_load((ROOT/'project/fixtures/issue313_preflight.yaml').read_text())
                cfg.pop('selection')
                cfg.update(rf=dict(constraint_id='RF-T009', allow_trial=True),
                           definition=plain(asdict(definition)), anytime_samples=[])
                step = cfg['arms'][0]['steps'][0]
                step.update(solver=solver, aggregation='signed_max' if solver == 'slp' else 'sum',
                            objective='signed_margin_db', options=(dict(max_search_forwards=2)
                            if solver == 'hybrid' else dict(max_iterations=1, max_evaluations=2)))
                compiled = compile_fixture(cfg, x, checkpoint_interval=1)
                plan = compiled[0]
                worker = fixture_worker(compiled, Path(tmp)/'checkpoints')
                from unittest.mock import patch
                from lpf.rf_core.independent import evaluate_independent_response
                with patch('lpf.rf_core.independent.evaluate_independent_response',
                           wraps=evaluate_independent_response) as independent:
                    result = worker.run()
                self.assertEqual(independent.call_count, 1)  # specified Terminal spot only
                record = result['steps'][0]
                out = record['solver_result']
                self.assertEqual(set(out), {'x', 'objective', 'converged', 'stop_reason', 'evaluations'})
                self.assertLessEqual(record['forward_count'], 2)
                self.assertFalse(out['converged'])
                g = plan.requested_grid('demo/coarse')
                response_at_result = worker.model.evaluator(g).evaluate(out['x'])
                _, residual = signed_margins(self.p, g, response_at_result)
                expected = float(np.max(residual) if solver == 'slp' else np.sum(residual**2))
                self.assertAlmostEqual(out['objective'], expected, places=10)
                self.assertNotIn('response', record)
                self.assertNotIn('selection', result)
                self.assertEqual(len(result['terminal']['candidates']), 1)
                terminal = result['terminal']['candidates'][0]
                self.assertEqual(terminal['vector_sha256'], vector_sha(out['x']))
                self.assertEqual(terminal['performance_feasible'], terminal['terminal_signed_max_margin_db'] <= 0)
                self.assertEqual(terminal['independent']['status'], 'pass')
                self.assertEqual(terminal['independent']['sample_indices'], [0])
                self.assertEqual(terminal['independent']['power_balance'], 'pass_at_samples')
                self.assertFalse(terminal['independent']['whole_band_checked'])
                self.assertEqual(terminal['external_passivity'], 'checked_on_terminal_grid')
                self.assertEqual(terminal['power_balance'], 'checked_on_terminal_grid')
                self.assertEqual(terminal['independent_power_balance'], 'checked_at_independent_mna_spots')
                self.assertNotIn('terminal_independent_full', terminal)
                self.assertNotIn('terminal_independent_full_samples', result['costs'])
                self.assertEqual(result['costs']['independent_mna_samples_by_stage'], {'terminal': 1})
                for key in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
                    self.assertEqual(len(terminal['response'][key]), 112)
                self.assertEqual(set(terminal['response']['grid']['setting']), set(range(6)))
                self.assertEqual(set(terminal['response']['grid']['segment']), set(range(28)))
                self.assertGreater(terminal['physical']['min_L_eigenvalue_H'], 0)
                self.assertEqual(terminal['independent']['spots'][0]['index'], 0)
                self.assertGreaterEqual(len(list((Path(tmp)/'checkpoints').glob('*.json'))), 1)

    def test_profile_worker_separates_search_and_terminal_checks(self):
        from dataclasses import asdict
        from unittest.mock import patch
        import yaml
        from lpf.search.component_constraints import _validate_values_with_bounds, _check_vector_box
        from lpf.rf_core.model import RFEvaluator
        from lpf.search.storage import plain, vector_sha
        policy, definition, _, _, x = make('RF-F003')
        cfg = yaml.safe_load((ROOT/'project/fixtures/issue313_preflight.yaml').read_text())
        cfg.pop('selection')
        cfg.update(rf=dict(constraint_id='RF-T009', allow_trial=True),
                   definition=plain(asdict(definition)), anytime_samples=[])
        cfg['arms'][0]['steps'][0].update(solver='hybrid', aggregation='sum',
            objective='signed_margin_db', options=dict(max_search_forwards=2))
        compiled = compile_fixture(cfg, x)
        with tempfile.TemporaryDirectory(prefix='issue447-worker-') as tmp:
            evaluate = RFEvaluator.evaluate
            events = []
            def forward(evaluator, vector, *, check_power=False):
                events.append('terminal' if check_power else 'search')
                return evaluate(evaluator, vector, check_power=check_power)
            def audit(*args, **kwargs):
                events.append('physical')
                return _validate_values_with_bounds(*args, **kwargs)
            with patch('lpf.search.performance.evaluate_requirements', side_effect=AssertionError('legacy')), \
                 patch('lpf.search.performance.summarize_mandatory', side_effect=AssertionError('legacy')), \
                 patch('lpf.search._development_worker._validate_values_with_bounds', side_effect=audit), \
                 patch('lpf.search._development_worker._check_vector_box', wraps=_check_vector_box) as box, \
                 patch.object(RFEvaluator, 'evaluate', forward):
                worker = fixture_worker(compiled, Path(tmp)/'checkpoints')
                result = worker.run()
            self.assertEqual(events, ['physical', 'search', 'search', 'physical', 'physical', 'terminal'])
            self.assertEqual(box.call_count, 3)
            self.assertNotIn('assessment', result['terminal']['candidates'][0])
            # Even a rehashed Plan cannot silently change the grid or reservation.
            from lpf.search.plan import Plan
            from lpf.search.storage import canonical, sha
            frozen = compiled[0].data
            frozen['grids']['terminal']['frequency_hz'][0] += 1
            with self.assertRaisesRegex(ValueError, 'Frozen grid SHA mismatch'):
                fixture_worker((Plan(canonical(frozen), sha(frozen)), *compiled[1:]), Path(tmp)/'bad-plan')
            self.assertFalse((Path(tmp)/'bad-plan').exists())

    def test_profile_worker_hard_forward_cap_and_no_retry(self):
        from dataclasses import asdict
        from unittest.mock import patch
        import yaml
        from lpf.search.storage import plain, vector_sha
        policy, definition, _, _, x = make('RF-F003')
        for solver in ('slsqp', 'slp', 'hybrid'):
            with self.subTest(solver=solver), tempfile.TemporaryDirectory(prefix='issue446-cap-') as tmp:
                cfg = yaml.safe_load((ROOT/'project/fixtures/issue313_preflight.yaml').read_text())
                cfg.pop('selection')
                cfg.update(rf=dict(constraint_id='RF-T009', allow_trial=True),
                           definition=plain(asdict(definition)), anytime_samples=[])
                cfg['arms'][0]['steps'][0].update(solver=solver,
                    aggregation='signed_max' if solver == 'slp' else 'sum', objective='signed_margin_db',
                    options=dict(max_search_forwards=2) if solver == 'hybrid' else
                            dict(max_iterations=1, max_evaluations=2))
                worker = fixture_worker(compile_fixture(cfg, x, checkpoint_interval=1), Path(tmp)/'checkpoints')
                def overrunning(callback, start, bounds, **kw):
                    for _ in range(3):
                        residual = callback(x)
                        value = float(np.max(residual) if solver == 'slp' else residual @ residual)
                        if solver == 'hybrid':
                            kw['objective_callback'](x, value)
                        else:
                            kw['objective_callback'](x, value)
                    self.fail('hard cap was not enforced')
                target = f'lpf.search._development_worker.{solver}_minimize'
                with patch(target, side_effect=overrunning):
                    with self.assertRaisesRegex(ValueError, 'Search RF forward budget exhausted'):
                        worker.run()
                self.assertEqual(worker.forward_count, 2)
                with self.assertRaisesRegex(RuntimeError, 'retry'):
                    worker.run()

    def test_real_forward_equals_formal_external_cascade(self):
        _, definition, old, _, x = make('RF-F003')
        new = self.p.build_model(definition)
        g = grid(self.p)
        a = old.evaluator(g).evaluate(x)
        b = new.evaluator(g).evaluate(x, check_power=True)
        np.testing.assert_allclose(a.s, b.s, rtol=0, atol=0)
        np.testing.assert_allclose(a.il_db, b.il_db, rtol=0, atol=0)
        j, margins = signed_margins(self.p, g, b)
        self.assertEqual(j, np.max(margins))
        audit = validate_response(new, x, b)
        self.assertEqual(audit['samples_checked'], 56)
        self.assertTrue(audit['independent_mna_checked'])
        self.assertFalse(audit['rf_compliance_certified'])

    def test_forward_power_check_rejects_active_two_port(self):
        from lpf.rf_core.model import power_response
        active = np.array([[[0, 0], [1.1, 0]]], dtype=complex)
        np.testing.assert_array_equal(power_response(active, 50, 50)[0], active)
        with self.assertRaisesRegex(ValueError, 'non-passive or fail power balance'):
            power_response(active, 50, 50, check_power=True)

    def test_fail_closed_profile_inputs(self):
        # Separate disposable RF trees preserve actual registered sources.
        mutations = ('missing', 'missing_band', 'unknown_band', 'unknown', 'nan', 'inf', 'duplicate', 's2p', 'bands', 'range', 'duplicate_row', 'wrong_role', 'unknown_top', 'old_objective')
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory(prefix='issue450-test-') as tmp:
                root = Path(tmp)
                shutil.copytree(ROOT/'rf', root/'rf')
                path = root/'rf/constraints/trial/RF-T009.json'
                data = json.loads(path.read_text())
                if mutation == 'missing': del data['limits_db']['B13']['ul_il_max']
                if mutation == 'missing_band': del data['limits_db']['B13']
                if mutation == 'unknown_band': data['limits_db']['B99'] = data['limits_db']['B13']
                if mutation == 'unknown': data['limits_db']['B71']['override'] = 1
                if mutation == 'nan': data['limits_db']['B71']['ul_il_max'] = float('nan')
                if mutation == 'inf': data['limits_db']['B71']['ul_il_max'] = float('inf')
                if mutation == 's2p': data['external_s2p']['input']['sha256'] = '0'*64
                if mutation == 'wrong_role': data['external_s2p']['input']['port_flip'] = True
                if mutation == 'unknown_top': data['default'] = 1
                if mutation == 'old_objective': data['objective'] = 'minimax_signed_margin_db'
                path.write_text(json.dumps(data))
                if mutation == 'duplicate': path.write_text(path.read_text().replace('"kind":', '"kind": "rf_performance_profile", "kind":'))
                if mutation in ('bands', 'range', 'duplicate_row'):
                    bp = root/'rf/bands.csv'
                    text = bp.read_text()
                    if mutation == 'duplicate_row':
                        lines = text.splitlines()
                        lines[2] = lines[1]
                        text = '\n'.join(lines) + '\n'
                    else:
                        text = text.replace('663,698', '663,699' if mutation == 'bands' else '663,7000')
                    bp.write_text(text)
                    if mutation != 'bands':
                        # Make the bands hash consistent so semantic/range checks execute.
                        rp = root/'rf/constraints/registry.json'
                        registry = json.loads(rp.read_text())
                        registry['minimax_profiles']['RF-T009']['bands_sha256'] = hashlib.sha256(bp.read_bytes()).hexdigest()
                        rp.write_text(json.dumps(registry))
                with self.assertRaises(ValueError): load_minimax_profile('RF-T009', allow_trial=True, root=root)


if __name__ == '__main__': unittest.main()
