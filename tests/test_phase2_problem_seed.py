"""C1 box and provenance tests, synthetic data only, no optimization."""
import sys
from pathlib import Path
import unittest
from dataclasses import replace
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from lpf.constraint_versions import load_constraint
from lpf.phase2_models.api import CircuitDefinition, NominalCircuit, build_nominal_circuit
from lpf.topology_management.circuit_layout import CapacitorPlacement, InductorTree
from lpf.phase2_models.problem_seed import definition_fingerprint, vector_fingerprint
from lpf.phase2_models.sampled_epigraph import SampledEpigraph


def make(policy_id, n=3):
    edges = ((0, 1), (1, 2), (1, 3)) if n == 3 else ((0, 1), (1, 3), (1, 4), (1, 2))
    pairs = ((0, 1), (0, 2)) if n == 3 else ((0, 1), (1, 3), (3, 2))
    order = tuple(range(n)) if n == 3 else (0, 1, 3, 2)
    var = ((3, -1), (0, 2))
    definition = CircuitDefinition(
        InductorTree(n+1, edges), ("LQP02HV",)*n, order, pairs,
        CapacitorPlacement(n+1, ((0, 1), (1, -1)), var,
                           var if policy_id == "RF-T008" else ()),
        ("GJM01", "PCB_PATTERN_C"), ("shunt_to_ground", "bridge"))
    c = build_nominal_circuit(load_constraint(policy_id, allow_trial=True), definition)
    vector = np.array([2.]*n + [1., .1] + [.02, 0. if n == 3 else -.03] + ([.01] if n == 4 else [])
                      + ([.5, .2] if policy_id == "RF-T008" else [])
                      + [0., 3.]*6)
    return SampledEpigraph(c, 1), vector


def seed(p, x, **overrides):
    kw = dict(policy_id=p.policy_id, policy_fingerprint=p.policy_fingerprint,
              definition_sha256=definition_fingerprint(p.circuit.definition),
              input_sha256=vector_fingerprint(x), seed=23)
    kw.update(overrides)
    return p.seed(x, **kw)


