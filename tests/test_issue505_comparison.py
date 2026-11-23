"""Selection and wall-censoring contracts for the Issue 505 diagnostic."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1]/'project/diagnostics/issue505/compare.py'
spec = importlib.util.spec_from_file_location('issue505', path)
compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare)

class ComparisonTests(unittest.TestCase):
    def test_no_future_first_tie_and_missing(self):
        events = [dict(elapsed_s=1., objective=2., sequence=1),
                  dict(elapsed_s=2., objective=2., sequence=2),
                  dict(elapsed_s=5.001, objective=0., sequence=3)]
        self.assertIsNone(compare.select(events, .9))
        self.assertEqual(compare.select(events, 5)['sequence'], 1)
        self.assertEqual(compare.select(events, 20)['sequence'], 3)

    def test_stop_categories(self):
        self.assertEqual(compare.classify('converged', 2, 5), 'early_convergence_hold')
        self.assertEqual(compare.classify('evaluation_limit', 2, 5), 'budget_censored')
        self.assertEqual(compare.classify('evaluation_budget_exhausted', 2, 5), 'budget_censored')
        self.assertEqual(compare.classify('converged', 6, 5), 'observed')
        self.assertEqual(compare.classify('solver_failure', 2, 5), 'early_other_stop')
        self.assertEqual(compare.classify(None, 2, 5, 'RF error'), 'rf_or_execution_stop')

if __name__ == '__main__':
    unittest.main()
