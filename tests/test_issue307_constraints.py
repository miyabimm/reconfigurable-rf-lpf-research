"""Stage-1 closed endpoints and archived scientific contract, no optimization."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import sys
import shutil
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from lpf.constraint_versions import load_constraint, constraint_fingerprint, validate_registry
from lpf.phase2_models.api import CircuitDefinition, build_nominal_circuit
from lpf.topology_management.circuit_layout import InductorTree, CapacitorPlacement
from lpf.search.component_constraints import physical_bounds, validate_values, validate_search_box
from lpf.search.performance import validate_performance, harmonic_limit_db, limit_db, additional_stopband
from lpf.phase2_models.problem_seed import circuit_box


def make(cid):
    policy = load_constraint(cid, allow_trial=cid.startswith('RF-T'))
    var = ((0, -1), (0, 2))
    d = CircuitDefinition(InductorTree(8, tuple((i, i+1) for i in range(7))),
        ('LQP02HV', 'LQP02HQ', 'LQP02HV', 'LQP02HV', 'PCB_L', 'PCB_L', 'PCB_L'),
        (0, 1, 2, 3), ((0, 1), (0, 2), (1, 4), (4, 5)),
        CapacitorPlacement(8, ((1, -1), (2, -1), (1, 3)), var,
                           var if cid == 'RF-T008' else ()),
        ('GJM01', 'PCB_PATTERN_C', 'PCB_PATTERN_C'), ('shunt_to_ground', 'bridge'))
    circuit = build_nominal_circuit(policy, d)
    bounds = physical_bounds(d, circuit.schema, policy)
    x = np.mean(bounds, axis=1)
    return policy, d, circuit, bounds, x


class Issue307Tests(unittest.TestCase):
    def test_current_and_retired_ids_and_sha_mapping(self):
        registry = validate_registry()
        mapping = json.loads((ROOT/'rf/constraints/history/issue307-migration.json').read_text())['mapping']
        self.assertEqual(set(registry['formal']), {'RF-F003'})
        self.assertEqual(set(registry['trial']), {'RF-T005', 'RF-T006', 'RF-T007', 'RF-T008'})
        for cid in mapping:
            if cid.startswith('RF-T'):
                with self.assertRaises(ValueError): load_constraint(cid)
            policy = load_constraint(cid, allow_trial=cid.startswith('RF-T'))
            self.assertEqual(constraint_fingerprint(policy), mapping[cid]['new_effective_sha256'])
            self.assertNotEqual(mapping[cid]['old_effective_sha256'], mapping[cid]['new_effective_sha256'])
        for cid in ('RF-F001', 'RF-F002', 'RF-T001', 'RF-T004'):
            with self.assertRaises(ValueError): load_constraint(cid, allow_trial=True)

    def test_loader_rejects_old_unknown_duplicate_and_wrong_trial_sha(self):
        for mutation in ('old', 'unknown', 'duplicate', 'trial_sha'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                shutil.copytree(ROOT/'rf/constraints', root/'rf/constraints')
                path = root/'rf/constraints/formal/RF-F003.json'
                p = json.loads(path.read_text())
                if mutation == 'old':
                    path.write_bytes((ROOT/'rf/constraints/history/pre-issue-307/formal/RF-F003.json').read_bytes())
                elif mutation == 'unknown':
                    p['unimplemented_physics'] = True
                    path.write_text(json.dumps(p))
                    regpath = root/'rf/constraints/registry.json'
                    reg = json.loads(regpath.read_text())
                    reg['formal']['RF-F003']['effective_constraint_sha256'] = constraint_fingerprint(p)
                    regpath.write_text(json.dumps(reg))
                elif mutation == 'duplicate':
                    path.write_text(path.read_text().replace('"schema_version": 2', '"schema_version": 2, "schema_version": 2'))
                else:
                    regpath = root/'rf/constraints/registry.json'
                    reg = json.loads(regpath.read_text())
                    reg['trial']['RF-T008']['effective_constraint_sha256'] = '0'*64
                    regpath.write_text(json.dumps(reg))
                with self.assertRaises(ValueError): validate_registry(root=root)

    def test_every_coordinate_closed_endpoints_and_no_clipping(self):
        for cid in ('RF-F003', 'RF-T005', 'RF-T006', 'RF-T007', 'RF-T008'):
            p, d, c, bounds, x = make(cid)
            self.assertEqual(circuit_box(c).bounds[:-1], bounds)
            self.assertEqual(circuit_box(c).open_lower, ())
            self.assertEqual(bounds[0], (.4, 27.))
            self.assertEqual(bounds[1], (.2, 56.))
            self.assertEqual(bounds[4], (.01, 2.))
            self.assertEqual(bounds[7], (.1, 100.))
            self.assertEqual(bounds[10:14], ((-.1,.1),(0.,0.),(0.,0.),(-.1,.1)))
            for i, (lo, hi) in enumerate(bounds):
                for endpoint in (lo, hi):
                    v = x.copy(); v[i] = endpoint
                    with self.subTest(cid=cid, index=i, endpoint=endpoint):
                        self.assertTrue(validate_values(d, c.schema, v, p)['component_policy_pass'])
                        self.assertTrue(c.validate_components(v)['component_policy_pass'])
                for outside in (np.nextafter(lo, -np.inf), np.nextafter(hi, np.inf)):
                    v = x.copy(); v[i] = outside
                    with self.subTest(cid=cid, index=i, outside=outside), self.assertRaises(ValueError):
                        validate_values(d, c.schema, v, p)
            narrowed = list(bounds); narrowed[7] = (.1, 10.)
            validate_search_box(narrowed, bounds)
            narrowed[7] = (0., 10.)
            with self.assertRaises(ValueError): validate_search_box(narrowed, bounds)
            with self.assertRaises(ValueError): circuit_box(c, gjm_search_max_pf=.09)
            np.testing.assert_array_equal(x, np.mean(bounds, axis=1))

    def test_complete_schema_constants_invariance_and_structure(self):
        p, d, c, bounds, x = make('RF-T007')
        self.assertEqual(c.schema.constant_caps_pf, (.5,))
        self.assertEqual(c.topology.capacitor_q[-1], 40.)
        for bad in (x[:-1], np.r_[x, 1.], np.full_like(x, np.nan), [True]*len(x), [str(v) for v in x]):
            with self.assertRaises(ValueError): validate_values(d, c.schema, bad, p)
        values = c.schema.decode(x)
        rows = list(values.capacitors_pf_by_setting); row = list(rows[-1]); row[0] += .1; rows[-1] = tuple(row)
        with self.assertRaises(ValueError):
            validate_values(d, c.schema, replace(values, capacitors_pf_by_setting=tuple(rows)), p)
        for kind in ('LQP01', 'LQW04', 'LQP02', 'unknown'):
            invalid = replace(d, inductor_types=(kind,) + d.inductor_types[1:])
            with self.assertRaises(ValueError): physical_bounds(invalid, c.schema, p)
        # Even a legal k endpoint must pass the existing all-L SPD gate.
        x[10] = bounds[10][1]
        with patch('lpf.rf_core.nominal_inductors.validate_inductor_coupling',
                   side_effect=ValueError('non-SPD')):
            with self.assertRaisesRegex(ValueError, 'non-SPD'): validate_values(d, c.schema, x, p)
        invalid = replace(d, variable_roles=('series', 'bridge'))
        with self.assertRaises(ValueError): validate_values(invalid, c.schema, x, p)

    def test_performance_and_trial_models_preserved(self):
        archive = ROOT/'rf/constraints/history/pre-issue-307'
        old = json.loads((archive/'formal/RF-F003.json').read_text())
        current = load_constraint()
        for key in ('source_ohms', 'load_ohms', 'bands_file', 'external_port_parasitics',
                    'chip_inductor_placement', 'area_formula', 'area_budget'):
            self.assertEqual(current[key], old[key])
        for cid in ('RF-F003', 'RF-T005', 'RF-T006', 'RF-T007', 'RF-T008'):
            p = load_constraint(cid, allow_trial=True)
            self.assertEqual(harmonic_limit_db(p), 30)
            self.assertEqual(harmonic_limit_db(p, 'nominal'), 35)
            self.assertEqual(limit_db(p, 'il_db', 'nominal'), .3)
            self.assertEqual(validate_performance(p)['modes']['matching_only']['excluded_regions'], ['H2','H3'])
            self.assertNotIn('full_phase2', p['evaluation'])
        trial = json.loads((archive/'trial/RF-T006.json').read_text())
        self.assertEqual(additional_stopband(load_constraint('RF-T006', allow_trial=True)), trial['study_additional_stopband'])
        t7 = load_constraint('RF-T007', allow_trial=True)
        self.assertEqual(t7['trial_shunt_dtc_parasitic'], json.loads((archive/'trial/RF-T007.json').read_text())['study_shunt_dtc_parasitic'])
        p,d,c,b,x = make('RF-T008')
        self.assertEqual(b[8:10], ((.02, 1.), (.02, .2)))
        self.assertEqual(b[14:16], ((.5, 3.), (.2, 3.)))
        self.assertEqual(c.topology.capacitor_q, (80.,60.,40.,35.,35.,60.,60.))
        self.assertEqual(c.schema.constant_caps_pf, ())
        for key in ('overrides',):
            bad = copy.deepcopy(current); bad['evaluation']['performance']['limits'][key] = [{'unknown':1}]
            with self.assertRaises(ValueError): validate_performance(bad)
        bad = copy.deepcopy(current); bad['evaluation']['performance']['limits']['defaults'].append(copy.deepcopy(bad['evaluation']['performance']['limits']['defaults'][0]))
        with self.assertRaises(ValueError): validate_performance(bad)


if __name__ == '__main__': unittest.main()
