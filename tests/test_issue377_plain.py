"""Regression coverage for checkpoint conversion; no RF evaluations."""
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.search.evaluation import raw_numbers
from lpf.search.storage import canonical, plain


def previous_plain(value):
    if is_dataclass(value):
        return previous_plain(asdict(value))
    if isinstance(value, dict):
        return {k: previous_plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list, np.ndarray)):
        return [previous_plain(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


@dataclass
class Nested:
    values: object


class ScalarSubclass(float):
    pass


class PlainConversionTests(unittest.TestCase):
    def test_nested_checkpoint_numbers_and_special_types_match_previous(self):
        samples = [
            {'nested': [Nested((np.float64(2.5), np.int64(3), True, None)),
                        np.array([1., np.inf, -np.inf, np.nan]),
                        complex(2., -3.), ScalarSubclass(1.5)]},
            np.array([[1, 2], [3, 4]]),
            (np.complex128(complex(1., 2.)), {'x': float('inf')}),
            np.array((1, 2.5), dtype=[('a', 'i4'), ('b', 'f8')])[()],
        ]
        for value in samples:
            with self.subTest(value=repr(value)):
                # Compare the complete raw encoding, including nonfinite values.
                with patch('lpf.search.evaluation.plain', previous_plain):
                    expected = raw_numbers(value)
                self.assertEqual(canonical(raw_numbers(value)), canonical(expected))
        scalar = ScalarSubclass(1.5)
        self.assertIs(plain(scalar), scalar)


if __name__ == '__main__':
    unittest.main()
