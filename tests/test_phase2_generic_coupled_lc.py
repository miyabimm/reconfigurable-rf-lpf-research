"""Frozen-vector numerical parity for one topology-agnostic RF forward model.

No new EXP is launched and numerical parity is not RF or physical compliance.
The legacy shaped modules are used as test references, never runtime imports
by the generic model.
"""
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lpf.constraint_versions import load_constraint
from lpf.phase2_models.circuit_layout import InductorTree
from lpf.phase2_models.coupled_lc import (
    CircuitValues, CoupledLCTopology, CoupledLCEvaluator,
    ParameterVectorSchema,
)
from lpf.phase2_models import (
    exp042, exp055, exp058_area3, exp058_area4, exp058_area4l_gjm,
)

SNAP = ROOT / "data/pareto_snapshots"
RUNS = ROOT / "experiments/chatgpt_topology_search/runs"
FOUR_PAIRS = ((0, 1), (1, 3), (3, 2))
THREE_PAIRS = ((0, 2), (2, 1))


def generic(policy, legacy, *, n_l, n_fixed, n_var, n_ic, edges, pairs,
            q, constant_caps=(), points=3, graph=None):
    tree = InductorTree(n_l + 1, edges if graph is None else graph)
    schema = ParameterVectorSchema(n_l, n_fixed, len(pairs), n_ic, n_var,
                                   tuple(constant_caps))
    topo = CoupledLCTopology(tree, pairs, (25.,) * n_l,
                             legacy.cap_edges if hasattr(legacy, "cap_edges")
                             else exp042.C_EDGES, tuple(map(float, q)))
    return CoupledLCEvaluator(policy, points, topo, schema)


def snapshot(filename, field):
    return json.loads((SNAP / filename).read_text(encoding="utf-8"))[field]


