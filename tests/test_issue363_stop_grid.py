"""Opt-in fixed stage grid; bounded software checks, not an RF search or EXP."""
from dataclasses import asdict, replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

import test_issue313_preflight as preflight_tests
import test_issue315_fixed_stage as fixed_stage_tests

ROOT = preflight_tests.ROOT
from lpf.constraint_versions import load_constraint
from lpf.search.performance import (MAX_GRID_SAMPLES, _digest, build_evaluation_grid,
                                    compile_requirements, grid_fingerprint)
from lpf.search.problem import Problem


class StopGridTests(unittest.TestCase):
    def requirements(self, cid='RF-T008', mode='full_lpf'):
        return compile_requirements(load_constraint(cid, allow_trial=True), ROOT/'rf/bands.csv', mode)

    def test_intervals_endpoints_centres_gaps_modes_and_legacy(self):
        for mode in ('full_lpf', 'matching_only'):
            req = self.requirements(mode=mode)
            legacy = build_evaluation_grid(req, 2)
            self.assertEqual(grid_fingerprint(legacy), grid_fingerprint(build_evaluation_grid(req, 2, None)))
            self.assertEqual(len(legacy.frequency_hz), 56 if mode == 'full_lpf' else 28)
            grid = build_evaluation_grid(req, 2, 3)
            self.assertEqual(len(grid.frequency_hz), 70 if mode == 'full_lpf' else 28)
            self.assertEqual(len(set(grid.segment)), len(req.intervals))
            self.assertEqual(set(grid.setting), set(range(6)))
            for interval in req.intervals:
                ix = (grid.segment == interval.segment) & (grid.setting == interval.setting)
                count = 3 if interval.region in ('H2', 'H3') else 2
                np.testing.assert_array_equal(grid.frequency_hz[ix],
                                              np.linspace(interval.low_hz, interval.high_hz, count))
                self.assertGreaterEqual(interval.low_hz, req.s2p_span_hz[0])
                self.assertLessEqual(interval.high_hz, req.s2p_span_hz[1])
            for region in ('UL', 'DL', 'H2', 'H3') if mode == 'full_lpf' else ('UL', 'DL'):
                pair = [i for i in req.intervals if i.case == 'B13+B14' and i.region == region]
                self.assertEqual([i.note for i in pair], ['B13', 'B14'])
                self.assertLess(pair[0].high_hz, pair[1].low_hz)
                self.assertNotEqual(pair[0].segment, pair[1].segment)

    def test_extra_fixed_step_limits_and_fingerprint(self):
        req = self.requirements('RF-T006')
        grid = build_evaluation_grid(req, 2, 3)
        self.assertEqual(len(grid.frequency_hz), 70 + 18006)
        for i in req.intervals:
            if i.step_hz:
                f = grid.frequency_hz[(grid.segment == i.segment) & (grid.setting == i.setting)]
                self.assertEqual((len(f), f[0], f[-1]), (3001, i.low_hz, i.high_hz))
                np.testing.assert_array_equal(np.diff(f), np.full(3000, i.step_hz))
        req = self.requirements()
        for bad in (True, False, 0, 1, -1, 2.0, '3', float('nan'), MAX_GRID_SAMPLES+1):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                build_evaluation_grid(req, 2, bad)
        with patch('lpf.search.performance.MAX_GRID_SAMPLES', 69), self.assertRaisesRegex(ValueError, 'allocation'):
            build_evaluation_grid(req, 2, 3)
        # Re-sign malformed intervals to exercise structural validation, not just the SHA guard.
        for intervals in (req.intervals[:-1] + (req.intervals[0],),
                          (replace(req.intervals[0], low_hz=0),) + req.intervals[1:]):
            altered = replace(req, intervals=intervals)
            content = asdict(altered); content.pop('fingerprint')
            altered = replace(altered, fingerprint=_digest(content))
            with self.assertRaises(ValueError):
                build_evaluation_grid(altered, 2, 3)
        with self.assertRaisesRegex(ValueError, 'fingerprint'):
            build_evaluation_grid(replace(req, fingerprint='0'*64), 2, 3)

    def test_static_schema_plan_cost_and_grid_readback(self):
        helper = preflight_tests.PreflightTests()
        config = helper.config()
        config['rf'] = dict(constraint_id='RF-T008', allow_trial=True)
        legacy = helper.load(config)
        self.assertEqual(len(legacy.requested_grid('demo/coarse').frequency_hz), 56)
        self.assertEqual(legacy.data['grids']['demo/coarse']['sha256'],
                         '2c571198479f28a26466efcee661053eca55e9620601ccc4c0a445cc89946fe1')
        self.assertNotIn('stop_points_per_interval', legacy.data['grids']['demo/coarse'])
        config['arms'][0]['steps'][0]['stop_points_per_interval'] = 3
        plan = helper.load(config)
        record = plan.data['grids']['demo/coarse']
        grid = plan.requested_grid('demo/coarse')
        self.assertEqual((record['points_per_interval'], record['stop_points_per_interval'],
                          record['requested_samples_per_forward']), (2, 3, 70))
        self.assertEqual(record['sha256'], grid_fingerprint(grid))
        req = self.requirements()
        self.assertEqual(record['interval_samples'], [
            dict(identity=i.identity, segment=i.segment, setting=i.setting,
                 samples=3 if i.region in ('H2', 'H3') else 2) for i in req.intervals])
        self.assertNotEqual(record['sha256'], legacy.data['grids']['demo/coarse']['sha256'])
        self.assertEqual(plan.data['costs']['jobs']['demo']['stages']['coarse']['one_forward_samples'], 70)
        self.assertEqual(plan.data['costs']['jobs']['demo']['stages']['coarse']['upper_reservation'], 1000)
        for name in ('selection', 'terminal', 'anytime', 'dense'):
            self.assertEqual(plan.data['grids'][name], legacy.data['grids'][name])
        config['anytime_samples'] = []
        config['arms'][0]['steps'][0]['max_requested_samples'] = 69
        with self.assertRaises(ValueError):
            helper.load(config)
        config['arms'][0]['steps'][0]['max_requested_samples'] = 70
        self.assertEqual(helper.load(config).data['costs']['jobs']['demo']['stages']['coarse']['one_forward_samples'], 70)
        config['arms'][0]['steps'][0]['max_requested_samples'] = 1000
        config['anytime_samples'] = [200, 400]
        for bad in (None, True, 1, 3.0, '3'):
            config['arms'][0]['steps'][0]['stop_points_per_interval'] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError): helper.load(config)
        config['arms'][0]['steps'][0]['stop_points_per_interval'] = 3
        config['arms'][0]['steps'][0]['unknown'] = 3
        with self.assertRaises(ValueError): helper.load(config)
        del config['arms'][0]['steps'][0]['unknown']
        config['selection']['stop_points_per_interval'] = 3
        with self.assertRaises(ValueError): helper.load(config)

    def test_real_callback_and_raw_readback(self):
        helper = fixed_stage_tests.FixedStageTests()
        helper.setUp()
        try:
            def opt_in(config):
                config['arms'][0]['steps'][0]['stop_points_per_interval'] = 3
                config['arms'][0]['steps'][0]['max_requested_samples'] = 140
                config['anytime_samples'] = []
            plan, definition, policy, x = helper.setup_model('RF-T008', mutate=opt_in)
            evaluation = helper.evaluator(plan, definition, policy)
            problem = Problem.from_fixed_stage(evaluation)
            problem.objective(x)
            problem.constraints(x)
            self.assertEqual((evaluation.requested, evaluation.completed), (140, 140))
            raw = json.loads(Path(evaluation.path).read_text())
            self.assertEqual(raw['plan_sha256'], plan.sha256)
            self.assertEqual(raw['grid_sha256'], plan.data['grids']['demo/coarse']['sha256'])
            self.assertEqual((raw['requested'], raw['completed']), (140, 140))
            self.assertEqual(raw['remaining']['step'], 0)
            for row in raw['batches']:
                self.assertEqual((row['requested'], row['completed'], row['status']), (70, 70, 'completed'))
                self.assertEqual(row['grid_sha256'], raw['grid_sha256'])
                self.assertEqual(len(row['response']['il_db']), 70)
            self.assertEqual(raw['reservations']['selection'], 168)
            self.assertEqual(raw['reservations']['terminal'], 112)
        finally:
            helper.doCleanups()


if __name__ == '__main__':
    unittest.main()
