"""Compare shared two-port reduction against archived EXP-058 RF-T008 v3.

Only the reduced transfer calculation is shared. Legacy EXP source and the
independent 9x9 branch-current MNA verifier remain unchanged.
"""
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(
    ROOT / "experiments/chatgpt_topology_search/runs/EXP-058"
))

from lpf.constraint_versions import load_constraint
from lpf.twoport_reduction import external_port_il_db
from sweep_area4l_gjm import (
    Evaluator as Legacy4LEvaluator,
    independent_mna,
    inductance,
)

SNAPSHOT = ROOT / "data/pareto_snapshots/rf_t008_exp058_area4p667_20261020.json"


class TwoportReductionTests(unittest.TestCase):
    def test_archived_rft008_four_l_with_external_s2p_and_independent_mna(self):
        snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        self.assertEqual(snapshot["constraint_id"], "RF-T008")
        self.assertEqual(snapshot["revision"], 3)
        self.assertEqual(len(snapshot["best"]["vector"]), 25)
        vector = np.asarray(snapshot["best"]["vector"], dtype=float)
        policy = load_constraint("RF-T008", allow_trial=True)
        ev = Legacy4LEvaluator(policy, "input_output", ("cf0",), 3)
        original = ev.il(vector)

        # The inductor and capacitor physics are constructed by the frozen EXP
        # implementation. Only the shared Schur/ABCD/external S2P stage differs.
        k, _, _, _ = inductance(vector)
        n = len(ev.f)
        y = np.broadcast_to(k, (n, 5, 5)).copy() / (
            ev.omega[:, None, None] * 1e-9
        )
        variable_c = vector[13:].reshape(6, 2)[ev.setting]
        capacitors = np.column_stack((
            np.broadcast_to(vector[4:8], (n, 4)),
            variable_c,
            np.broadcast_to(vector[11:13], (n, 2)),
        ))
        admittance = (
            ev.omega[:, None] * 1e-12 * capacitors
            / (1 / ev.Q_C[None, :] - 1j)
        )
        y += np.einsum(
            "nb,ib,jb->nij", admittance, ev.BC, ev.BC, optimize=True
        )
        shared = external_port_il_db(y, ev.pre, ev.post)
        self.assertEqual(original.shape, shared.shape)
        np.testing.assert_allclose(shared, original, rtol=0, atol=1e-9)

        independent = independent_mna(
            policy, "input_output", ("cf0",), vector
        )
        self.assertTrue(independent["pass"])
        self.assertLess(independent["max_IL_difference_db"], 1e-8)
        self.assertLess(independent["max_power_residual_W"], 1e-9)

    def test_validates_input_shapes_and_ports(self):
        sample = np.eye(3, dtype=complex)[None, :, :]
        twoport = np.eye(2, dtype=complex)[None, :, :]
        with self.assertRaises(ValueError):
            external_port_il_db(sample, twoport[:, :1], twoport)
        with self.assertRaises(ValueError):
            external_port_il_db(sample, twoport, twoport, port_nodes=(0, 0))
        with self.assertRaises(ValueError):
            external_port_il_db(sample, twoport, twoport, source_ohms=0)


if __name__ == "__main__":
    unittest.main()