class GenericCircuitEvaluationTests(unittest.TestCase):
    def check_case(self, original, common, x):
        x = np.asarray(x, float)
        self.assertEqual(x.size, common.schema.vector_length)
        val = common.schema.decode(x)
        self.assertIsInstance(val, CircuitValues)
        np.testing.assert_array_equal(common.schema.encode(val), x)
        np.testing.assert_allclose(common.il(x), original.il(x), atol=1e-9,
                                   rtol=0)
        np.testing.assert_allclose(common.il(val), original.il(x), atol=1e-9,
                                   rtol=0)
        self.assertEqual(common.role.tolist(), original.role.tolist())
        self.assertEqual(common.setting.tolist(), original.setting.tolist())
        self.assertEqual(common.segment.tolist(), original.segment.tolist())
        self.assertEqual(common.summary(x)["worst_IL_db"],
                         max(common.il(x)[common.role == 0]))
        self.assertAlmostEqual(common.summary(x)["min_H2_db"],
                               original.summary(x).get("min_H2_db",
                                                      original.summary(x).get("min_h2_db")),
                               places=9)

    def test_exp042_t005_4l_three_variable_c(self):
        policy, vector = exp042.policy_and_seed()
        legacy = exp042.Evaluator(policy, 3)
        common = generic(
            policy, legacy, n_l=4, n_fixed=4, n_var=3, n_ic=0,
            edges=exp042.L_EDGES, pairs=FOUR_PAIRS, q=exp042.Q_C,
        )
        self.check_case(legacy, common, vector)

    def test_exp055_t007_4l_ground_parasitic_or_absent(self):
        policy = load_constraint("RF-T007", allow_trial=True)
        x = np.asarray(json.loads(
            (RUNS / "EXP-055/checkpoints/cv1_input_tip_best.json").read_text()
        )["vector"], float)
        for name, parasitic in (("cv1_input_tip", True), ("two_dtc", False)):
            with self.subTest(name=name, parasitic=parasitic):
                legacy = exp055.Evaluator(policy, 3, name, parasitic)
                common = generic(
                    policy, legacy, n_l=4, n_fixed=4, n_var=3, n_ic=0,
                    edges=legacy.L_edges, pairs=FOUR_PAIRS, q=exp055.Q_C,
                    constant_caps=(0.5 if parasitic else 0.,)
                )
                self.check_case(legacy, common, x)
                # The mutable old source graph is not touched by new API.
                self.assertEqual(exp055.L_EDGES, legacy.L_edges)

    def test_exp058_t008_3l_with_ic_fixed_q60(self):
        policy = load_constraint("RF-T008", allow_trial=True)
        rows = snapshot("rf_t008_exp058_area3_to_3p667_20261020.json",
                        "observed_nondominated")
        for row in rows:
            gjm = 0 if row["GJM_count"] else None
            with self.subTest(gjm=gjm):
                x = np.asarray(row["vector"], float)
                old = exp058_area3.Evaluator(policy, "shunt_output", 3, gjm)
                common = generic(
                    policy, old, n_l=3, n_fixed=3, n_var=2, n_ic=2,
                    edges=exp058_area3.THREE_L_EDGES, pairs=THREE_PAIRS,
                    q=old.Q_C
                )
                self.check_case(old, common, x)

    def test_exp058_t008_4l_no_gjm(self):
        policy = load_constraint("RF-T008", allow_trial=True)
        x = snapshot("rf_t008_exp058_area4_20261020.json", "best_cost_cell")["vector"]
        old = exp058_area4.Evaluator(policy, "shunt_output", "cp", 3)
        common = generic(
            policy, old, n_l=4, n_fixed=3, n_var=2, n_ic=2,
            edges=old.L_edges, pairs=FOUR_PAIRS, q=old.Q_C
        )
        self.check_case(old, common, x)

    def test_exp058_t008_4l_mixed_gjm(self):
        policy = load_constraint("RF-T008", allow_trial=True)
        x = snapshot("rf_t008_exp058_area4p667_20261020.json", "best")["vector"]
        old = exp058_area4l_gjm.Evaluator(policy, "input_output", ("cf0",), 3)
        common = generic(
            policy, old, n_l=4, n_fixed=4, n_var=2, n_ic=2,
            edges=old.L_edges, pairs=FOUR_PAIRS, q=old.Q_C
        )
        self.check_case(old, common, x)

    def test_exp055_alternative_tree_does_not_mutate_other_instances(self):
        policy = load_constraint("RF-T007", allow_trial=True)
        x = np.asarray(json.loads(
            (RUNS / "EXP-055/checkpoints/cv1_input_tip_best.json").read_text()
        )["vector"], float)
        alternate = ((0, 1), (0, 3), (1, 4), (1, 2))
        a = exp055.Evaluator(policy, 3, "cv1_input_tip")
        b = exp055.Evaluator(policy, 3, "cv1_input_tip", l_edges=alternate)
        a0 = a.il(x).copy()
        common = generic(
            policy, b, n_l=4, n_fixed=4, n_var=3, n_ic=0,
            edges=alternate, pairs=FOUR_PAIRS, q=exp055.Q_C,
            constant_caps=(0.5,)
        )
        np.testing.assert_allclose(common.il(x), b.il(x), atol=1e-9, rtol=0)
        np.testing.assert_array_equal(a.il(x), a0)
        self.assertGreater(float(np.max(np.abs(b.il(x) - a0))), 1e-6)

    def test_schema_finite_shape_fixed_state_and_spd_guards(self):
        schema = ParameterVectorSchema(3, 1, 2, 1, 2, (0.5,))
        self.assertEqual(schema.vector_length, 3 + 1 + 2 + 1 + 12)
        with self.assertRaises(ValueError):
            schema.decode(np.zeros(schema.vector_length - 1))
        with self.assertRaises(ValueError):
            schema.decode(np.full(schema.vector_length, np.nan))
        x = np.r_[np.ones(3), .1, 0., 0., .5, np.zeros(12)]
        self.assertEqual(schema.encode(schema.decode(x)).tolist(), x.tolist())
        val = schema.decode(x)
        rows = list(val.capacitors_pf_by_setting)
        rows[1] = (0.2,) + rows[1][1:]
        with self.assertRaises(ValueError):
            schema.encode(CircuitValues(val.inductances_nh, val.coupling_k,
                                        tuple(rows)))
        with self.assertRaises(ValueError):
            CircuitValues((0., 1.), (0.1,), ((0.1,),) * 6)
        t = CoupledLCTopology(
            InductorTree(4, ((0, 1), (1, 2), (1, 3))),
            ((0, 1), (0, 2), (1, 2)),
            (25.,) * 3,
            ((0, 1),),
            (40.,),
        )
        bad = CircuitValues((1., 1., 1.), (0.9, 0.9, 0.9),
                            ((0.1,),) * 6)
        with self.assertRaises(ValueError):
            t.matrices(bad)
        with self.assertRaises(ValueError):
            CoupledLCTopology(
                InductorTree(4, ((0, 1), (1, 2), (1, 3))),
                ((0, 1), (1, 0)), (25.,) * 3,
                ((0, 1),), (40.,),
            )
        with self.assertRaises(ValueError):
            t.node_admittance(val, np.array([-1.]), np.array([0]))


if __name__ == "__main__":
    unittest.main()
