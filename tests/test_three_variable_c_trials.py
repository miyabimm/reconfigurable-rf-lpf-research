"""Current three-C trials stay opt-in; retired trials remain read-only evidence."""
import json
import unittest
from pathlib import Path
from src.lpf.constraint_versions import constraint_fingerprint, load_constraint, validate_registry, validate_variable_c_connections
from src.lpf.constraints import check_counts
from src.lpf.experiment_manifest import new_manifest, validate_manifest

ROOT = Path(__file__).resolve().parents[1]


class TrialThreeVariableCTests(unittest.TestCase):
    def test_registered_trial_scopes_and_formal_immutability(self):
        registry = validate_registry()
        self.assertEqual(registry['active_formal_id'], 'RF-F003')
        self.assertEqual(set(registry['trial']), {'RF-T005','RF-T006','RF-T007','RF-T008'})
        base = load_constraint()
        self.assertEqual(base, json.loads((ROOT/'rf/constraints/formal/RF-F003.json').read_text()))
        self.assertEqual(base['components']['IC_VARIABLE_C']['max_branches_principle'], 2)
        self.assertFalse(check_counts(n_var=3))
        trials = [load_constraint(cid, allow_trial=True) for cid in ('RF-T005','RF-T007')]
        for trial in trials:
            self.assertEqual(trial['active_constraint_status'], 'trial')
            self.assertEqual(trial['trial_base_constraint_id'], 'RF-F003')
            self.assertEqual(trial['components']['IC_VARIABLE_C']['q'], 35)
            self.assertEqual(trial['components']['IC_VARIABLE_C']['max_branches_principle'], 3)
            for key in ('evaluation','area_budget','coupling_limits','phase3'):
                self.assertEqual(trial[key], base[key])
            self.assertNotEqual(constraint_fingerprint(trial), constraint_fingerprint(base))
        self.assertNotEqual(constraint_fingerprint(trials[0]), constraint_fingerprint(trials[1]))
        archive = ROOT/'rf/constraints/history/pre-issue-307/trial'
        shapes = [json.loads((archive/f'{cid}.json').read_text())['study_variable_c_layout'] for cid in ('RF-T001','RF-T002')]
        self.assertEqual([(s['shunt_to_ground'],s['non_ground_bridge']) for s in shapes], [(3,0),(2,1)])

    def test_explicit_opt_in_is_required(self):
        for cid in ('RF-T005','RF-T007'):
            with self.subTest(cid=cid), self.assertRaises(ValueError): load_constraint(cid)
        for cid in ('RF-T001','RF-T002','RF-T003','RF-T004'):
            with self.subTest(retired=cid), self.assertRaises(ValueError): load_constraint(cid, allow_trial=True)
        self.assertEqual(load_constraint()['active_constraint_status'], 'formal')

    def test_connection_layout_up_to_three(self):
        formal = load_constraint()
        shunts = [{'a': 1,'b': 0}, {'a': 3,'b': 0}, {'a': 2,'b': 0}]
        mixed = shunts[:2] + [{'a': 3,'b': 4,'role': 'bridge'}]
        self.assertTrue(validate_variable_c_connections(shunts[:2], formal))
        for branches in (shunts, mixed):
            with self.assertRaises(ValueError): validate_variable_c_connections(branches, formal)
        for cid in ('RF-T005','RF-T007'):
            trial = load_constraint(cid, allow_trial=True)
            for branches in (shunts[:2], shunts, mixed):
                self.assertTrue(validate_variable_c_connections(branches, trial))
            with self.assertRaises(ValueError): validate_variable_c_connections(shunts + shunts[:1], trial)
            with self.assertRaises(ValueError): validate_variable_c_connections(shunts[:2] + [{'a': 3,'b': 4}], trial)

    def test_trial_manifests_are_distinct_and_not_run(self):
        for cid in ('RF-T001','RF-T002'):
            with self.subTest(retired=cid), self.assertRaises(ValueError):
                new_manifest('EXP-016', 'metadata-only test', {}, objective='full_lpf', seed=23, constraint_id=cid, allow_trial=True)
        for cid in ('RF-T005','RF-T007'):
            with self.subTest(cid=cid):
                with self.assertRaises(ValueError):
                    new_manifest('EXP-016', 'metadata-only test', {}, objective='full_lpf', seed=23, constraint_id=cid)
                trial = new_manifest('EXP-016', 'metadata-only test', {}, objective='full_lpf', seed=23, constraint_id=cid, allow_trial=True)
                validate_manifest(trial)
                self.assertEqual(trial['execution']['status'], 'planned')
                self.assertEqual(trial['validation']['independent'], 'not_run')
                self.assertEqual(trial['constraints']['class'], 'trial')


if __name__ == '__main__': unittest.main()
