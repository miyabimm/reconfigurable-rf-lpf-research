"""Issue 458: bounded profile and existing-candidate checks; no scientific EXP."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from lpf.constraint_versions import constraint_fingerprint, load_constraint
from lpf.minimax_profile import load_minimax_profile, signed_margins
from lpf.rf_core.model import build_rf_model
from lpf.rf_core.independent import evaluate_independent_response
from lpf.search import _development_runner as runner
from lpf.search.component_constraints import validate_values
from lpf.search.performance import build_evaluation_grid, compile_profile_grid
from lpf.search.plan import ROOT
from lpf.search.proposals import definition_from_data
from lpf.search.storage import sha, vector_sha


class Profile458Tests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT/'project/diagnostics/issue361/definition.json').read_text())
        self.assertEqual(sha(self.data), 'bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068')
        self.x = json.loads((ROOT/'experiments/chatgpt_topology_search/runs/EXP-062/checkpoints/a6_best.json').read_text())['vector']
        self.assertEqual(vector_sha(self.x), '4131fa4e677afd364c8e448325d2971f05214284047c349bf2f794585668313c')
        self.cfg = dict(schema_version=1, rf=dict(constraint_id='RF-T010', allow_trial=True),
            definition=self.data, seeds=[23], terminal_points=4,
            arms=[dict(name='demo', steps=[dict(name='coarse', solver='hybrid', objective='signed_margin_db',
                aggregation='sum', points_per_interval=2, options=dict(max_search_forwards=2))])],
            budget=dict(rf_samples=224, rf_forwards=3, independent_mna_samples=2))
        self.starts = {'23': {'demo': dict(vector=self.x, vector_sha256=vector_sha(self.x))}}

    def freeze(self, root=ROOT):
        return runner.freeze_run(self.cfg, self.starts, root=root, spot_checks={'terminal': [0, 57]},
                                 search_bounds=None, checkpoint_interval=1)

    def test_existing_candidate_forward_and_margins(self):
        p = load_minimax_profile('RF-T010', allow_trial=True)
        base = load_constraint('RF-T008', allow_trial=True)
        self.assertEqual(p.base_sha256, 'e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532')
        self.assertEqual(p.fingerprint, 'd50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417')
        for limits in p.profile['limits_db'].values():
            self.assertEqual(limits, dict(ul_il_max=.75, dl_il_max=.75, h2_atten_min=30, h3_atten_min=30))
        d = definition_from_data(self.data)
        a, b = build_rf_model(d, base), p.build_model(d)
        physical = validate_values(d, a.schema, self.x, base, frozen_model=a)
        self.assertTrue(physical['component_policy_pass'])
        g = build_evaluation_grid(compile_profile_grid(p), 17)
        self.assertEqual(len(g.frequency_hz), 476)
        old, new = a.evaluator(g).evaluate(self.x, check_power=True), b.evaluator(g).evaluate(self.x, check_power=True)
        for key in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
            np.testing.assert_allclose(getattr(old, key), getattr(new, key), rtol=0, atol=1e-9)
        j, margins = signed_margins(p, g, new)
        regions = np.array([p.records[i]['region'] for i in g.segment])
        passed = np.isin(regions, ['UL', 'DL'])
        expected = np.where(passed, new.il_db-.75, 30-new.il_db)
        np.testing.assert_allclose(margins, expected, atol=1e-12)
        self.assertEqual(j, max(margins))
        self.assertAlmostEqual(max(new.il_db[passed]), .82784114846, places=9)
        self.assertGreater(j, 0)
        self.assertGreaterEqual(min(new.il_db[~passed]), 30)
        for i in (0, 57):
            ref = evaluate_independent_response(b, self.x, float(g.frequency_hz[i]), int(g.setting[i]))
            for key in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
                np.testing.assert_allclose(getattr(new, key)[i], ref[key], rtol=0, atol=1e-9)
        print('T010 476-point: worst IL', max(new.il_db[passed]), 'min H2/H3', min(new.il_db[~passed]), 'J', j)

    def test_hybrid_sigma_plan(self):
        options = self.cfg['arms'][0]['steps'][0]['options']
        fingerprints = []
        for sigma in (None, .03, .10, .30):
            if sigma is None:
                options.pop('restart_sigma', None)
            else:
                options['restart_sigma'] = sigma
            plan = self.freeze()[0]
            step = plan.data['config']['arms'][0]['steps'][0]
            self.assertEqual(step['effective_options']['restart_sigma'], .1 if sigma is None else sigma)
            self.assertEqual(plan.sha256, sha(plan.data))
            fingerprints.append(plan.sha256)
        self.assertEqual(len(set(fingerprints)), 4)
        for invalid in (True, False, None, '0.1', [], float('nan'), float('inf'),
                        -float('inf'), 0, -0.1, 10**400):
            options['restart_sigma'] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.freeze()
        options['restart_sigma'] = .1
        options['extra'] = 1
        with self.assertRaises(ValueError):
            self.freeze()

    def test_runner_smoke(self):
        self.cfg['arms'][0]['steps'][0]['options']['restart_sigma'] = .03
        with tempfile.TemporaryDirectory(prefix='issue458-smoke-') as tmp:
            out = Path(tmp)/'run'
            state = runner.run(self.cfg, self.starts, out, root=ROOT, spot_checks={'terminal':[0,57]},
                               search_bounds=None, checkpoint_interval=1)
            plan = json.loads((out/'plan.json').read_text())
            self.assertEqual(state['kind'], 'development_rf_profile_run_v1')
            self.assertEqual(plan['rf_profile']['constraint_id'], 'RF-T010')
            self.assertEqual(plan['rf_profile']['base_constraint_id'], 'RF-T008')
            row = state['jobs'][0]
            self.assertEqual(row['status'], 'completed')
            self.assertEqual(row['scientific_status'], 'not_converged')
            for key in ('rf_samples', 'rf_forwards', 'independent_mna_samples'):
                self.assertEqual(row['actual'][key]+row['released'][key], row['reservation'][key])
            self.assertTrue(list((out/'job-0001/checkpoints').iterdir()))
            result = json.loads((out/'job-0001/result.json').read_text())
            terminal = result['terminal']['candidates'][0]
            self.assertEqual(terminal['independent']['status'], 'pass')
            self.assertEqual(terminal['independent']['sample_indices'], [0, 57])
            self.assertEqual(terminal['external_passivity'], 'checked_on_terminal_grid')
            self.assertEqual(terminal['power_balance'], 'checked_on_terminal_grid')
            self.assertTrue(terminal['physical']['component_policy_pass'])
            self.assertGreater(terminal['physical']['min_L_eigenvalue_H'], 0)
            self.assertEqual(terminal['terminal_signed_max_margin_db'], max(terminal['signed_margins_db']))
            self.assertEqual(terminal['performance_feasible'], terminal['terminal_signed_max_margin_db'] <= 0)
            self.assertEqual(set(terminal['response']['grid']['setting']), set(range(6)))
            self.assertEqual(set(terminal['response']['grid']['segment']), set(range(28)))
            self.assertEqual(plan['config']['arms'][0]['steps'][0]['effective_objective'],
                             'sum_squared_positive_violation_db2_unit_weights')
            self.assertIn('squared positive violations', result['solver_objective']['slsqp_hybrid'])
            step = result['steps'][0]
            profile = load_minimax_profile('RF-T010', allow_trial=True)
            model = profile.build_model(definition_from_data(self.data))
            from lpf.search.plan import grid_from_record
            g = grid_from_record(plan['grids']['demo/coarse'])
            _, residual = signed_margins(profile, g, model.evaluator(g).evaluate(step['solver_result']['x']))
            self.assertAlmostEqual(step['solver_result']['objective'], np.sum(np.maximum(residual, 0)**2), places=9)
            self.assertEqual(row['actual'], dict(rf_samples=step['requested_samples'] + 112,
                                                rf_forwards=step['forward_count'] + 1,
                                                independent_mna_samples=2))
            receipt = json.loads((out/'job-0001/receipt.json').read_text())
            for name, info in receipt['files'].items():
                blob = (out/'job-0001'/name).read_bytes()
                self.assertEqual(info, dict(bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest()))
                self.assertEqual(row['raw'][name], info)
            receipt_blob = (out/'job-0001/receipt.json').read_bytes()
            self.assertEqual(row['raw']['receipt.json'], dict(bytes=len(receipt_blob),
                             sha256=hashlib.sha256(receipt_blob).hexdigest()))
            self.assertEqual(plan['config']['arms'][0]['steps'][0]['effective_options']['restart_sigma'], .03)
            self.assertEqual(result['steps'][0]['solver_options']['restart_sigma'], .03)
            self.assertEqual(result['steps'][0]['local_runs'], 1)
            self.assertEqual(result['plan_sha256'], sha(plan))
            print('T010 smoke reservation', row['reservation'], 'actual', row['actual'])

    def test_hybrid_local_run_callback_counts_each_invocation(self):
        from lpf.optimizers.hybrid import hybrid_minimize

        def multiple_runs(*args, **kwargs):
            from lpf.optimizers.hybrid import LocalRun
            callback = kwargs['local_run_callback']
            callback(LocalRun([], None, None, None, False, None, 'interrupted', 0, 0))
            callback(LocalRun([], None, None, None, False, None, 'interrupted', 0, 0))
            return hybrid_minimize(*args, **kwargs)

        with tempfile.TemporaryDirectory(prefix='issue461-callback-') as tmp, \
             patch('lpf.search._development_worker.hybrid_minimize', side_effect=multiple_runs):
            out = Path(tmp)/'run'
            runner.run(self.cfg, self.starts, out, root=ROOT, spot_checks={'terminal': [0, 57]},
                       search_bounds=None, checkpoint_interval=1)
            result = json.loads((out/'job-0001/result.json').read_text())
            step = result['steps'][0]
            self.assertEqual(step['local_runs'], 3)
            self.assertEqual(sum(r['nfev'] for r in step['local_run_details']), step['forward_count'])
            self.assertIsNone(step['local_run_details'][0]['status'])
            self.assertFalse(step['local_run_details'][0]['success'])

    def test_generic_alias_and_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix='issue458-registry-') as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT/'rf', root/'rf')
            rp = root/'rf/constraints/registry.json'
            original = json.loads(rp.read_text())
            profile = json.loads((root/'rf/constraints/trial/RF-T010.json').read_text())
            profile['constraint_id'] = 'RF-T011'
            (root/'rf/constraints/trial/RF-T011.json').write_text(json.dumps(profile))
            registry = copy.deepcopy(original)
            entry = copy.deepcopy(registry['minimax_profiles']['RF-T010'])
            entry['file'] = 'rf/constraints/trial/RF-T011.json'
            entry['effective_constraint_sha256'] = constraint_fingerprint(dict(profile=profile,
                base_constraint_sha256=entry['base_constraint_sha256'], bands_sha256=entry['bands_sha256']))
            registry['minimax_profiles']['RF-T011'] = entry
            rp.write_text(json.dumps(registry))
            self.cfg['rf']['constraint_id'] = 'RF-T011'
            with patch('lpf.minimax_profile.ROOT', root):
                plan = self.freeze(root)[0]
            self.assertEqual(plan.data['rf_profile']['constraint_id'], 'RF-T011')
            for change in ('missing_base', 'unapproved_base', 'base_sha', 'profile_sha', 's2p'):
                r = copy.deepcopy(registry)
                if change == 'missing_base': r['minimax_profiles']['RF-T011']['base_physical_constraint_id'] = 'RF-T999'
                if change == 'unapproved_base':
                    r['trial']['RF-T008']['state'] = 'proposed'
                    trial = root/'rf/constraints/trial/RF-T008.json'
                    t = json.loads(trial.read_text()); t['study_authorized'] = False; trial.write_text(json.dumps(t))
                if change == 'base_sha': r['minimax_profiles']['RF-T011']['base_constraint_sha256'] = '0'*64
                if change == 'profile_sha': r['minimax_profiles']['RF-T011']['effective_constraint_sha256'] = '0'*64
                if change == 's2p':
                    s2p = root/profile['external_s2p']['input']['path']
                    s2p.write_bytes(s2p.read_bytes()+b'\n')
                rp.write_text(json.dumps(r))
                with self.subTest(change=change), self.assertRaises(ValueError):
                    load_minimax_profile('RF-T011', allow_trial=True, root=root)
                if change == 'unapproved_base': shutil.copy2(ROOT/'rf/constraints/trial/RF-T008.json', trial)
            for rf in ({'constraint_id':'RF-T010'}, {'constraint_id':'RF-T008', 'allow_trial':True},
                       {'constraint_id':'RF-T010', 'allow_trial':True, 'extra':1}):
                self.cfg['rf'] = rf
                with self.assertRaises(ValueError): self.freeze()


if __name__ == '__main__': unittest.main()
