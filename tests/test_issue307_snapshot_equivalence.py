"""One-off frozen contract comparison; never used as a runtime old-JSON parser."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'rf/constraints'
OLD = ROOT / 'history/pre-issue-307'


def read(root, path): return json.loads((root/path).read_text())


class SnapshotEquivalenceTests(unittest.TestCase):
    def test_only_approved_representation_and_lower_limits_changed(self):
        expected = read(OLD, 'formal/RF-F003.json')
        expected['schema_version'] = 2
        c = expected['components']
        def move_bounds(spec, low_key, high_key, unit, new_low=None):
            lo = spec.pop(low_key) if low_key else new_low
            hi = spec.pop(high_key)
            spec['bounds'] = {'min': lo, 'max': hi, 'unit': unit}
        for spec in c['LQP02']['series'].values():
            move_bounds(spec, 'min_inductance_nH', 'max_inductance_nH', 'nH')
        move_bounds(c['GJM01'], None, 'max_pf_per_component', 'pF', .1)
        move_bounds(c['PCB_L'], None, 'max_inductance_nh', 'nH', .01)
        c['PCB_L'].pop('max_inductance_nh_approx')
        move_bounds(c['PCB_PATTERN_C'], 'min_pf_per_component', 'max_pf_per_component', 'pF')
        move_bounds(c['IC_VARIABLE_C'], 'min_total_variable_pf_per_branch', 'max_total_variable_pf_per_branch', 'pF')
        for name in ('LQP01', 'LQW04'): c[name]['search_supported'] = False
        k = expected['coupling_limits']
        k['bounds'] = {name: {'min': -v, 'max': v, 'unit': '1'} for name, v in (
            ('chip_neighbor', .1), ('chip_nonstrong_sensitivity', .03),
            ('chip_nonstrong_nominal', 0), ('pcb_pcb', .1), ('chip_pcb', 0))}
        e = expected['evaluation']
        full = e.pop('full_phase2')
        matching = e.pop('matching_only_phase2')
        self.assertFalse(matching['h2_h3_constraints'])
        self.assertEqual(matching['minimize'], 'worst_case_IL_over_six_settings_and_all_UL_DL_ranges')
        e['performance'] = {
            'objective': {'metric': 'il_db', 'selector': {'type': 'pass'}, 'aggregation': 'worst', 'direction': 'minimize'},
            'modes': {'full_lpf': {'excluded_regions': []}, 'matching_only': {'excluded_regions': ['H2','H3']}},
            'limits': {'defaults': [
                {'metric': 'attenuation_db', 'selector': {'region': region}, 'min_db': full[key], 'level': level}
                for level,key in (('mandatory','minimum_h2_h3_db'),('nominal','nominal_h2_h3_target_db'))
                for region in ('H2','H3')
            ] + [{'metric':'il_db','selector':{'type':'pass'},'max_db':full['nominal_max_il_db'],'level':'nominal'}], 'overrides': []},
            'margins': [], 'additional_stopbands': []}
        self.assertEqual(read(ROOT, 'formal/RF-F003.json'), expected)
        for cid in ('RF-T005','RF-T006','RF-T007','RF-T008'):
            expected = read(OLD, f'trial/{cid}.json')
            expected['schema_version'] = 2
            if cid == 'RF-T006':
                expected['overrides']['evaluation'] = {'performance': {
                    'additional_stopbands': [expected.pop('study_additional_stopband')]}}
            for key in ('study_pcb_pattern_c_by_connection', 'study_ic_fixed_c_by_connection'):
                if key in expected:
                    suffix = 'per_component' if 'pcb' in key else 'per_branch'
                    for position in ('grounded','non_ground'):
                        move_bounds(expected[key][position], 'min_pf_'+suffix, 'max_pf_'+suffix, 'pF')
            self.assertEqual(read(ROOT, f'trial/{cid}.json'), expected, cid)


if __name__ == '__main__': unittest.main()