class ProblemSeedTests(unittest.TestCase):
    def test_box_seed_all_trials_and_topologies(self):
        for trial in ("RF-T005", "RF-T007", "RF-T008"):
            for n in (3, 4):
                with self.subTest(trial=trial, n=n):
                    p, x = make(trial, n)
                    self.assertEqual(len(p.box.bounds), len(x)+1)
                    self.assertEqual(p.box.bounds[-1], (None, None))
                    self.assertEqual(p.box.open_lower, ())
                    self.assertEqual(p.box.bounds[n+1], (.02, 1. if trial == "RF-T008" else .2))
                    if n == 3:
                        self.assertEqual(p.box.bounds[n+3], (-0., 0.))
                        x[n+3] = 0.
                    if trial == "RF-T008":
                        k_end = n + 2 + len(p.circuit.definition.coupling_pairs)
                        self.assertEqual(p.box.bounds[k_end:k_end+2], ((.5, 3.), (.2, 3.)))
                    if trial == "RF-T007":
                        self.assertEqual(p.circuit.schema.constant_caps_pf, (.5,))
                    self.assertTrue(p.circuit.validate_components(x)["component_policy_pass"])
                    r = seed(p, x)
                    np.testing.assert_array_equal(r["vector"][:-1], x)
                    self.assertEqual(r["changes"], ())
                    self.assertGreaterEqual(min(p.residuals(r["vector"])[p.evaluator.role == 0]), -1e-12)
                    self.assertTrue(r["candidate_promotion_blocked"])

    def test_reject_outside_box_jitter_and_identity(self):
        p, x = make('RF-T008', 4)
        for index, value in ((6, -.2), (-1, 4.)):
            bad = x.copy(); bad[index] = value
            with self.assertRaisesRegex(ValueError, 'clipping is forbidden'):
                seed(p, bad)
        r = seed(p, x)
        self.assertEqual(r['changes'], ())
        a = seed(p, x, jitter_fraction=.001)
        self.assertEqual(a, seed(p, x, jitter_fraction=.001))
        self.assertNotEqual(a, seed(p, x, jitter_fraction=.001, seed=24))
        for kw in ({"policy_id": "RF-T007"}, {"policy_fingerprint": "bad"},
                   {"definition_sha256": "bad"}, {"input_sha256": "bad"}):
            with self.assertRaises(ValueError):
                seed(p, x, **kw)
        with self.assertRaises(ValueError):
            seed(p, x[:-1])
        x[0] = np.nan
        with self.assertRaises(ValueError):
            seed(p, x)

    def test_defensive_policy_even_for_mutable_adapter(self):
        class MutableAdapter:
            policy = {"nested": {"value": 1}}
        nominal = NominalCircuit(MutableAdapter(), None)
        nominal.resolved_policy["nested"]["value"] = 2
        self.assertEqual(nominal.resolved_policy["nested"]["value"], 1)

    def test_mixed_inductor_coupling_and_closed_pcb_bound(self):
        d = CircuitDefinition(InductorTree(4, ((0, 1), (1, 2), (1, 3))),
            ("LQP02HV", "PCB_L", "PCB_L"), (0,), ((0, 1), (1, 2)),
            CapacitorPlacement(4, ((1, -1),), (), ()), ("PCB_PATTERN_C",), ())
        p = SampledEpigraph(build_nominal_circuit(load_constraint("RF-T005", allow_trial=True), d), 1)
        self.assertEqual(p.box.bounds[:3], ((.4, 27.), (.01, 2.), (.01, 2.)))
        self.assertEqual(p.box.open_lower, ())
        self.assertEqual(p.box.bounds[4:6], ((0., 0.), (-.1, .1)))
        x = np.array([2., 1., 1., .1, 0., -.05])
        r = seed(p, x)
        self.assertEqual(r["input_vector"], tuple(x))
        self.assertEqual(r["vector"][4], 0.)
        x[1] = .01
        self.assertTrue(p.circuit.validate_components(x)['component_policy_pass'])
        x[1] = 0.
        with self.assertRaisesRegex(ValueError, 'clipping is forbidden'):
            seed(p, x)

    def test_multistart_determinism_legality_and_fail_closed(self):
        from unittest.mock import patch
        from lpf.phase2_models.multistart import generate_starts, unique_topologies
        for n in (3, 4):
            p, x = make('RF-T008', n)
            if n == 3:
                x[6] = 0.
            a = generate_starts(p, x, seed=23)
            from lpf.phase2_models.evaluation_cost import EvaluationCost
            meter = EvaluationCost()
            pair = generate_starts(p, x, seed=23, count=2, cost_meter=meter)
            self.assertEqual(pair['starts'], a['starts'][:2])
            self.assertEqual(meter.RF_forward_calls, 2)
            self.assertEqual(meter.frequency_samples_requested, 56)
            self.assertEqual(a, generate_starts(p, x, seed=23))
            self.assertNotEqual(a, generate_starts(p, x, seed=24))
            self.assertEqual([s['id'].split('-')[-1] for s in a['starts']], ['0', '1', '2'])
            self.assertEqual(len({s['id'] for s in a['starts']}), 3)
            self.assertEqual(len({s['vector_sha256'] for s in a['starts']}), 3)
            self.assertEqual([s['generation_method'] for s in a['starts']],
                             ['nominal_design', 'sobol', 'sobol'])
            for s in a['starts']:
                self.assertEqual(s['vector_sha256'], vector_fingerprint(s['vector']))
                detail = p.circuit.validate_components(s['vector'])
                self.assertEqual(detail['checked_settings'], 6)
                self.assertGreater(detail['min_L_eigenvalue_H'], 0)
                self.assertFalse(s['seed_record']['changes'])
            self.assertEqual(unique_topologies([p.circuit, p.circuit]), [p.circuit])
            bad = x.copy()
            bad[n] = 0.
            with self.assertRaisesRegex(ValueError, 'Box violation'):
                generate_starts(p, bad, seed=23)
            bad = x.copy()
            bad[-1] = 4.
            with self.assertRaisesRegex(ValueError, 'Box violation'):
                generate_starts(p, bad, seed=23)
            with patch('lpf.phase2_models.multistart.qmc.Sobol') as sobol:
                bounds = np.asarray(p.box.bounds[:-1], float)
                unit = np.divide(x - bounds[:, 0], bounds[:, 1] - bounds[:, 0],
                    out=np.zeros_like(x), where=bounds[:, 1] != bounds[:, 0])
                sobol.return_value.random_base2.return_value = np.tile(unit, (16, 1))
                # A degenerate legal block must not lead to unlimited retries.
                with self.assertRaisesRegex(ValueError, 'Insufficient legal distinct'):
                    generate_starts(p, x, seed=23)
                sobol.return_value.random_base2.assert_called_once_with(4)

    def test_continuation_initial_forward_failure_never_skips_to_next_sobol(self):
        from unittest.mock import patch
        from lpf.phase2_models.coupled_lc_evaluator import CoupledLCEvaluator
        from lpf.phase2_models.experiment_config import prepare_continuation_starts, ContinuationPreparationError
        p, _ = make('RF-T008', 4)
        config = dict(schema_version=4, methods=['A', 'B', 'C', 'D'],
                      rf={'effective_sha256': p.circuit.policy_fingerprint},
                      definition_sha256=definition_fingerprint(p.circuit.definition))
        original = CoupledLCEvaluator.il
        calls = []
        def fail_second(evaluator, vector):
            calls.append(1)
            if len(calls) == 2:
                raise ValueError('synthetic forward failure')
            return original(evaluator, vector)
        with patch.object(CoupledLCEvaluator, 'il', fail_second):
            with self.assertRaises(ContinuationPreparationError) as error:
                prepare_continuation_starts(p.circuit, config)
        self.assertEqual(len(calls), 2)
        self.assertEqual(error.exception.cost['frequency_samples_requested'], 112)
        self.assertEqual(error.exception.cost['frequency_samples_completed'], 56)
        self.assertEqual(error.exception.cost['forward_failures'], 1)

    def test_impedance_design_prototype_pool_and_fail_closed(self):
        from lpf.phase2_models.multistart import generate_starts
        from lpf.phase2_models.designed_starts import design_candidates, impedance
        from lpf.phase2_models.start_selection import StartSelectionError
        d = CircuitDefinition(
            InductorTree(4, ((0, 1), (1, 3), (3, 2))), ('LQP02HV',)*3,
            (0, 1, 2), ((0, 1), (1, 2)),
            CapacitorPlacement(4, (), ((0, -1),), ((0, -1),)), (), ('shunt_to_ground',))
        p = SampledEpigraph(build_nominal_circuit(
            load_constraint('RF-T008', allow_trial=True), d), 2)
        x = np.array([2., 2., 2., 0., 0., .5] + [1.]*6)
        # Synthetic matching fixture only: actual fixed-S2P feasibility is
        # separately diagnosed, never inferred from this engineering test.
        p.evaluator.pre[:] = np.eye(2)
        p.evaluator.post[:] = np.eye(2)
        p.evaluator.source_ohms = 50.+0j
        p.evaluator.load_ohms = 40.-40j
        designs = design_candidates(p, x)
        np.testing.assert_array_equal(x, [2., 2., 2., 0., 0., .5] + [1.]*6)
        for row in designs:
            self.assertTrue(p.circuit.validate_components(row['vector'])['component_policy_pass'])
            diag = row['design']
            self.assertEqual(len(diag['representatives']), 6)
            anchor = diag['anchor_setting']
            rep = diag['representatives'][anchor]
            zs, zl = complex(*rep['source_ohms']), complex(*rep['load_ohms'])
            branch = zl + 1j * rep['series_x_ohms']
            matched = 1 / (1 / branch + 1j * rep['shunt_b_siemens'])
            self.assertAlmostEqual(abs(matched - zs.conjugate()), 0., places=10)
            self.assertGreater(sum(diag['series_loss_ohms_by_L']), 0)
            self.assertEqual(len(diag['approximate_response']), 6)
            self.assertAlmostEqual(diag['approximate_response'][anchor]['external_gt'], 1.)
        out_d = replace(d, capacitor_placement=CapacitorPlacement(
            4, (), ((2, -1),), ((2, -1),)))
        out_p = SampledEpigraph(build_nominal_circuit(
            load_constraint('RF-T008', allow_trial=True), out_d), 2)
        out_p.evaluator.pre[:] = np.eye(2)
        out_p.evaluator.post[:] = np.eye(2)
        out_p.evaluator.load_ohms = 100.-40j
        for row in design_candidates(out_p, x):
            diag = row['design']
            self.assertEqual(diag['shunt_port'], 'output')
            self.assertAlmostEqual(diag['approximate_response'][diag['anchor_setting']]['external_gt'], 1.)
        self.assertEqual(impedance(np.eye(2), 60-40j), 60-40j)
        kw = dict(seed=23, selection='rf_pareto', max_initial_samples=952)
        a = generate_starts(p, x, candidate_pool='design_prototype', **kw)
        b = generate_starts(p, x, candidate_pool='design_prototype', **kw)
        baseline = generate_starts(p, x, **kw)
        # Frozen against main 6f4a5da, excluding measured timing only.
        from lpf.checkpoint_io import canonical_config_hash
        for generated, expected in ((baseline,
                '8b3ff7c05f8a185b98df28c58ac48c3f8e5b9f944995397bdd9005fea9ceb775'),
                (a, '5df4656451891398d67ec19087a2f2f149948507d9dbe5332716c60ce5097b89')):
            self.assertEqual(canonical_config_hash([r['vector_sha256'] for r in
                generated['selection_report']['candidates']]), expected)
        self.assertEqual(a['starts'], b['starts'])
        report = a['selection_report']
        self.assertEqual(report['cost']['frequency_samples_requested'], 952)
        self.assertEqual(report['cost']['frequency_samples_requested'],
                         baseline['selection_report']['cost']['frequency_samples_requested'])
        self.assertEqual([r['generation_method'] for r in report['candidates'][1:3]],
                         ['impedance_design_prototype']*2)
        self.assertTrue(all(r['sobol_index'] is None for r in report['candidates'][1:3]))
        self.assertEqual([r['vector_sha256'] for r in report['candidates'][3:]],
                         [r['vector_sha256'] for r in baseline['selection_report']['candidates'][3:]])
        from unittest.mock import patch
        illegal = [dict(row, vector=row['vector'].copy()) for row in designs]
        illegal[0]['vector'][-1] = 4.
        with patch('lpf.phase2_models.designed_starts.design_candidates', return_value=illegal):
            with self.assertRaises(StartSelectionError) as rejected:
                generate_starts(p, x, candidate_pool='design_prototype', **kw)
        self.assertEqual(rejected.exception.report['cost']['frequency_samples_requested'], 56)
        self.assertEqual(rejected.exception.report['candidates'][-1]['pool_index'], 0)
        self.assertEqual(rejected.exception.report['candidates'][-1]['reason'], 'rejected')
        with self.assertRaises(StartSelectionError) as stopped:
            generate_starts(p, x, seed=23, selection='rf_pareto',
                            candidate_pool='design_prototype', max_initial_samples=56)
        self.assertEqual(stopped.exception.report['status'], 'failed')
        unsupported, u = make('RF-T008', 3)
        u[6] = 0.
        with self.assertRaises(StartSelectionError):
            generate_starts(SampledEpigraph(unsupported.circuit, 2), u,
                            candidate_pool='design_prototype', **kw)
        with self.assertRaises(ValueError):
            generate_starts(p, x, seed=23, candidate_pool='design_prototype')

    def test_multistart_warm_identity(self):
        import hashlib
        import json
        import tempfile
        from dataclasses import asdict
        from lpf.phase2_models.multistart import generate_starts
        p, x = make('RF-T008', 4)
        body = {'policy_id': p.policy_id, 'policy_sha256': p.policy_fingerprint,
                'definition_sha256': definition_fingerprint(p.circuit.definition),
                'parameter_schema': asdict(p.circuit.schema), 'vector': x.tolist(),
                'vector_sha256': vector_fingerprint(x)}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'warm.json'
            def save():
                path.write_text(json.dumps(body))
                return hashlib.sha256(path.read_bytes()).hexdigest()
            sha = save()
            result = generate_starts(p, x, seed=23, warm_checkpoint=path, warm_sha256=sha)
            self.assertEqual(result['starts'][0]['source_checkpoint']['sha256'], sha)
            self.assertEqual(result['starts'][0]['generation_method'], 'verified_warm_checkpoint')
            selected = generate_starts(SampledEpigraph(p.circuit, 2), x, seed=23,
                warm_checkpoint=path, warm_sha256=sha, selection='rf_pareto')
            self.assertEqual(selected['starts'][0]['vector'], x.tolist())
            self.assertEqual(selected['starts'][0]['source_checkpoint']['sha256'], sha)
            with self.assertRaisesRegex(ValueError, 'SHA mismatch'):
                generate_starts(p, x, seed=23, warm_checkpoint=path, warm_sha256='0'*64)
            for field in ('policy_sha256', 'definition_sha256', 'parameter_schema', 'vector_sha256'):
                original = body[field]
                body[field] = 'wrong'
                with self.assertRaises(ValueError):
                    generate_starts(p, x, seed=23, warm_checkpoint=path, warm_sha256=save())
                body[field] = original

    def test_intermediate_scan_separate_grid_no_mutation(self):
        from lpf.phase2_models.multistart import intermediate_scan
        p, x = make('RF-T008', 4)
        before = x.copy()
        result = intermediate_scan(p.circuit, x)
        self.assertEqual(result['grid']['sample_count'], 28*17)
        evaluator = p.circuit.forward_evaluator(17)
        self.assertEqual(set(evaluator.setting), set(range(6)))
        self.assertEqual(set(evaluator.segment), set(range(28)))
        self.assertTrue(all(np.count_nonzero(evaluator.segment == i) == 17 for i in range(28)))
        self.assertEqual(result['observation']['sampled_forward_metrics'], evaluator.summary(x))
        self.assertTrue(all(v == 'not_run' for v in result['validation'].values()))
        np.testing.assert_array_equal(x, before)

    def test_closed_lower_and_explicit_policy(self):
        p, x = make('RF-T005', 4)
        x[4] = 0
        with self.assertRaisesRegex(ValueError, 'clipping is forbidden'):
            seed(p, x)
        definition = p.circuit.definition
        for identifier in ('RF-F003', 'RF-T006'):
            circuit = build_nominal_circuit(load_constraint(identifier, allow_trial=True), definition)
            self.assertEqual(circuit.policy_id, identifier)
        altered = replace(definition, physical_order=(1, 0, 3, 2))
        other = SampledEpigraph(build_nominal_circuit(
            load_constraint("RF-T005", allow_trial=True), altered), 1)
        with self.assertRaisesRegex(ValueError, "topology fingerprint"):
            seed(other, x, definition_sha256=definition_fingerprint(definition))


