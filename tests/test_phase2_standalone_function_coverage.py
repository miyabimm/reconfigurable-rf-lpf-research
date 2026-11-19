"""Run the historical Phase-2 theory function tests via manual unittest discovery.

The six theory modules use pytest-style top-level functions that unittest
discovery does not execute directly. This bridge executes them when explicitly
selected; normal CI uses the scoped selector and does not invoke this module.
"""
import importlib.util
import inspect
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
THEORY_MODULES = (
    "test_pi_zero_retarget.py",
    "test_t_coupled_geometry.py",
    "test_t_coupled_modal_theory.py",
    "test_t_matched_shunt_high_current.py",
    "test_t_shunt_high_current.py",
    "test_t_two_coupling_models.py",
)


class Phase2TheoryStandaloneFunctions(unittest.TestCase):
    def test_each_theory_module_runs_its_top_level_tests(self):
        total = 0
        for filename in THEORY_MODULES:
            path = TESTS / filename
            self.assertTrue(path.is_file(), f"Missing theory module: {filename}")
            spec = importlib.util.spec_from_file_location(
                f"ci_phase2_{path.stem}", path
            )
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            cases = [
                (name, fn)
                for name, fn in inspect.getmembers(module, inspect.isfunction)
                if name.startswith("test_") and fn.__module__ == module.__name__
            ]
            self.assertGreater(len(cases), 0, f"No test functions in {filename}")
            total += len(cases)
            for name, fn in cases:
                with self.subTest(module=filename, case=name):
                    fn()
        self.assertGreaterEqual(total, 15)


if __name__ == "__main__":
    unittest.main()
