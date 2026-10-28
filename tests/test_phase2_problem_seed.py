"""C1 box and provenance tests, synthetic data only, no optimization."""
import sys
from pathlib import Path
import unittest
from dataclasses import replace
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from lpf.constraint_versions import load_constraint
from lpf.phase2_models.api import CircuitDefinition, NominalCircuit, build_nominal_circuit
from lpf.phase2_models.circuit_layout import CapacitorPlacement, InductorTree
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
    vector = np.array([2.]*n + [1., .1] + [.02, -.03] + ([.01] if n == 4 else [])
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
                    self.assertEqual(p.box.open_lower, (n,))
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

    def test_clip_jitter_and_identity(self):
        p, x = make("RF-T008", 4)
        x[6] = -.2  # signed adjacent k clipped, never silently changed
        x[-1] = 4.  # Cv clipped at maximum
        r = seed(p, x)
        self.assertEqual([z["index"] for z in r["changes"]], [6, len(x)-1])
        self.assertEqual(r["vector"][6], -.1)
        self.assertEqual(r["vector"][-2], 3.)
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

    def test_mixed_inductor_coupling_and_open_pcb_bound(self):
        d = CircuitDefinition(InductorTree(4, ((0, 1), (1, 2), (1, 3))),
            ("LQP02HV", "PCB_L", "PCB_L"), (0,), ((0, 1), (1, 2)),
            CapacitorPlacement(4, ((1, -1),), (), ()), ("PCB_PATTERN_C",), ())
        p = SampledEpigraph(build_nominal_circuit(load_constraint("RF-T005", allow_trial=True), d), 1)
        self.assertEqual(p.box.bounds[:3], ((.4, 27.), (0., 2.), (0., 2.)))
        self.assertEqual(p.box.open_lower, (1, 2))
        self.assertEqual(p.box.bounds[4:6], ((0., 0.), (-.1, .1)))
        x = np.array([2., 1., 1., .1, .5, -.05])
        r = seed(p, x)
        self.assertEqual(r["input_vector"], tuple(x))
        self.assertEqual(r["vector"][4], 0.)
        x[1] = 0.
        with self.assertRaisesRegex(ValueError, "open lower"):
            seed(p, x)

    def test_open_lower_and_invalid_policy(self):
        p, x = make("RF-T005", 4)
        x[4] = 0
        with self.assertRaisesRegex(ValueError, "open lower"):
            seed(p, x)
        definition = p.circuit.definition
        for identifier in ("RF-F003", "RF-T006"):
            with self.assertRaises(ValueError):
                build_nominal_circuit(load_constraint(identifier, allow_trial=True), definition)
        altered = replace(definition, physical_order=(1, 0, 3, 2))
        other = SampledEpigraph(build_nominal_circuit(
            load_constraint("RF-T005", allow_trial=True), altered), 1)
        with self.assertRaisesRegex(ValueError, "topology fingerprint"):
            seed(other, x, definition_sha256=definition_fingerprint(definition))


if __name__ == "__main__":
    unittest.main()
