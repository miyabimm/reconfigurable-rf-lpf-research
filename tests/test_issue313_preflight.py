"""Static planning only: synthetic response, no RF forward or EXP writes."""
import copy
import csv
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from lpf.constraint_versions import load_constraint
from lpf.rf_core.model import EvaluationGrid
from lpf.search.plan import load_preflight
from lpf.search.performance import (compile_requirements, build_evaluation_grid,
                                    grid_fingerprint, evaluate_requirements)
from lpf.search.preflight import check_next_batch
from lpf.search.storage import sha
from test_issue311_performance import synthetic

FIXTURE = ROOT / 'project/fixtures/issue313_preflight.yaml'


class PreflightTests(unittest.TestCase):
    def load(self, config=None):
        if config is None:
            return load_preflight(FIXTURE)
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)/'plan.yaml'
            p.write_text(yaml.safe_dump(config))
            with patch('lpf.rf_core.model.RFEvaluator.evaluate', side_effect=AssertionError('No RF forward')):
                return load_preflight(p)

    def config(self):
        return yaml.safe_load(FIXTURE.read_text())

    def test_all_policies_modes_and_synthetic_completion(self):
        for cid in ('RF-F003', 'RF-T005', 'RF-T006', 'RF-T007', 'RF-T008'):
            for mode in ('full_lpf', 'matching_only'):
                with self.subTest(cid=cid, mode=mode):
                    req = compile_requirements(load_constraint(cid, allow_trial=True), ROOT/'rf/bands.csv', mode)
                    g = build_evaluation_grid(req, 4)
                    extra = 18006 if cid == 'RF-T006' and mode == 'full_lpf' else 0
                    self.assertEqual(len(g.frequency_hz), (28 if mode == 'full_lpf' else 14)*4+extra)
                    self.assertEqual(grid_fingerprint(g), grid_fingerprint(build_evaluation_grid(req, 4)))
                    for i in req.intervals:
                        f = g.frequency_hz[(g.segment == i.segment) & (g.setting == i.setting)]
                        self.assertEqual((f[0], f[-1]), (i.low_hz, i.high_hz))
                        self.assertEqual(len(f), 3001 if i.step_hz else 4)
                        if i.step_hz:
                            np.testing.assert_array_equal(np.diff(f), np.full(3000, 1e6))
                    with self.assertRaises(ValueError):
                        g.frequency_hz.flags.writeable = True
                    result = evaluate_requirements(synthetic(req, g), req, requested_grid=g)
                    self.assertTrue(result['strict_feasible'])
                    missing = EvaluationGrid(g.frequency_hz[:-1], g.setting[:-1], g.segment[:-1])
                    with self.assertRaises(ValueError):
                        evaluate_requirements(synthetic(req, missing), req, requested_grid=g)

    def test_margin_overlap_and_invalid_requirements(self):
        p = load_constraint()
        p['evaluation']['performance']['margins'] = [dict(selector={'region': 'UL'}, lower_mhz=1, upper_mhz=2)]
        req = compile_requirements(p, ROOT/'rf/bands.csv')
        g = build_evaluation_grid(req, 3)
        self.assertEqual((g.frequency_hz[0], g.frequency_hz[2]), (662e6, 700e6))
        with (ROOT/'rf/bands.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        rows[1]['low_mhz'], rows[1]['high_mhz'] = rows[0]['low_mhz'], rows[0]['high_mhz']
        overlapping = build_evaluation_grid(compile_requirements(load_constraint(), rows), 3)
        np.testing.assert_array_equal(overlapping.frequency_hz[:3], overlapping.frequency_hz[3:6])
        self.assertNotEqual(overlapping.segment[0], overlapping.segment[3])
        self.assertEqual(len(g.frequency_hz), 84)
        for bad in (True, 1, 0, -1, 2.5, float('nan'), 10**100):
            with self.subTest(points=bad), self.assertRaises(ValueError):
                build_evaluation_grid(req, bad)
        for intervals in (req.intervals[:-1], req.intervals+(req.intervals[0],),
                          (replace(req.intervals[0], low_hz=0),)+req.intervals[1:]):
            with self.assertRaises(ValueError):
                build_evaluation_grid(replace(req, intervals=intervals), 3)
        p['evaluation']['performance']['margins'][0]['upper_mhz'] = 10000
        with self.assertRaises(ValueError):
            compile_requirements(p, ROOT/'rf/bands.csv')

    def test_frozen_yaml_costs_and_plan_origin_grid(self):
        plan = self.load()
        self.assertEqual(plan.sha256, self.load().sha256)
        d = plan.data
        job = d['costs']['jobs']['demo']
        self.assertEqual(job['stages']['coarse']['one_forward_samples'], 56)
        self.assertEqual(job['selection_upper_reservation'], 168)
        self.assertEqual(job['terminal_fixed_reservation'], 112)
        self.assertEqual(job['anytime_fixed_reservation'], 168)
        self.assertEqual(job['total_upper_reservation'], 1448)
        self.assertEqual(job['runtime_reserved_samples'], 448)
        self.assertEqual(job['stages']['coarse']['reserved_after_step'], 448)
        self.assertEqual(d['costs']['dense']['upper_reservation'], 392)
        self.assertEqual(d['costs']['dense']['status'], 'not_run')
        self.assertEqual(d['execution']['requested_samples'], 0)
        req = compile_requirements(load_constraint(), ROOT/'rf/bands.csv')
        g = plan.requested_grid('terminal')
        evaluate_requirements(synthetic(req, g), req, requested_grid=g)
        for path, value in [('anytime_points_per_interval', 2), ('max_trial_requested_samples', 2500)]:
            config = self.config(); config[path] = value
            self.assertNotEqual(plan.sha256, self.load(config).sha256)
        config = self.config(); config['arms'][0]['steps'][0]['options']['max_iterations'] = 4
        self.assertNotEqual(plan.sha256, self.load(config).sha256)

    def test_invalid_yaml_and_conflicting_caps_stop(self):
        mutations = [
            lambda d: d.pop('anytime_points_per_interval'),
            lambda d: d.update(anytime_points_per_interval=1),
            lambda d: d.update(anytime_samples=[1, 1]),
            lambda d: d.update(anytime_samples=[1001]),
            lambda d: d.update(anytime_samples=[float('nan')]),
            lambda d: d.update(max_trial_requested_samples=1499),
            lambda d: d['rf'].update(constraint_id='RF-T006'),
            lambda d: d['arms'][0].update(max_requested_samples=1447),
            lambda d: d['arms'][0]['steps'][0].update(max_requested_samples=55),
            lambda d: d['arms'][0]['steps'][0].update(points_per_interval=True),
            lambda d: d['arms'][0]['steps'][0].update(solver='unknown'),
            lambda d: d['arms'][0]['steps'][0]['options'].update(max_evaluations=0),
            lambda d: d['selection'].update(top_k=3),
            lambda d: d['selection'].update(points_per_interval=1),
            lambda d: d['validation'].update(terminal_points=1),
            lambda d: d['validation'].update(dense_points=1),
            lambda d: d['validation'].update(max_requested_samples=391),
        ]
        for mutate in mutations:
            d = self.config(); mutate(d)
            with self.subTest(config=d), self.assertRaises(ValueError):
                self.load(d)
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)/'bad.yaml'; p.write_text('schema_version: 2\nschema_version: 2\n')
            with self.assertRaises(ValueError):
                load_preflight(p)

    def test_full_batch_boundary_and_reservation_release(self):
        kw = dict(step_remaining=56, job_remaining=336, trial_remaining=500,
                  job_reserved=280, trial_reserved=444)
        check_next_batch(56, **kw)
        for key in ('step_remaining', 'job_remaining', 'trial_remaining'):
            bad = dict(kw); bad[key] -= 1
            with self.subTest(key=key), self.assertRaises(ValueError):
                check_next_batch(56, **bad)
        with self.assertRaises(ValueError):
            check_next_batch(56, **dict(kw, job_reserved=float('nan')))

    def test_multiple_stages_jobs_and_solver_caps(self):
        d = self.config()
        first = d['arms'][0]['steps'][0]
        first.update(solver='hybrid', options=dict(maxiter=3, max_restarts=0,
                                                 max_evaluations=8, restart_sigma=.2))
        second = copy.deepcopy(first)
        second.update(name='fine', solver='slp', aggregation='signed_max',
                      points_per_interval=5,
                      options=dict(max_iterations=3, max_evaluations=8))
        d['arms'][0]['steps'].append(second)
        d['arms'][0]['max_requested_samples'] = 2500
        other = copy.deepcopy(d['arms'][0]); other['name'] = 'other'
        d['arms'].append(other)
        d['max_trial_requested_samples'] = 5000
        p = self.load(d)
        j = p.data['costs']['jobs']['demo']
        self.assertEqual(j['stages']['coarse']['reserved_after_step'], 1448)
        self.assertEqual(j['stages']['fine']['reserved_after_step'], 448)
        self.assertEqual(j['stages']['fine']['one_forward_samples'], 140)
        self.assertEqual(p.data['costs']['trial_job_cap_reservation'], 5000)
        d['arms'][0]['steps'][0]['options']['restart_sigma'] = float('nan')
        with self.assertRaises(ValueError):
            self.load(d)

    def test_definition_sources_and_s2p_sha_fail_closed(self):
        d = self.config()
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            source = Path(temp)/'definition.json'
            raw = b'{"source": "static reference only"}'
            source.write_bytes(raw)
            d['definition'] = dict(path=str(source.relative_to(ROOT)),
                                   source_sha256=hashlib.sha256(raw).hexdigest(),
                                   definition_sha256=sha(json.loads(raw)))
            p = self.load(d)
            self.assertEqual(p.data['config']['definition'], d['definition'])
            source.write_bytes(b'{}')
            with self.assertRaises(ValueError):
                self.load(d)
            from lpf.constraint_versions import rf_input_file
            def replaced(root, path):
                return rf_input_file(root, path) if 'bands' in path else source
            with patch('lpf.search.preflight.rf_input_file', side_effect=replaced):
                with self.assertRaisesRegex(ValueError, 'S2P SHA'):
                    self.load(self.config())

    def test_t006_plan_and_model_free_matching(self):
        d = self.config()
        d['rf'] = dict(constraint_id='RF-T006', allow_trial=True)
        # The trial adds samples to every full-LPF forward, not every metric.
        for arm in d['arms']:
            arm['steps'][0]['max_requested_samples'] = 20000
            arm['max_requested_samples'] = 200000
        d['max_trial_requested_samples'] = 200000
        d['validation']['max_requested_samples'] = 100000
        p = self.load(d)
        self.assertEqual(len(p.requested_grid('selection').frequency_hz), 18006+84)
        d['objective'] = 'matching_only'
        p = self.load(d)
        self.assertEqual(len(p.requested_grid('selection').frequency_hz), 42)


if __name__ == '__main__':
    unittest.main()
