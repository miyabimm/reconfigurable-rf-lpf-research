"""Evaluator prepares the unchanged frozen source/load once, not per forward."""
import json
import unittest
from dataclasses import FrozenInstanceError, replace
from unittest.mock import PropertyMock, patch

import numpy as np
from test_issue307_constraints import make
from lpf.rf_core.model import EvaluationGrid
from lpf.rf_core.coupled_lc import _fixed_port_impedance


class PreparedPortTests(unittest.TestCase):
    def test_all_models_settings_response_and_frozen_impedances(self):
        grid = EvaluationGrid(np.linspace(1e9, 2e9, 6), np.arange(6), np.arange(6))
        for cid in ('RF-F003', 'RF-T005', 'RF-T006', 'RF-T007', 'RF-T008'):
            with self.subTest(cid=cid):
                policy, _, model, _, vector = make(cid)
                evaluator = model.evaluator(grid)
                self.assertEqual(evaluator.source_ohms, _fixed_port_impedance(policy, 'source_ohms'))
                self.assertEqual(evaluator.load_ohms, _fixed_port_impedance(policy, 'load_ohms'))
                with self.assertRaises(FrozenInstanceError):
                    evaluator.source_ohms = 1
                expected = evaluator.evaluate(vector)
                with patch.object(type(model), 'resolved_policy', new_callable=PropertyMock,
                                  side_effect=AssertionError('policy decoded during forward')):
                    actual = evaluator.evaluate(vector)
                for name in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
                    np.testing.assert_array_equal(getattr(actual, name), getattr(expected, name))

    def test_invalid_fixed_impedance_stops_when_preparing_evaluator(self):
        policy, _, model, _, _ = make('RF-T008')
        grid = EvaluationGrid(np.array([1e9]), np.array([0]), np.array([0]))
        for key, invalid in (('source_ohms', {'real': 0, 'imag': 0}),
                             ('load_ohms', {'real': 50, 'imag': 0, 'frequency_dependent': True})):
            with self.subTest(key=key):
                changed = dict(policy, **{key: invalid})
                bad = replace(model, policy_json=json.dumps(changed))
                with self.assertRaisesRegex(ValueError, key):
                    bad.evaluator(grid)


if __name__ == '__main__':
    unittest.main()
