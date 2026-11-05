"""Verify the byte-preserving pre-migration RF constraint archive."""
import hashlib
import json
from pathlib import Path
import copy
import unittest


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'rf/constraints/history/pre-issue-307'


class HistoricalConstraintArchiveTests(unittest.TestCase):
    def test_original_bytes_parents_and_effective_fingerprints(self):
        metadata = json.loads((ARCHIVE / 'provenance.json').read_text())
        self.assertEqual(metadata['source_main_commit'], 'e1a1c883d449a9378eb9bf2e20c01d5e972afadd')
        expected = metadata['snapshot_file_sha256']
        files = {str(p.relative_to(ARCHIVE)) for p in ARCHIVE.rglob('*.json')
                 if p.name != 'provenance.json'}
        self.assertEqual(files, set(expected))
        for name, digest in expected.items():
            self.assertEqual(hashlib.sha256((ARCHIVE / name).read_bytes()).hexdigest(), digest, name)
        registry = json.loads((ARCHIVE / 'registry.json').read_text())
        self.assertEqual(registry['active_formal_id'], 'RF-F003')
        self.assertEqual({i: e['base_constraint_id'] for i, e in registry['trial'].items()},
                         metadata['trial_base_ids'])
        self.assertEqual(set(metadata['resolved_effective_sha256']),
                         set(registry['formal']) | set(registry['trial']))
        def merge(base, overrides):
            result = copy.deepcopy(base)
            for key, value in overrides.items():
                result[key] = merge(result[key], value) if isinstance(value, dict) else value
            return result
        for cid, fingerprint in metadata['resolved_effective_sha256'].items():
            with self.subTest(cid=cid):
                if cid in registry['formal']:
                    policy = json.loads((ARCHIVE / 'formal' / f'{cid}.json').read_text())
                else:
                    trial = json.loads((ARCHIVE / 'trial' / f'{cid}.json').read_text())
                    base = json.loads((ARCHIVE / 'formal' / f"{trial['base_constraint_id']}.json").read_text())
                    policy = merge(base, trial['overrides'])
                    policy.update(active_constraint_id=cid, active_constraint_status='trial',
                                  trial_base_constraint_id=trial['base_constraint_id'],
                                  trial_variable_c_layout=trial['study_variable_c_layout'])
                    for name in ('additional_stopband', 'shunt_dtc_parasitic',
                                 'pcb_pattern_c_by_connection', 'ic_fixed_c_by_connection'):
                        if f'study_{name}' in trial:
                            policy[f'trial_{name}'] = trial[f'study_{name}']
                encoded = json.dumps(policy, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode('utf-8')
                self.assertEqual(hashlib.sha256(encoded).hexdigest(), fingerprint)


if __name__ == '__main__':
    unittest.main()
