"""Current three-layer contract and strict schema2 legality (no legacy oracle/EXP)."""
import ast
import copy
from dataclasses import asdict, fields, replace
from pathlib import Path
import sys
import subprocess
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.constraint_versions import load_constraint, constraint_fingerprint
from lpf.topology_management import CircuitDefinition, InductorTree, CapacitorPlacement
from lpf.rf_core import build_rf_model
from lpf.search.component_constraints import physical_bounds, validate_values


IDS = ('RF-F003', 'RF-T005', 'RF-T006', 'RF-T007', 'RF-T008')


def make(cid):
    """Complete current model, with no NominalCircuit or policy wrapper."""
    p = load_constraint(cid, allow_trial=cid.startswith('RF-T'))
    var = ((0, -1), (0, 2))
    d = CircuitDefinition(InductorTree(8, tuple((i, i+1) for i in range(7))),
        ('LQP02HV', 'LQP02HQ', 'LQP02HV', 'LQP02HV', 'PCB_L', 'PCB_L', 'PCB_L'),
        (0, 1, 2, 3), ((0, 1), (0, 2), (1, 4), (4, 5)),
        CapacitorPlacement(8, ((1, -1), (2, -1), (1, 3)), var,
                           var if cid == 'RF-T008' else ()),
        ('GJM01', 'PCB_PATTERN_C', 'PCB_PATTERN_C'), ('shunt_to_ground', 'bridge'))
    c = build_rf_model(d, p)
    bounds = physical_bounds(d, c.schema, p)
    return p, d, c, bounds, np.mean(bounds, axis=1)


