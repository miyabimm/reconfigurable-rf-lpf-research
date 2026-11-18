"""Independent external checkout/source checks, without Campaign or RF forwards."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from lpf.constraint_versions import constraint_fingerprint, load_constraint, rf_input_file
from lpf.search import checkout
from lpf.search.plan import ROOT


class CheckoutTests(unittest.TestCase):
    def test_standalone_complete_fresh_clean_and_rf_identity(self):
        with tempfile.TemporaryDirectory(prefix='issue448-checkout-') as temp:
            base = Path(temp)
            root = base/'root'
            root.mkdir()
            def git(*args, **kwargs):
                return subprocess.check_output(['git', *args], cwd=root, **kwargs)
            git('init', '-q', '-b', 'main')
            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@example.invalid')
            git('init', '--bare', '-q', str(base/'origin.git'))
            git('remote', 'add', 'origin', str(base/'origin.git'))
            shutil.copytree(ROOT/'rf', root/'rf')
            for name in ('pyproject.toml', 'uv.lock', 'scripts/run_rf_search.py',
                         'src/lpf/__init__.py', 'experiments/fixture',
                         'data/experiment_number_registry.csv', 'data/phase2_git_storage_budget.json'):
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'fixture\n')
            def commit():
                git('add', '.')
                git('commit', '-qm', 'fixture')
            commit()
            git('push', '-q', '-u', 'origin', 'main')
            policy = load_constraint('RF-F003', root=root)
            expected = constraint_fingerprint(policy)
            # The synthetic repository is for filesystem / Git checks, not
            # imported implementation. Real import contamination is tested below.
            with patch.object(checkout, 'verify_import_origins') as imports:
                report = checkout.verify_checkout(root, 'RF-F003', expected)
                imports.assert_called_once_with(root)
                self.assertEqual(report['source']['head'], git('rev-parse', 'HEAD', text=True).strip())
                self.assertEqual(report['effective_sha256'], expected)
                self.assertEqual(len(report['rf_input_sha256']), 3)
                with self.assertRaisesRegex(ValueError, 'effective SHA'):
                    checkout.verify_checkout(root, 'RF-F003', '0'*64)
                git('config', 'core.sparseCheckout', 'true')
                with self.assertRaisesRegex(ValueError, 'sparse checkout'):
                    checkout.verify_checkout(root, 'RF-F003', expected)
                git('config', 'core.sparseCheckout', 'false')
                fixture = root/'experiments/fixture'
                fixture.unlink()
                with self.assertRaisesRegex(ValueError, 'missing tracked evidence'):
                    checkout.verify_checkout(root, 'RF-F003', expected)
                fixture.write_bytes(b'dirty\n')
                with self.assertRaisesRegex(ValueError, 'clean checkout'):
                    checkout.verify_checkout(root, 'RF-F003', expected)
                fixture.write_bytes(b'fixture\n')
                s2p = rf_input_file(root, policy['external_port_parasitics']['input_parasitic']['path'])
                with s2p.open('ab') as stream:
                    stream.write(b'\n! changed\n')
                commit()
                with self.assertRaisesRegex(ValueError, 'S2P SHA'):
                    checkout.verify_checkout(root, 'RF-F003', expected)
                git('push', '-q', 'origin', 'main')
                git('update-ref', 'refs/remotes/origin/main', 'HEAD^')
                with self.assertRaisesRegex(ValueError, 'stale'):
                    checkout.verify_checkout(root, 'RF-F003', expected)

    def test_import_origin_cannot_point_at_other_checkout(self):
        import lpf
        with patch.object(lpf.__spec__, 'origin', '/tmp/other-checkout/src/lpf/__init__.py'):
            with self.assertRaisesRegex(ValueError, 'import origin mismatch: lpf'):
                checkout.verify_import_origins(ROOT)
