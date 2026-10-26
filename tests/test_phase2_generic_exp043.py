"""Preserved EXP-043 3L RF-T005 vector versus generic Phase-2 forward solver.

Archived EXP-043 run source is loaded READ-ONLY as an independent historical
parity oracle. New production code never imports it; these are finite-grid
numeric regression checks, not a new RF compliance result.
"""
import importlib.util
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
    CoupledLCTopology, CoupledLCEvaluator, ParameterVectorSchema
)

ARCHIVE = ROOT / "experiments/chatgpt_topology_search/runs/EXP-043"


class EXP043GenericParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "frozen_exp043_search_3l", ARCHIVE / "search_3l.py"
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("EXP-043 frozen source is unavailable")
        source = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(source)
        cls.source = source
        cls.policy = load_constraint("RF-T005", allow_trial=True)

    def test_archived_three_l_variants_use_one_immutable_forward_api(self):
        for filename in ("zero_gjm_double.json", "two_gjm_bridge.json"):
            row = json.loads((ARCHIVE / "checkpoints" / filename).read_text())
            self.assertEqual(row["experiment"], "EXP-043")
            variant = row["variant"]
            types, var_edges = self.source.CONFIGS[variant]
            x = np.asarray(row["vector"], float)
            source = self.source.Evaluator(self.policy, variant, 3)
            topo = CoupledLCTopology(
                InductorTree(4, self.source.L_EDGES),
                ((0, 2), (2, 1)),
                (25., 25., 25.),
                self.source.CF_EDGES + var_edges,
                tuple(80. if t == "GJM" else 40. for t in types)
                + (35., 35., 35.),
            )
            schema = ParameterVectorSchema(3, 3, 2, 0, 3)
            common = CoupledLCEvaluator(self.policy, 3, topo, schema)
            with self.subTest(checkpoint=filename,variant=variant):
                self.assertEqual(x.size, 26)
                np.testing.assert_array_equal(schema.encode(schema.decode(x)), x)
                np.testing.assert_allclose(
                    common.il(x), source.il(x), rtol=0, atol=1e-9
                )
                for key in ("worst_IL_db", "min_H2_db", "min_H3_db"):
                    self.assertAlmostEqual(
                        common.summary(x)[key], source.summary(x)[key],
                        places=9,
                    )
                self.assertEqual(common.role.tolist(), source.role.tolist())
                self.assertEqual(common.setting.tolist(), source.setting.tolist())
                self.assertEqual(common.segment.tolist(), source.segment.tolist())


if __name__ == "__main__":
    unittest.main()
