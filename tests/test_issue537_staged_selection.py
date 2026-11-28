"""Deterministic staged ranking and reproducibility, with no RF forwards."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.search._staged_selection import rank_candidates, select_discovery, assess_reproducibility


def row(seed, margins, objective=0.1, converged=True, vector=None):
    return dict(seed=seed, terminal_margins=margins, terminal_grid_sha256='grid',
                search_objective=objective, converged=converged, vector=vector or [.5, 2.],
                worst_il_db=1., min_h2_db=20., min_h3_db=30.)


class SelectionTests(unittest.TestCase):
    def test_ranking_and_no_padding(self):
        rows = [row(2, [1., 1.]), row(3, [1., -2.]), row(1, [1., -2.]), row(4, [2., -1.], 0.)]
        self.assertEqual([r['seed'] for r in rank_candidates(rows)], [1, 3, 2, 4])
        self.assertEqual([r['seed'] for r in select_discovery(rows, target_objective=.1,
                                                              terminal_max_margin=1., count=2)], [1, 3])
        self.assertEqual(select_discovery(rows, target_objective=0., terminal_max_margin=1., count=2), [])
        rows[0]['terminal_grid_sha256'] = 'other'
        with self.assertRaises(ValueError):
            rank_candidates(rows)

    def test_reference_must_converge_and_fixed_coordinates_excluded(self):
        tolerances = dict(search_objective=.01, worst_il_db=.1, min_h2_db=.1, min_h3_db=.1)
        rows = [row(1, [0.], vector=[.5, 2.]), row(2, [.1], vector=[.7, 2.])]
        result = assess_reproducibility(rows, [[0., 1.], [2., 2.]], tolerances=tolerances, required_seeds=2)
        self.assertTrue(result['reproducible'])
        self.assertAlmostEqual(result['comparisons'][1]['vector_distance_rms'], .2)
        rows[0]['converged'] = False
        result = assess_reproducibility(rows, [[0., 1.], [2., 2.]], tolerances=tolerances, required_seeds=2)
        self.assertFalse(result['reproducible'])
        self.assertEqual(result['matching_seeds'], [])


if __name__ == '__main__':
    unittest.main()