class RFStartSelectionTests(unittest.TestCase):
    def setUp(self):
        self.p, self.x = make('RF-T008', 3)
        self.x[6] = 0.
        self.p = SampledEpigraph(self.p.circuit, 2)

    def generate(self, **kwargs):
        from lpf.phase2_models.multistart import generate_starts
        return generate_starts(self.p, self.x, seed=23, selection='rf_pareto', **kwargs)

    def test_reproducible_full_block_score_cost_and_default_SHA(self):
        from unittest.mock import patch
        from lpf.phase2_models.multistart import generate_starts
        from lpf.phase2_models.evaluation_cost import EvaluationCost
        def mock(e, x):
            return np.choose(e.role, [x[0], 30., np.nextafter(30., 0.)])
        with patch.object(type(self.p.evaluator), 'il', mock):
            legacy = generate_starts(self.p, self.x, seed=23)
            meter = EvaluationCost()
            a = self.generate(cost_meter=meter)
            b = self.generate()
            # Measured timing varies but must not enter synthetic preview run ID.
            from lpf.phase2_models.multistart import run_multistart_preview
            class Captured(Exception):
                pass
            ids = []
            def capture_plan(*args, **kwargs):
                ids.append(kwargs['run_id'])
                raise Captured()
            with patch('lpf.phase2_models.multistart.make_synthetic_plan',
                       side_effect=capture_plan):
                for generated in (a, b):
                    with self.assertRaises(Captured):
                        run_multistart_preview(self.p.circuit, generated, None,
                            optimize_stage=lambda *args: None,
                            historical_benchmarks=[], max_new_starts=0)
            self.assertEqual(len(ids), 2)
            self.assertEqual(ids[0], ids[1])
        self.assertEqual([s['vector_sha256'] for s in legacy['starts']], [
            'b6a098b045772b02fee8ed619e5324481ed72cbcf3008cc522783df5009ba591',
            'ae535ea3b9b6c9f9986a726f7186bbd4548789d24fd5a35cabd058d9223b5dc9',
            '545b09f059e8d8223055ef065ca521d1a63aafb05c452a54189da92504ec9d83'])
        self.assertEqual(a['starts'], b['starts'])
        ra = a['selection_report']
        self.assertEqual(len(ra['candidates']), 17)
        self.assertEqual(ra['baseline_prefix_vector_sha256'],
                         [s['vector_sha256'] for s in legacy['starts']])
        self.assertEqual(ra['cost']['RF_forward_calls'], 17)
        self.assertEqual(ra['cost']['frequency_samples_requested'], 952)
        self.assertEqual(ra['cost']['frequency_samples_completed'], 952)
        self.assertEqual(ra['baseline_frequency_samples_requested'], 168)
        self.assertEqual(ra['extra_frequency_samples_requested'], 784)
        self.assertEqual(meter.RF_forward_calls, 17)
        for row in ra['candidates']:
            self.assertEqual(row['cost']['RF_forward_calls'], 1)
            self.assertEqual(row['vector'][6], 0.)
            self.assertFalse(row['score']['strict_feasible'])
            self.assertGreater(row['score']['max_violation_db'], 0.)
            self.p.circuit.validate_components(row['vector'])
        self.assertEqual(set(self.p.evaluator.setting), set(range(6)))
        self.assertEqual(set(self.p.evaluator.segment), set(range(28)))
        self.assertEqual(a['starts'][0]['vector'], legacy['starts'][0]['vector'])

    def test_pareto_high_IL_and_distance_ties(self):
        from lpf.phase2_models.start_selection import select_pair
        def item(i, f, v, x):
            return {'sobol_index': i, 'vector': [x, 0.], 'score': {
                'worst_il_db': f, 'max_violation_db': v, 'sum_violation_db': v}}
        low = item(0, 1., 5., 0.)
        near = item(1, 2., 0., .2)
        far = item(2, 2., 0., .8)
        high = item(3, 100., 0., 1.)
        bounds = np.array([[0., 1.], [0., 0.]])
        self.assertEqual(select_pair([None, high, near, far, low], bounds), (low, far))
        # Dominating singleton front still yields two distinct candidates.
        best = item(4, .5, 0., .1)
        self.assertEqual(select_pair([None, best, low, high], bounds), (best, high))

    def test_budget_forward_failure_and_all_rejected_preserve_partial(self):
        from unittest.mock import patch
        from lpf.phase2_models.evaluation_cost import EvaluationCost
        from lpf.phase2_models.start_selection import StartSelectionError
        def mock(e, x):
            return np.choose(e.role, [x[0], 30., 31.])
        meter = EvaluationCost(frequency_samples_requested=100)
        with patch.object(type(self.p.evaluator), 'il', mock):
            with self.assertRaises(StartSelectionError) as cm:
                self.generate(cost_meter=meter, max_initial_samples=168)
        report = cm.exception.report
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['cost']['frequency_samples_requested'], 168)
        self.assertEqual(len(report['candidates']), 4)
        self.assertIn('budget exhausted', report['candidates'][-1]['exception'])
        calls = []
        def fail(e, x):
            calls.append(1)
            if len(calls) == 3:
                raise RuntimeError('forward failed')
            return mock(e, x)
        with patch.object(type(self.p.evaluator), 'il', fail):
            with self.assertRaises(StartSelectionError) as cm:
                self.generate()
        r = cm.exception.report
        self.assertEqual(r['cost']['forward_failures'], 1)
        self.assertEqual(r['cost']['frequency_samples_requested'], 168)
        self.assertEqual(r['cost']['frequency_samples_completed'], 112)
        self.assertEqual(len(r['candidates']), 3)
        # One fixed block of duplicate nominal vectors: no retry, no partial selection.
        fixed = tuple((float(v), float(v)) for v in self.x) + ((None, None),)
        with patch.object(self.p, 'box', replace(self.p.box, bounds=fixed, open_lower=())):
            with self.assertRaisesRegex(StartSelectionError, 'Insufficient legal') as cm:
                self.generate()
        self.assertEqual(len(cm.exception.report['candidates']), 17)
        self.assertEqual(cm.exception.report['cost']['RF_forward_calls'], 1)
        original = type(self.p.circuit).validate_components
        def reject(c, x, **kw):
            if x[0] > 20.:
                raise ValueError('Full inductance matrix is non-positive-definite or ill-conditioned')
            return original(c, x, **kw)
        with patch.object(type(self.p.circuit), 'validate_components', reject):
            r = self.generate()['selection_report']
        rejected = [row for row in r['candidates'] if row['reason'] == 'rejected']
        self.assertTrue(rejected)
        self.assertEqual(r['cost']['spd_rejections'], len(rejected))
        self.assertEqual(r['cost']['RF_forward_calls'], 17 - len(rejected))
        self.assertTrue(all(row['cost']['RF_forward_calls'] == 0 for row in rejected))

    def test_zero_GJM_exploration_only_and_read_only_real_forward(self):
        from lpf.phase2_models.start_selection import StartSelectionError
        self.x[3] = 0.
        with self.assertRaises(StartSelectionError) as cm:
            self.generate()
        self.assertEqual(cm.exception.report['cost']['RF_forward_calls'], 0)
        # #307 has no absent-GJM bounds exception, even for exploration.
        with self.assertRaises(StartSelectionError) as cm:
            self.generate(for_exploration=True)
        self.assertEqual(cm.exception.report['cost']['RF_forward_calls'], 0)
        self.x[3] = 1.
        definition = replace(self.p.circuit.definition,
                             variable_roles=('shunt_to_ground', 'series'))
        self.p = SampledEpigraph(build_nominal_circuit(
            self.p.circuit.resolved_policy, definition), 2)
        with self.assertRaisesRegex(StartSelectionError, 'role not proven'):
            self.generate()
        with self.assertRaises(StartSelectionError):
            self.generate(for_exploration=True)


if __name__ == "__main__":
    unittest.main()
