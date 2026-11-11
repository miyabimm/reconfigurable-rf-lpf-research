"""Stage-3 synthetic requirements/ordering and bounded Stage-2 integration."""
import copy
from dataclasses import replace
from pathlib import Path
import unittest
import subprocess
import sys
import numpy as np

from test_issue307_constraints import make
from lpf.constraint_versions import load_constraint
from lpf.rf_core import build_rf_model, EvaluationGrid
from lpf.rf_core.model import RFResponse
from lpf.search.performance import compile_requirements, evaluate_requirements, prepare_requirements
from lpf.search.validation import rank_candidates

BANDS = Path(__file__).resolve().parents[1] / 'rf/bands.csv'


def grid(req, full_extra=True):
    f, s, seg = [], [], []
    for i in req.intervals:
        points = (np.arange(i.low_hz, i.high_hz+i.step_hz, i.step_hz)
                  if i.step_hz and full_extra else [i.low_hz, i.high_hz])
        f.extend(points); s.extend([i.setting]*len(points)); seg.extend([i.segment]*len(points))
    return EvaluationGrid(f, s, seg)


def synthetic(req, g=None):
    g = grid(req) if g is None else g
    il = np.where(np.isin(g.segment, req.objective_segments), .2, 36.)
    s = np.full((len(il), 2, 2), .1, complex)
    s[:, 1, 0] = 10**(-il/20)
    return RFResponse(g, req.policy_id, req.policy_fingerprint, s, il,
                      il.copy(), np.full(len(il), 20.), np.full(len(il), 20.))


def assess(r, req):
    return evaluate_requirements(r, req, requested_grid=r.grid)


