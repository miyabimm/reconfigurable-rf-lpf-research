"""Issue 450: bounded deterministic tests; no search or scientific EXP."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from lpf.constraint_versions import constraint_fingerprint, load_constraint
from lpf.minimax_profile import load_minimax_profile, signed_margins
from lpf.rf_core import EvaluationGrid
from lpf.rf_core.model import RFResponse
from lpf.rf_core.independent import validate_response
from lpf.rf_core._grid import validated_band_segments
from test_issue307_constraints import make

def grid(profile):
    segments = validated_band_segments(profile.records)
    return EvaluationGrid([v*1e6 for _, _, lo, hi in segments for v in (lo, hi)],
                          [s for s, _, _, _ in segments for _ in range(2)],
                          [i for i in range(28) for _ in range(2)])


def response(profile, g, offset=-.2):
    il = np.array([(0.8 + offset if profile.records[i]['type'] == 'pass' else 30 - offset)
                   for i in g.segment])
    s = np.zeros((len(il), 2, 2), complex)
    s[:, 1, 0] = 10**(-il/20)
    return RFResponse(g, 'RF-T009', profile.fingerprint, s, il, il, il, il)


class MinimaxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = load_minimax_profile('RF-T009', allow_trial=True)

    def test_identity_inputs_and_legacy(self):
        with self.assertRaises(ValueError): load_minimax_profile('RF-T009')
        with self.assertRaises(ValueError): load_constraint('RF-T009', allow_trial=True)
        old = load_constraint('RF-F003')
        new = self.p.profile
        self.assertEqual(new['source_ohms'], old['source_ohms'])
        self.assertEqual(new['load_ohms'], {k: old['load_ohms'][k] for k in ('real', 'imag')})
        for name in ('input', 'output'):
            a, b = new['external_s2p'][name], old['external_port_parasitics'][name+'_parasitic']
            self.assertEqual(a['sha256'], b['sha256'])
            self.assertEqual(a['path'], b['path'].replace('data/', 'rf/'))
        self.assertEqual(self.p.base_sha256, 'e12c42b11d12db7f20983c48cfa441ea96e362e533450d5862aa8a271c82af86')
        self.assertEqual(self.p.fingerprint, 'd1ebefaf4cb6735898467b9c2affcc57b9590d4a6c9f53a0dd84d1f1f2f8b18d')
        self.assertEqual(new['kind'], 'rf_performance_profile')
        self.assertNotIn('objective', new)
        self.assertEqual(len(new['limits_db']), 7)
        for limits in new['limits_db'].values():
            self.assertEqual(limits, dict(ul_il_max=0.8, dl_il_max=0.8, h2_atten_min=30, h3_atten_min=30))
        for cid in ('RF-T005', 'RF-T006', 'RF-T007', 'RF-T008'):
            self.assertEqual(load_constraint(cid, allow_trial=True)['active_constraint_id'], cid)

    def test_every_band_region_independent_and_shared_setting(self):
        p = self.p
        g = grid(p)
        r = response(p, g)
        _, baseline = signed_margins(p, g, r)
        keys = {'UL':'ul_il_max', 'DL':'dl_il_max', 'H2':'h2_atten_min', 'H3':'h3_atten_min'}
        with tempfile.TemporaryDirectory(prefix='issue450-limits-') as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT/'rf', root/'rf')
            path = root/'rf/constraints/trial/RF-T009.json'
            registry_path = root/'rf/constraints/registry.json'
            registry = json.loads(registry_path.read_text())
            entry = registry['minimax_profiles']['RF-T009']
            for i, row in enumerate(p.records):
                data = p.profile
                band = row['note'] or row['case']
                data['limits_db'][band][keys[row['region']]] += 1
                path.write_text(json.dumps(data))
                entry['effective_constraint_sha256'] = constraint_fingerprint({
                    'profile': data, 'base_constraint_sha256': p.base_sha256, 'bands_sha256': p.bands_sha256})
                registry_path.write_text(json.dumps(registry))
                changed = load_minimax_profile('RF-T009', allow_trial=True, root=root)
                _, margins = signed_margins(changed, g, replace(r, policy_fingerprint=changed.fingerprint))
                delta = margins - baseline
                expected = np.where(g.segment == i, -1 if row['type'] == 'pass' else 1, 0)
                np.testing.assert_allclose(delta, expected, atol=1e-12)
        self.assertEqual(set(g.setting[np.isin(g.segment, [12, 13, 14, 15, 16, 17, 18, 19])]), {3})

    def test_score_sign_boundary_max_and_invalid_grids(self):
        g = grid(self.p)
        for v in (-.5, 0., 1.):
            j, margins = signed_margins(self.p, g, response(self.p, g, v))
            self.assertAlmostEqual(j, v)
            np.testing.assert_allclose(margins, v, atol=1e-14)
        r = response(self.p, g)
        il, s = r.il_db.copy(), r.s.copy()
        il[17] += 2
        s[17, 1, 0] = 10**(-il[17]/20)
        self.assertAlmostEqual(signed_margins(self.p, g, replace(r, il_db=il, s=s))[0], 1.8)
        with self.assertRaises(ValueError): signed_margins(self.p, g, replace(r, il_db=il))
        with self.assertRaises(ValueError): signed_margins(self.p, g, replace(r, policy_id='RF-F003'))
        invalid_s = r.s.copy()
        invalid_s[0, 1, 0] = 2
        with self.assertRaises(ValueError): signed_margins(self.p, g, replace(r, s=invalid_s))
        # Exact zero transmission is a valid +inf dB attenuation, never floored.
        il, s = r.il_db.copy(), r.s.copy()
        il[4], s[4, 1, 0] = np.inf, 0
        self.assertAlmostEqual(signed_margins(self.p, g, replace(r, il_db=il, s=s))[0], -.2)
        il[0], s[0, 1, 0] = np.inf, 0
        self.assertEqual(signed_margins(self.p, g, replace(r, il_db=il, s=s))[0], np.inf)
        for f, st, seg in [(g.frequency_hz[:-1], g.setting[:-1], g.segment[:-1]),
                           (g.frequency_hz+1, g.setting, g.segment),
                           (g.frequency_hz, (g.setting+1)%6, g.segment)]:
            wrong = EvaluationGrid(f, st, seg)
            with self.assertRaises(ValueError): signed_margins(self.p, wrong, r)
            with self.assertRaises(ValueError): signed_margins(self.p, wrong, response(self.p, wrong))

    def test_real_forward_equals_formal_external_cascade(self):
        _, definition, old, _, x = make('RF-F003')
        new = self.p.build_model(definition)
        g = grid(self.p)
        a = old.evaluator(g).evaluate(x)
        b = new.evaluator(g).evaluate(x)
        np.testing.assert_allclose(a.s, b.s, rtol=0, atol=0)
        np.testing.assert_allclose(a.il_db, b.il_db, rtol=0, atol=0)
        j, margins = signed_margins(self.p, g, b)
        self.assertEqual(j, np.max(margins))
        audit = validate_response(new, x, b)
        self.assertEqual(audit['samples_checked'], 56)
        self.assertTrue(audit['independent_mna_checked'])
        self.assertFalse(audit['rf_compliance_certified'])

    def test_fail_closed_profile_inputs(self):
        # Separate disposable RF trees preserve actual registered sources.
        mutations = ('missing', 'missing_band', 'unknown_band', 'unknown', 'nan', 'inf', 'duplicate', 's2p', 'bands', 'range', 'duplicate_row', 'wrong_role', 'unknown_top', 'old_objective')
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory(prefix='issue450-test-') as tmp:
                root = Path(tmp)
                shutil.copytree(ROOT/'rf', root/'rf')
                path = root/'rf/constraints/trial/RF-T009.json'
                data = json.loads(path.read_text())
                if mutation == 'missing': del data['limits_db']['B13']['ul_il_max']
                if mutation == 'missing_band': del data['limits_db']['B13']
                if mutation == 'unknown_band': data['limits_db']['B99'] = data['limits_db']['B13']
                if mutation == 'unknown': data['limits_db']['B71']['override'] = 1
                if mutation == 'nan': data['limits_db']['B71']['ul_il_max'] = float('nan')
                if mutation == 'inf': data['limits_db']['B71']['ul_il_max'] = float('inf')
                if mutation == 's2p': data['external_s2p']['input']['sha256'] = '0'*64
                if mutation == 'wrong_role': data['external_s2p']['input']['port_flip'] = True
                if mutation == 'unknown_top': data['default'] = 1
                if mutation == 'old_objective': data['objective'] = 'minimax_signed_margin_db'
                path.write_text(json.dumps(data))
                if mutation == 'duplicate': path.write_text(path.read_text().replace('"kind":', '"kind": "rf_performance_profile", "kind":'))
                if mutation in ('bands', 'range', 'duplicate_row'):
                    bp = root/'rf/bands.csv'
                    text = bp.read_text()
                    if mutation == 'duplicate_row':
                        lines = text.splitlines()
                        lines[2] = lines[1]
                        text = '\n'.join(lines) + '\n'
                    else:
                        text = text.replace('663,698', '663,699' if mutation == 'bands' else '663,7000')
                    bp.write_text(text)
                    if mutation != 'bands':
                        # Make the bands hash consistent so semantic/range checks execute.
                        rp = root/'rf/constraints/registry.json'
                        registry = json.loads(rp.read_text())
                        registry['minimax_profiles']['RF-T009']['bands_sha256'] = hashlib.sha256(bp.read_bytes()).hexdigest()
                        rp.write_text(json.dumps(registry))
                with self.assertRaises(ValueError): load_minimax_profile('RF-T009', allow_trial=True, root=root)


if __name__ == '__main__': unittest.main()
