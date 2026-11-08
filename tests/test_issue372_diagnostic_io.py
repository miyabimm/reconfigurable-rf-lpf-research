"""Diagnostic reporting schema only; no RF or production runs."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
spec = importlib.util.spec_from_file_location('issue372_diagnose_window', ROOT / 'project/diagnostics/issue372/diagnose_window.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class DiagnosticIOSchemaTests(unittest.TestCase):
    def test_legacy_has_no_fake_zero_io(self):
        self.assertEqual(module.io_record('legacy', {}), {'status': 'not_applicable'})
        with self.assertRaises(ValueError):
            module.io_record('legacy', {'io': {}})

    def test_window_requires_complete_nonzero_readback(self):
        with self.assertRaises(ValueError):
            module.io_record('window100', {})
        section = dict(atomic_writes=1, payload_bytes=10, atomic_readbacks=1, readback_bytes=10)
        good = {'complete_worker_accounting': True, **{k: dict(section) for k in ('parent', 'worker', 'summary')}}
        self.assertEqual(module.io_record('window100', {'io': good}), good)
        good['worker']['readback_bytes'] = 9
        with self.assertRaises(ValueError):
            module.io_record('window100', {'io': good})
        good['worker']['readback_bytes'] = 10
        good['complete_worker_accounting'] = False
        with self.assertRaises(ValueError):
            module.io_record('window100', {'io': good})

if __name__ == '__main__':
    unittest.main()