class PerformanceTests(unittest.TestCase):
    def setUp(self):
        self.p = load_constraint('RF-F003')
        self.req = compile_requirements(self.p, BANDS)

    def test_prepared_solver_parity_and_grid_identity(self):
        for cid in ('RF-F003', 'RF-T006', 'RF-T008'):
            req = compile_requirements(load_constraint(cid, allow_trial=True), BANDS)
            r = synthetic(req)
            prepared = prepare_requirements(req, r.grid)
            old = assess(r, req)
            new = evaluate_requirements(r, prepared)
            self.assertEqual(old['worst_il_db'], new['worst_il_db'])
            np.testing.assert_array_equal(old['mandatory_g'], new['mandatory_g'])
            self.assertEqual(set(new), {'worst_il_db', 'mandatory_g'})
            clone = EvaluationGrid(r.grid.frequency_hz, r.grid.setting, r.grid.segment)
            with self.assertRaisesRegex(ValueError, 'identity'):
                evaluate_requirements(replace(r, grid=clone), prepared)
            with self.assertRaisesRegex(ValueError, 'policy'):
                evaluate_requirements(replace(r, policy_id='wrong'), prepared)
            with self.assertRaises(ValueError):
                prepared.indices[0].setflags(write=True)
            missing = EvaluationGrid(r.grid.frequency_hz[2:], r.grid.setting[2:], r.grid.segment[2:])
            with self.assertRaises(ValueError):
                prepare_requirements(req, missing)
            il, s = r.il_db.copy(), r.s.copy()
            stop = next(i for i, seg in enumerate(r.grid.segment) if seg == 2)
            il[stop] = np.inf
            s[stop, 1, 0] = 0
            apl = r.apl_db.copy(); apl[stop] = np.inf
            zero = replace(r, il_db=il, apl_db=apl, s=s)
            np.testing.assert_array_equal(assess(zero, req)['mandatory_g'],
                                          evaluate_requirements(zero, prepared)['mandatory_g'])
        req = compile_requirements(load_constraint('RF-T008', allow_trial=True), BANDS, 'matching_only')
        r = synthetic(req)
        prepared = prepare_requirements(req, r.grid)
        self.assertEqual(prepared.mandatory, ())
        self.assertEqual(assess(r, req)['mandatory_g'], ())
        self.assertEqual(evaluate_requirements(r, prepared)['mandatory_g'], ())
        self.assertEqual(evaluate_requirements(r, prepared)['worst_il_db'], assess(r, req)['worst_il_db'])

    def test_current_policies_modes_and_immutable_sources(self):
        for cid in ('RF-F003', 'RF-T005', 'RF-T006', 'RF-T007', 'RF-T008'):
            p = load_constraint(cid, allow_trial=True)
            before = copy.deepcopy(p)
            for mode in ('full_lpf', 'matching_only'):
                req = compile_requirements(p, BANDS, mode)
                normal = [i for i in req.intervals if i.csv_line is not None]
                self.assertEqual(len(normal), 28 if mode == 'full_lpf' else 14)
                self.assertEqual(len({i.setting for i in normal}), 6)
                self.assertEqual(len({i.identity for i in normal}), len(normal))
                self.assertEqual([i.csv_line for i in normal if i.note == 'B13'],
                                 [14, 16, 18, 20] if mode == 'full_lpf' else [14, 16])
                for r in req.limits:
                    if r.interval.region in ('H2', 'H3'):
                        self.assertEqual(r.threshold_db, 30 if r.level == 'mandatory' else 35)
                    if r.interval.type == 'pass':
                        self.assertEqual((r.level, r.threshold_db), ('nominal', .3))
                extra = [i for i in req.intervals if i.step_hz]
                self.assertEqual(len(extra), 6 if cid == 'RF-T006' and mode == 'full_lpf' else 0)
                if extra:
                    self.assertEqual(sum((i.high_hz-i.low_hz)//i.step_hz+1 for i in extra), 18006)
                    self.assertEqual({r.threshold_db for r in req.limits if r.interval.step_hz}, {20})
            self.assertEqual(p, before)

    def test_selectors_override_margin_and_new_metrics(self):
        p = copy.deepcopy(self.p)
        perf = p['evaluation']['performance']
        perf['limits']['overrides'] = [dict(metric='attenuation_db', selector={'case': 'B13+B14', 'note': 'B13', 'region': 'H2'}, min_db=31, level='mandatory')]
        perf['limits']['defaults'].append(dict(metric='in_rl_db', selector={'case': 'B71', 'region': 'UL'}, min_db=10, level='mandatory'))
        perf['margins'] = [dict(selector={'case': 'B71', 'region': 'UL'}, lower_mhz=1, upper_mhz=2)]
        req = compile_requirements(p, BANDS)
        self.assertEqual((req.intervals[0].low_hz, req.intervals[0].high_hz), (662e6, 700e6))
        self.assertEqual(req.intervals[2].low_hz, 1326e6)  # no harmonic scaling
        h2 = [r for r in req.limits if r.interval.region == 'H2' and r.interval.case == 'B13+B14' and r.level == 'mandatory']
        self.assertEqual([(r.interval.note, r.threshold_db) for r in h2], [('B13', 31.), ('B14', 30.)])
        response = synthetic(req)
        detailed = assess(response, req)
        self.assertTrue(detailed['strict_feasible'])
        np.testing.assert_array_equal(detailed['mandatory_g'],
            evaluate_requirements(response, prepare_requirements(req, response.grid))['mandatory_g'])

    def test_existing_scalar_import_does_not_require_src_on_sys_path(self):
        # Smoke's existing src.lpf consumers must not import the lpf-only RF
        # core just by importing scalar helpers. Fresh interpreter avoids the
        # test process's sys.path edits and cached lpf modules.
        code = (f'import sys; sys.path.insert(0, {str(BANDS.parents[1])!r}); '
                'from src.lpf.search.performance import harmonic_limit_db; '
                'from src.lpf.constraint_versions import load_constraint; '
                'assert harmonic_limit_db(load_constraint("RF-F003")) == 30')
        result = subprocess.run([sys.executable, '-I', '-c', code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_each_metric_bound_and_infinite_reflection(self):
        p = copy.deepcopy(self.p)
        rules = p['evaluation']['performance']['limits']['defaults']
        for metric, bound, threshold in (('in_rl_db', 'min_db', 21),
                                          ('out_rl_db', 'max_db', 19),
                                          ('apl_db', 'max_db', .1)):
            rule = dict(metric=metric, selector={'case': 'B71', 'region': 'UL'},
                        level='mandatory', **{bound: threshold})
            rules.append({**rule, bound: threshold + 3})
            p['evaluation']['performance']['limits']['overrides'].append(rule)
        req = compile_requirements(p, BANDS)
        r = synthetic(req)
        a = assess(r, req)
        self.assertEqual(a['max_violation_db'], 1)
        self.assertAlmostEqual(a['sum_violation_db'], 2.1)
        np.testing.assert_array_equal(a['mandatory_g'],
            evaluate_requirements(r, prepare_requirements(req, r.grid))['mandatory_g'])
        s = r.s.copy(); s[0, 0, 0] = 0
        rl = r.in_rl_db.copy(); rl[0] = np.inf
        r = replace(r, s=s, in_rl_db=rl)
        a = assess(r, req)
        np.testing.assert_array_equal(a['mandatory_g'],
            evaluate_requirements(r, prepare_requirements(req, r.grid))['mandatory_g'])
        row = next(row for row in a['rows'] if row['requirement'].metric == 'in_rl_db')
        self.assertEqual(row['residuals_db'], (-np.inf, 1.))

    def test_fail_closed_declarations(self):
        base = self.p['evaluation']['performance']
        bad = []
        def add(change):
            p = copy.deepcopy(self.p); change(p['evaluation']['performance']); bad.append(p)
        rule = dict(metric='attenuation_db', selector={'region': 'H2'}, min_db=31, level='mandatory')
        add(lambda p: p['limits']['defaults'].append(copy.deepcopy(p['limits']['defaults'][0])))
        add(lambda p: p['limits']['overrides'].extend([rule, rule]))
        add(lambda p: p['limits']['overrides'].append({**rule, 'metric': 'apl_db'}))
        for selector in ({'region': 'unknown'}, {'unknown': 'B71'}, {}):
            add(lambda p, selector=selector: p['limits']['overrides'].append({**rule, 'selector': selector}))
        for key, value in (('metric', 'gt'), ('level', 'hard'), ('min_db', float('nan')), ('direction', 'up')):
            add(lambda p, key=key, value=value: p['limits']['defaults'].append({**rule, key: value}))
        for lower, upper in ((-1, 0), (700, 0), (0, 6000)):
            add(lambda p, lower=lower, upper=upper: p['margins'].append(dict(selector={'region': 'UL'}, lower_mhz=lower, upper_mhz=upper)))
        margin = dict(selector={'region': 'UL'}, lower_mhz=1, upper_mhz=0)
        add(lambda p: p['margins'].extend([margin, margin]))
        add(lambda p: p.update(objective={**p['objective'], 'direction': 'maximize'}))
        for p in bad:
            with self.subTest(performance=p['evaluation']['performance']), self.assertRaises(ValueError):
                compile_requirements(p, BANDS)
        self.assertEqual(base, self.p['evaluation']['performance'])

    def test_sample_residuals_nominal_argworst_and_vsum(self):
        r = synthetic(self.req)
        il = r.il_db.copy()
        il[4:6] = [28, 29]  # first H2: deficit 2, not sample sum 3
        il[6:8] = [27, 31]  # first H3: deficit 3
        il[0] = .5         # nominal only
        a = assess(replace(r, il_db=il), self.req)
        self.assertFalse(a['strict_feasible'])
        self.assertEqual((a['max_violation_db'], a['sum_violation_db']), (3, 5))
        row = next(row for row in a['rows'] if row['requirement'].interval.segment == 2 and row['requirement'].level == 'mandatory')
        self.assertEqual(row['residuals_db'], (2., 1.))
        self.assertEqual(row['sample_pass'], (False, False))
        self.assertEqual((row['worst_observation_db'], row['worst_frequency_hz'], row['worst_setting']), (28, 1326e6, 0))
        self.assertEqual(min(a['mandatory_g']), -3)
        il = r.il_db.copy(); il[0] = 1.
        a = assess(replace(r, il_db=il), self.req)
        self.assertTrue(a['strict_feasible'])
        self.assertEqual(a['sum_violation_db'], 0)
        self.assertTrue(any(not row['passed'] for row in a['rows']))

    def test_missing_wrong_grid_policy_undefined_and_zero_transmission(self):
        r = synthetic(self.req)
        for changed in (replace(r, policy_id='RF-T005'), replace(r, policy_fingerprint='bad'),
                        replace(r, il_db=np.full(len(r.il_db), np.nan)),
                        replace(r, apl_db=np.full(len(r.il_db), -np.inf)),
                        replace(r, out_rl_db=np.full(len(r.il_db), np.inf))):
            with self.assertRaises(ValueError):
                assess(changed, self.req)
        g = r.grid
        missing = EvaluationGrid(g.frequency_hz[1:], g.setting[1:], g.segment[1:])
        with self.assertRaises(ValueError):
            evaluate_requirements(replace(r, grid=missing), self.req, requested_grid=g)
        absent_interval = EvaluationGrid(g.frequency_hz[2:], g.setting[2:], g.segment[2:])
        with self.assertRaises(ValueError):
            assess(synthetic(self.req, absent_interval), self.req)
        # Normal interval density is supplied by the caller, not hard-coded.
        one_point = EvaluationGrid(g.frequency_hz[::2], g.setting[::2], g.segment[::2])
        self.assertTrue(assess(synthetic(self.req, one_point), self.req)['strict_feasible'])
        wrong = EvaluationGrid(g.frequency_hz, (g.setting+1)%6, g.segment)
        with self.assertRaises(ValueError):
            assess(synthetic(self.req, wrong), self.req)
        s, il, apl = r.s.copy(), r.il_db.copy(), r.apl_db.copy()
        s[4, 1, 0] = 0; il[4] = apl[4] = np.inf
        a = assess(replace(r, s=s, il_db=il, apl_db=apl), self.req)
        self.assertTrue(a['strict_feasible'])
        s[0, 1, 0] = 0; il[0] = apl[0] = np.inf
        a = assess(replace(r, s=s, il_db=il, apl_db=apl), self.req)
        self.assertEqual(a['worst_il_db'], np.inf)  # valid poor objective, not NaN/floor

    def test_t006_completeness_without_rf_forward(self):
        req = compile_requirements(load_constraint('RF-T006', allow_trial=True), BANDS)
        partial = synthetic(req, grid(req, full_extra=False))
        with self.assertRaises(ValueError):
            assess(partial, req)
        a = assess(synthetic(req), req)  # arrays only: no 18006-point RF computation
        self.assertTrue(a['strict_feasible'])
        req = compile_requirements(load_constraint('RF-T006', allow_trial=True), BANDS, 'matching_only')
        a = assess(synthetic(req), req)
        self.assertEqual(a['mode'], 'matching_only')
        self.assertFalse(any(r['requirement'].interval.region in ('H2', 'H3', 'additional') for r in a['rows']))

    def test_rank_and_real_small_grid(self):
        p, d, _, _, x = make('RF-F003')
        model = build_rf_model(d, p)
        req = compile_requirements(p, BANDS)
        g = grid(req)
        real = assess(model.evaluator(g).evaluate(x), req)
        self.assertEqual(len(real['samples']), 56)
        r = synthetic(req)
        good = assess(r, req)
        il = r.il_db.copy(); il[4] = 29
        fail = assess(replace(r, il_db=il), req)
        def candidate(a, vector=x):
            return dict(model=model, vector=vector, assessment=a)
        x2 = x.copy(); x2[-1] += .01
        invalid = x.copy(); invalid[0] = -1
        result = rank_candidates([candidate(fail), candidate(good, x2), candidate(good), candidate(None), candidate(good, invalid)])
        self.assertEqual([c['status'] for c in result['ranked']], ['pass', 'pass', 'fail'])
        digests = [c['vector_sha256'] for c in result['ranked'][:2]]
        self.assertEqual(digests, sorted(digests))
        self.assertEqual({c['status'] for c in result['excluded']}, {'unrun', 'invalid'})
        for key in ('mode', 'grid_fingerprint', 'requirements_fingerprint'):
            with self.assertRaises(ValueError):
                rank_candidates([candidate(good), candidate({**good, key: 'different'})])
        # FAIL order is Vmax, then interval-wise Vsum, then objective, then SHA.
        il2 = r.il_db.copy(); il2[4] = il2[6] = 29
        two_fail = assess(replace(r, il_db=il2), req)
        ordered = rank_candidates([candidate(two_fail), candidate(fail)])['ranked']
        self.assertEqual([c['assessment']['sum_violation_db'] for c in ordered], [1, 2])
        high_max_il = r.il_db.copy(); high_max_il[4] = 28.5
        high_max = assess(replace(r, il_db=high_max_il), req)
        ordered = rank_candidates([candidate(high_max), candidate(two_fail)])['ranked']
        self.assertIs(ordered[0]['assessment'], two_fail)  # Vmax before Vsum
        numeric = rank_candidates([candidate({'status': 'numerical_failure'})])
        self.assertEqual(numeric['ranked'], [])
        self.assertEqual(numeric['excluded'][0]['status'], 'not_evaluated')
        low_il = r.il_db.copy(); low_il[0:4] = .1
        # all other pass intervals also lower to change the actual worst IL
        low_il[np.isin(g.segment, req.objective_segments)] = .1
        better = assess(replace(r, il_db=low_il), req)
        self.assertIs(rank_candidates([candidate(good), candidate(better)])['ranked'][0]['assessment'], better)


if __name__ == '__main__':
    unittest.main()
