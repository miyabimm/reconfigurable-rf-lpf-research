"""Retired F001/F002/T004 evidence is preserved, never executable as current RF."""
import json
import unittest
from pathlib import Path
from src.lpf.constraint_versions import constraint_fingerprint, load_constraint, validate_registry, validate_variable_c_connections
from src.lpf.constraint_history import archived_formal_evidence, archived_binding
from src.lpf.constraints import check_counts

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT/'rf/constraints/history/pre-issue-307'


class RevisedRFConstraintsTests(unittest.TestCase):
    def test_formal_identity_hash_and_components(self):
        reg = validate_registry()
        self.assertIn('RF-F003', reg['formal'])
        self.assertNotIn('RF-F002', reg['formal'])
        digest = 'f20d27e93451dcec2f823e6f7c3731c06d843050c4d2ace8b0b46ded605542e2'
        current = archived_formal_evidence('RF-F002', digest, root=ROOT)
        self.assertEqual(constraint_fingerprint(current), digest)
        self.assertEqual(load_constraint('RF-F003'), json.loads((ROOT/'rf/constraints/formal/RF-F003.json').read_text()))
        self.assertEqual(current['components']['IC_VARIABLE_C']['q'], 50)
        self.assertEqual(current['components']['IC_VARIABLE_C']['max_total_variable_pf_per_branch'], 1.5)
        self.assertEqual(current['components']['IC_VARIABLE_C']['max_branches_principle'], 2)
        self.assertEqual(current['components']['IC_VARIABLE_C']['positions_allowed_by_default'],
                         ['shunt_to_ground', 'non_ground_bridge', 'series'])
        self.assertFalse(current['components']['IC_VARIABLE_C']['series_requires_separate_approval'])
        self.assertEqual(current['components']['LQW04']['q'], 33)
        self.assertEqual(current['components']['PCB_L']['max_inductance_nh'], 2)
        for name, expected in (('chip_chip_strong_adjacent_abs_k_max', .15),
                               ('chip_chip_nonstrong_abs_k_max', .03),
                               ('chip_chip_nonstrong_nominal_k', 0),
                               ('pcb_pcb_abs_k_max_default', .15), ('chip_pcb_abs_k_max', 0)):
            self.assertEqual(current['coupling_limits'][name], expected)
        with self.assertRaises(ValueError): load_constraint('RF-F002', allow_trial=True)

    def test_legacy_f001_is_intact(self):
        old = archived_formal_evidence('RF-F001', None, root=ROOT)
        self.assertEqual(old['coupling_limits']['chip_chip_strong_adjacent_abs_k_max'], .4)
        self.assertEqual(old['components']['IC_VARIABLE_C']['q'], 80)
        self.assertEqual(old['components']['IC_VARIABLE_C']['max_total_variable_pf_per_branch'], 4)
        self.assertEqual(old['components']['IC_VARIABLE_C']['positions_allowed_by_default'], ['shunt_to_ground'])
        with self.assertRaises(ValueError): load_constraint('RF-F001', allow_trial=True)

    def test_connections_formal_and_trial(self):
        trial_evidence = json.loads((ARCHIVE/'trial/RF-T004.json').read_text())
        metadata = json.loads((ARCHIVE/'provenance.json').read_text())
        digest = metadata['resolved_effective_sha256']['RF-T004']
        self.assertEqual(archived_binding('RF-T004', digest, root=ROOT),
                         {'class': 'trial', 'base_constraint_id': 'RF-F002'})
        self.assertEqual(trial_evidence['study_variable_c_layout'],
                         {'branch_count': 3, 'count_policy': 'up_to', 'connection_policy': 'any_allowed'})
        self.assertEqual(trial_evidence['overrides']['components']['IC_VARIABLE_C']['max_branches_principle'], 3)
        for opt_in in (False, True):
            with self.assertRaises(ValueError): load_constraint('RF-T004', allow_trial=opt_in)
        # Exercise current connection invariants with current RF only.
        formal = load_constraint('RF-F003')
        trial = load_constraint('RF-T005', allow_trial=True)
        self.assertFalse(check_counts(n_var=3, resolved_policy=formal))
        self.assertTrue(check_counts(n_var=3, resolved_policy=trial))
        self.assertFalse(check_counts(n_var=4, resolved_policy=trial))
        shunt, bridge, series = {'a': 1, 'b': 0}, {'a': 1, 'b': 2, 'role': 'bridge'}, {'a': 2, 'b': 3, 'role': 'series'}
        for branches in ([shunt, bridge], [shunt, series], [bridge, series]):
            self.assertTrue(validate_variable_c_connections(branches, formal))
            self.assertTrue(validate_variable_c_connections(branches, trial))
        for branches in ([shunt, bridge, series], [series]*3):
            self.assertTrue(validate_variable_c_connections(branches, trial))
            with self.assertRaises(ValueError): validate_variable_c_connections(branches, formal)
        for branches in ([{'a': 1, 'b': 2}], [shunt]*4):
            with self.assertRaises(ValueError): validate_variable_c_connections(branches, trial)


if __name__ == '__main__': unittest.main()