class DependenciesTests(unittest.TestCase):
    def test_topology_identity_and_fields(self):
        # Structural types have one owner, without legacy re-export modules.
        root = Path(__file__).resolve().parents[1] / 'src/lpf/phase2_models'
        for name in ('circuit_layout', 'role_audit'):
            self.assertFalse((root / (name + '.py')).exists())
        self.assertEqual([f.name for f in fields(CircuitDefinition)], [
            'inductor_tree', 'inductor_types', 'physical_order', 'coupling_pairs',
            'capacitor_placement', 'fixed_c_types', 'variable_roles'])
        _, d, _, _, _ = make('RF-T008')
        self.assertEqual(asdict(d)['inductor_tree']['edges'], d.inductor_tree.edges)
        self.assertTrue(CircuitDefinition.__module__.startswith('lpf.topology_management'))

    def test_import_boundaries_and_legacy_callers(self):
        root = Path(__file__).resolve().parents[1] / 'src/lpf'
        def imports(path):
            result = []
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom):
                    result.append(node.module or '')
                elif isinstance(node, ast.Import):
                    result.extend(alias.name for alias in node.names)
            return result
        for path in (root / 'topology_management').glob('*.py'):
            self.assertFalse(any(any(part in name.split('.') for part in
                                     ('search', 'rf_core', 'phase2_models')) for name in imports(path)))
        self.assertFalse(any('search' in name.split('.') for name in imports(root/'constraint_versions.py')))
        legacy_arrows = {path.name for path in (root/'phase2_models').glob('*.py')
                         if any('search' in name.split('.') for name in imports(path))}
        # Isolated old callers, not part of the schema2 import/call graph.
        self.assertEqual(legacy_arrows, {'api.py', 'problem_seed.py'})
        for path in (root/'rf_core').glob('*.py'):
            self.assertFalse(any('phase2_models' in name.split('.') or 'search' in name.split('.')
                                 for name in imports(path)), path)
        for path in (root/'search').glob('*.py'):
            self.assertFalse(any('phase2_models' in name.split('.') for name in imports(path)), path)
        # Independent branch-current MNA must not call the forward implementation.
        self.assertFalse(any(name.endswith('.model') for name in imports(root/'rf_core/branch_mna.py')))
        retired = {'api', 'problem_seed', 'rft005_t007_policy_circuit', 'rft008_policy_circuit'}
        paths = list((root/'search').glob('*.py')) + list((root/'rf_core').glob('*.py'))
        paths += [root.parents[1]/'scripts/run_rf_search.py']
        for path in paths:
            self.assertFalse(any(retired.intersection(name.split('.')) for name in imports(path)), path)

    def test_retired_experiment_entrypoints_absent(self):
        root = Path(__file__).resolve().parents[1]
        for path in ('scripts/run_phase2_shared.py', 'scripts/run_phase2_one_start.py',
                     'scripts/prepare_issue250_comparison.py', 'scripts/diagnose_phase2_scaling.py',
                     'src/lpf/phase2_models/experiment_config.py',
                     'src/lpf/phase2_models/experiment_run.py',
                     'src/lpf/phase2_models/experiment_post_search.py'):
            self.assertFalse((root / path).exists(), path)

    def test_retired_optimizer_closure_is_absent(self):
        root = Path(__file__).resolve().parents[1] / 'src/lpf/phase2_models'
        for name in ('candidate_records', 'designed_starts', 'evaluation_cost',
                     'frequency_exchange', 'frequency_exchange_c1', 'generic_starts',
                     'multistart', 'normalized_epigraph', 'optimizer_comparison',
                     'post_search_evidence', 'post_search_journal', 'post_search_validation',
                     'rf_pipeline_adapter', 'sampled_epigraph', 'scipy_de_preview',
                     'staged_optimization', 'start_selection', 'synthetic_plan',
                     'synthetic_runner'):
            self.assertFalse((root / (name + '.py')).exists(), name)

    def test_checkout_checks_have_one_definition_and_no_legacy_gate_import(self):
        from lpf.search import checkout, gates, preservation
        for name in ('_complete_checkout', '_fresh_main'):
            self.assertIs(getattr(gates, name), getattr(checkout, name))
        for module in (gates, preservation):
            source = Path(module.__file__).read_text()
            self.assertNotIn('scripts.run_phase2_shared', source)
            self.assertNotIn('scripts.run_phase2_one_start', source)

    def test_science_and_preservation_without_legacy_execution_closure(self):
        # Run actual scientific assertions in a fresh interpreter, rather than
        # importing old modules merely to patch them. Covers transitive fixture
        # dependencies as well as G3/G4, unlike develop-only blocked imports.
        code = '''
import importlib.abc
import sys
import unittest
sys.path[:0] = ['src', 'tests']
class BlockLegacy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('lpf.phase2_models', 'scripts.run_phase2_')):
            raise AssertionError('Legacy execution dependency: ' + fullname)
sys.meta_path.insert(0, BlockLegacy())
from lpf.search import gates, preservation
from lpf.experiment_preservation import finalize_experiment, aggregate_selected
assert aggregate_selected([], {})['validation'] == {'numerical': 'not_run', 'independent': 'not_run'}
suite = unittest.defaultTestLoader.loadTestsFromNames([
    'test_issue307_constraints', 'test_issue309_rf_core',
    'test_issue311_performance', 'test_issue315_fixed_stage',
    'test_issue323_dependencies.DependenciesTests.test_new_values_without_legacy_validation_or_forward',
])
result = unittest.TextTestRunner(verbosity=1).run(suite)
assert result.wasSuccessful()
assert not any(name.startswith(('lpf.phase2_models', 'scripts.run_phase2_')) for name in sys.modules)
'''
        subprocess.run([sys.executable, '-c', code], check=True,
                       cwd=Path(__file__).resolve().parents[1])

    def test_exact_closed_bounds_including_all_40_coupling_neighbors(self):
        coupling_rejections = 0
        for cid in IDS:
            p, d, c, bounds, x = make(cid)
            for i, (lo, hi) in enumerate(bounds):
                for endpoint in (lo, hi):
                    v = x.copy(); v[i] = endpoint
                    with self.subTest(cid=cid, index=i, endpoint=endpoint):
                        self.assertTrue(validate_values(d, c.schema, v, p)['component_policy_pass'])
                for outside in (np.nextafter(lo, -np.inf), np.nextafter(hi, np.inf)):
                    v = x.copy(); v[i] = outside
                    with self.subTest(cid=cid, index=i, outside=outside), self.assertRaises(ValueError):
                        validate_values(d, c.schema, v, p)
                    coupling_rejections += int(10 <= i < 14)
            np.testing.assert_array_equal(x, np.mean(bounds, axis=1))
        self.assertEqual(coupling_rejections, 40)

    def test_new_values_without_legacy_validation_or_forward(self):
        for cid in IDS:
            p, d, c, bounds, x = make(cid)
            with patch('lpf.rf_core.model.RFEvaluator.evaluate', side_effect=AssertionError('forward')):
                result = validate_values(d, c.schema, x, p)
                self.assertEqual(result['constraint_fingerprint'], constraint_fingerprint(p))
                self.assertEqual(result['checked_settings'], 6)
                self.assertTrue(result['component_policy_pass'])
                self.assertGreater(result['min_L_eigenvalue_H'], 0)
                self.assertFalse(result['rf_performance_checked'])
                for bad in (x[:-1], np.full_like(x, np.nan), [True]*len(x)):
                    with self.assertRaises(ValueError): validate_values(d, c.schema, bad, p)
                values = c.decode(x)
                # Fixed GJM, trial IC-fixed, and T007 constant parasite cannot
                # vary between settings, even when all coordinates are in box.
                indices = [0]
                if c.schema.constant_caps_pf:
                    indices.append(-1)
                if c.schema.n_ic_fixed:
                    indices.append(c.schema.n_fixed + c.schema.n_variable)
                for index in indices:
                    rows = [list(row) for row in values.capacitors_pf_by_setting]
                    rows[-1][index] += .1
                    bad = replace(values, capacitors_pf_by_setting=tuple(map(tuple, rows)))
                    with self.assertRaises(ValueError): validate_values(d, c.schema, bad, p)
                invalid = replace(d, variable_roles=('series', 'bridge'))
                with self.assertRaises(ValueError): validate_values(invalid, c.schema, x, p)
                with patch('lpf.rf_core.nominal_inductors.validate_inductor_coupling',
                           side_effect=ValueError('non-SPD')):
                    with self.assertRaisesRegex(ValueError, 'non-SPD'): validate_values(d, c.schema, x, p)
                for field in ('q', 'max_count'):
                    changed = copy.deepcopy(p)
                    changed['components']['PCB_PATTERN_C'][field] = 0
                    with self.assertRaises(ValueError): validate_values(d, c.schema, x, changed)
                with self.assertRaises(ValueError):
                    validate_values(d, c.schema, x, dict(p, active_constraint_id='RF-T999'))
