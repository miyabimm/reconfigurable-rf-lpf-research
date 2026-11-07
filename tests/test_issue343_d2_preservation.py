"""G3/G4 post-search guard regression without retired runners or RF evaluation."""
import copy
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.checkpoint_io import canonical_config_hash
from lpf.experiment_manifest import INDEX_FIELDS
from lpf.experiment_preservation import _post_search_finalize_guard, aggregate_selected


class PreservationGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='issue343-d2-guard-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(self.root)], check=True)
        for key, value in [('user.name', 'Test'), ('user.email', 'test@example.com')]:
            subprocess.run(['git', '-C', str(self.root), 'config', key, value], check=True)
        self.index = self.root / 'data/experiment_index.csv'
        self.index.parent.mkdir()
        self.row = dict.fromkeys(INDEX_FIELDS, '')
        self.row['experiment_id'] = 'EXP-999'
        self.write_index(self.row)
        subprocess.run(['git', '-C', str(self.root), 'add', 'data/experiment_index.csv'], check=True)
        subprocess.run(['git', '-C', str(self.root), 'commit', '-qm', 'index'], check=True)
        self.run = self.root / 'experiments/EXP-999'
        self.run.mkdir(parents=True)
        report = {'schema': 'post-search-validation-1', 'component': {'state': 'pass'},
                  'separate17': {'state': 'pass'}, 'dense1001': {'state': 'pass'},
                  'independent84': {'state': 'pass'}}
        self.selection = {'targets': [{'candidate_id': 'a'}]}
        selection_sha = canonical_config_hash(self.selection)
        self.validation = aggregate_selected(['a'], {'a': report})
        selection_ref = self.write_ref('selection.json', self.selection)
        self.overlay = {'candidate_id': 'a', 'selection_sha256': selection_sha,
                        'execution_state': 'completed', 'validation': self.validation['candidates']['a'],
                        'report': report}
        overlay_ref = self.write_ref('overlay.json', self.overlay)
        self.storage = {'validation_overlays': [selection_ref, overlay_ref]}
        self.manifest = {'experiment_id': 'EXP-999', 'search_scope': {'post_search_validation': {}},
                         'validation': self.validation['validation'], 'execution': {'status': 'complete'}}
        self.summary = {'post_search': {'execution_state': 'complete', 'selection_sha256': selection_sha,
                        'selection': selection_ref, 'overlays': {'a': overlay_ref},
                        'candidates': self.validation['candidates'], 'validation': self.validation['validation']}}
        receipt = self.root / 'results/EXP-999/post-search/packaging.json'
        receipt.parent.mkdir(parents=True)
        receipt.write_text(json.dumps({'state': 'packaged', 'preservation': 'awaiting_git_readback',
                                       'selection_sha256': selection_sha}))
        self.row.update(execution_status='complete', numerical_validation='passed', independent_validation='passed')
        self.write_index(self.row)

    def write_index(self, row):
        with self.index.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=INDEX_FIELDS)
            writer.writeheader()
            writer.writerow(row)

    def write_ref(self, name, data):
        path = self.run / name
        raw = json.dumps(data).encode()
        path.write_bytes(raw)
        return {'path': path.relative_to(self.root).as_posix(), 'sha256': hashlib.sha256(raw).hexdigest()}

    def guard(self):
        return _post_search_finalize_guard(self.root, self.run, self.manifest, self.storage, self.summary)

    def test_frozen_candidate_set_and_authenticated_overlay(self):
        self.assertEqual(self.guard(), self.index)
        self.summary['post_search']['candidates']['extra'] = {'numerical': 'passed', 'independent': 'passed'}
        with self.assertRaisesRegex(ValueError, 'candidate set'):
            self.guard()
        del self.summary['post_search']['candidates']['extra']
        (self.run / 'overlay.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'SHA mismatch'):
            self.guard()

    def test_incomplete_receipt_status_and_unrelated_index_fail_closed(self):
        self.summary['post_search']['execution_state'] = 'running'
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            self.guard()
        self.summary['post_search']['execution_state'] = 'complete'
        self.manifest['validation'] = {'numerical': 'failed', 'independent': 'not_run'}
        with self.assertRaisesRegex(ValueError, 'status mismatch'):
            self.guard()
        self.manifest['validation'] = copy.deepcopy(self.validation['validation'])
        self.row['experiment_id'] = 'EXP-998'
        self.write_index(self.row)
        with self.assertRaises(ValueError):
            self.guard()

    def test_missing_failed_and_unexpected_candidates(self):
        incomplete = {'schema': 'post-search-validation-1', 'component': {'state': 'fail'}}
        self.assertEqual(aggregate_selected(['a', 'b'], {'a': incomplete})['validation'],
                         {'numerical': 'failed', 'independent': 'not_run'})
        self.assertEqual(aggregate_selected(['a'], {})['validation'],
                         {'numerical': 'not_run', 'independent': 'not_run'})
        with self.assertRaises(ValueError):
            aggregate_selected(['a'], {'b': incomplete})


if __name__ == '__main__':
    unittest.main()
