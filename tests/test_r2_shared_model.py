"""R2 shared policy/model regression; bounded numerical checks, not new optimization."""
import copy
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lpf.legacy_graph_builder import build_grounded_settings, check_graph
from lpf.circuit import Branch, solve
from lpf.configuration import validate_six_settings
from lpf.constraint_versions import load_constraint
from lpf.evaluate import CASES, evaluate_settings
from lpf.independent import solve_gain


def a_graph():
    # Ground=0, IN=1, OUT=2, internals=3,4,5.
    # Fixed path IN-3-OUT, trap node 4 and C branch to 5.
    return (6, ((1, 3, "LQP02HV"), (3, 2, "LQP02HQ"),
                (3, 4, "LQP02HV"), (3, 5, "GJM01")))


def a_values():
    return [1.8e-9, 35e-9, 2.2e-9, .7e-12]


def caps_for(n):
    return [[(.25 + .02 * i) * (j + 1) for j in range(n)]
            for i in range(len(CASES))]


class ExplicitSeriesTests(unittest.TestCase):
    def test_hv_hq_explicit_both_instantiate_and_use_correct_q(self):
        params = build_grounded_settings(a_graph(), a_values(), caps=caps_for(2),
                variable_cap_edges=[(4, 0), (5, 0)], require_explicit_series=True)
        self.assertEqual([x.q for x in params["B71"]["inductors"]], [25, 20, 25])
        self.assertGreater(solve(703e6, **params["B71"])["gain"], 0)
        self.assertTrue(validate_six_settings(params, (1, 2)))

    def test_hv_hq_endpoints_and_legacy_label(self):
        g = (3, ((1, 2, "LQP02HV"),))
        for L in (.4, 27):
            cfg = build_grounded_settings(g, values=[L * 1e-9],
                                          require_explicit_series=True)
            self.assertEqual(cfg["B71"]["inductors"][0].q, 25)
        for L in (.2, 56):
            cfg = build_grounded_settings(
                (3, ((1, 2, "LQP02HQ"),)), values=[L * 1e-9],
                require_explicit_series=True)
            self.assertEqual(cfg["B71"]["inductors"][0].q, 20)
        for label, L in (("LQP02HV", .3), ("LQP02HV", 27.1),
                         ("LQP02HQ", .1), ("LQP02HQ", 56.1)):
            with self.subTest(label=label, L=L), self.assertRaises(ValueError):
                build_grounded_settings(
                    (3, ((1, 2, label),)), values=[L * 1e-9],
                    require_explicit_series=True)
        with self.assertRaises(ValueError):
            check_graph((3, ((1, 2, "LQP02"),)), require_explicit_series=True)
        self.assertEqual(check_graph((3, ((1, 2, "LQP02"),))), 1.0)


class VariablePlacementTests(unittest.TestCase):
    def test_all_three_policies(self):
        formal = load_constraint()
        t1 = load_constraint("RF-T001", allow_trial=True)
        t2 = load_constraint("RF-T002", allow_trial=True)
        formal_settings = build_grounded_settings(
            a_graph(), a_values(), caps=caps_for(2),
            variable_cap_edges=[(4, 0), (5, 0)],
            resolved_policy=formal, require_explicit_series=True)
        all_ground = build_grounded_settings(
            a_graph(), a_values(), caps=caps_for(3),
            variable_cap_edges=[(4, 0), (5, 0), (2, 0)],
            resolved_policy=t1, require_explicit_series=True)
        with_bridge = build_grounded_settings(
            a_graph(), a_values(), caps=caps_for(3),
            variable_cap_edges=[(4, 0), (5, 0), (1, 3)],
            variable_roles=[None, None, "bridge"], resolved_policy=t2,
            require_explicit_series=True)
        for result in (formal_settings, all_ground, with_bridge):
            for name in CASES:
                sol = solve(900e6, **result[name])
                independ = solve_gain(900e6, **result[name])
                self.assertAlmostEqual(sol["gain"], independ, delta=1e-10)
                self.assertLess(abs(sol["power_residual"]), 1e-10)
        self.assertEqual(len(with_bridge["B8"]["capacitors"]),
                         len(formal_settings["B8"]["capacitors"]) + 1)

    def test_wrong_trial_layout_rejected(self):
        t1 = load_constraint("RF-T001", allow_trial=True)
        t2 = load_constraint("RF-T002", allow_trial=True)
        trials = [(t1, [(4, 0), (5, 0), (1, 3)], [None, None, "bridge"]),
                  (t2, [(4, 0), (5, 0), (2, 0)], None),
                  (t2, [(4, 0), (5, 0), (1, 3)], None)]
        for policy, edges, roles in trials:
            with self.subTest(policy=policy["active_constraint_id"], edges=edges, roles=roles):
                with self.assertRaises(ValueError):
                    build_grounded_settings(a_graph(), a_values(), caps_for(3),
                        variable_cap_edges=edges, variable_roles=roles,
                        resolved_policy=policy, require_explicit_series=True)

    def test_bypassed_and_series_only_bridge(self):
        t2 = load_constraint("RF-T002", allow_trial=True)
        broken = (5, ((1, 3, "LQP02HV"), (3, 4, "LQP02HV"),
                      (4, 0, "GJM01")))
        # Fixed graph cannot connect output 2; the variable bridge (4,2)
        # would be the only non-ground signal path, so must be rejected.
        with self.assertRaisesRegex(ValueError, "Bridge cannot"):
            build_grounded_settings(
                broken, [2e-9, 3e-9, .5e-12], caps=caps_for(3),
                variable_cap_edges=[(3, 0), (4, 0), (4, 2)],
                variable_roles=[None, None, "bridge"], resolved_policy=t2,
                require_explicit_series=True)

    def test_six_setting_immutability_nonfinite_and_bounds(self):
        t1 = load_constraint("RF-T001", allow_trial=True)
        cfg = build_grounded_settings(
            a_graph(), a_values(), caps=caps_for(3),
            variable_cap_edges=[(4, 0), (5, 0), (2, 0)],
            resolved_policy=t1, require_explicit_series=True)
        changed = copy.deepcopy(cfg)
        cc = list(changed["B8"]["capacitors"])
        cc[-1] = Branch(cc[-1].a, cc[-1].b, 4.1e-12, cc[-1].q)
        changed["B8"]["capacitors"] = tuple(cc)
        with self.assertRaises(ValueError):
            validate_six_settings(changed, [1, 2, 3], resolved_policy=t1)
        changed = copy.deepcopy(cfg)
        cc = list(changed["B8"]["capacitors"])
        cc[-1] = Branch(cc[-1].a, cc[-1].b, float("nan"), cc[-1].q)
        changed["B8"]["capacitors"] = tuple(cc)
        with self.assertRaises(ValueError):
            validate_six_settings(changed, [1, 2, 3], resolved_policy=t1)
        changed = copy.deepcopy(cfg)
        cc = list(changed["B8"]["capacitors"])
        cc[0] = Branch(cc[0].a, cc[0].b, cc[0].value * 2, cc[0].q)
        changed["B8"]["capacitors"] = tuple(cc)
        with self.assertRaises(ValueError):
            validate_six_settings(changed, [1, 2, 3], resolved_policy=t1)
        changed = copy.deepcopy(cfg)
        cc = list(changed["B8"]["capacitors"])
        cc[-1] = Branch(1, 0, cc[-1].value, cc[-1].q)
        changed["B8"]["capacitors"] = tuple(cc)
        with self.assertRaises(ValueError):
            validate_six_settings(changed, [1, 2, 3], resolved_policy=t1)

    def test_coarse_band_metrics_mna_crosscheck(self):
        t2 = load_constraint("RF-T002", allow_trial=True)
        cfg = build_grounded_settings(
            a_graph(), a_values(), caps=caps_for(3),
            variable_cap_edges=[(4, 0), (5, 0), (1, 3)],
            variable_roles=[None, None, "bridge"], resolved_policy=t2,
            require_explicit_series=True)
        report = evaluate_settings(lambda c: cfg[c], samples_per_segment=3)
        self.assertEqual(set(report["per_case"]), set(CASES))
        self.assertTrue(np.isfinite(report["worst_il_db"][0]))
        self.assertTrue(np.isfinite(report["min_h2_db"][0]))
        self.assertTrue(np.isfinite(report["min_h3_db"][0]))


class HistoricalBaselineAdapterTests(unittest.TestCase):
    def test_saved_lpf007_008_nodal_solve_without_mutating_history(self):
        # Historical regression: source candidates deliberately lack
        # explicit HV/HQ series; NOT RF-F001 physical-series certification.
        for cid in ("LPF-007", "LPF-008"):
            saved = json.loads((ROOT / "candidates" / (cid + ".json")).read_text())
            top = saved["topology"]
            inductors = [Branch(x["a"], x["b"], x["L_nH"] * 1e-9, x["Q"])
                         for x in top["inductors"]]
            fixed = [Branch(x["a"], x["b"], x["C_pF"] * 1e-12, x["Q"])
                     for x in top["fixed_caps"]]
            by_id = {x["id"]: i for i, x in enumerate(top["inductors"])}
            order = saved["chip_physical_order"]
            K = np.eye(len(inductors))
            for (a, b), k in zip(zip(order, order[1:]), saved["neighbor_k_values"]):
                i, j = by_id[a], by_id[b]
                K[i, j] = K[j, i] = k
            all_settings = {}
            for case in CASES:
                variable = [Branch(x["a"], x["b"], value * 1e-12, x["Q"])
                            for x, value in zip(top["variable_caps"],
                            saved["ic_variable_C_pf_by_setting"][case])]
                all_settings[case] = dict(n_nodes=top["n_nodes"],
                    source_node=top["input_node"], load_node=top["output_node"],
                    inductors=tuple(inductors), capacitors=tuple(fixed + variable),
                    coupling=K)
            self.assertTrue(validate_six_settings(
                all_settings, range(len(fixed), len(fixed) + 2),
                resolved_policy=load_constraint('RF-F001')))
            for case in CASES:
                for f in (700e6, 900e6, 1500e6, 2500e6):
                    v = solve(f, **all_settings[case])
                    self.assertAlmostEqual(v["gain"], solve_gain(f, **all_settings[case]),
                                           delta=2e-11)
                    self.assertLess(abs(v["power_residual"]), 1e-10)
            report = evaluate_settings(lambda c: all_settings[c], samples_per_segment=51)
            self.assertLess(abs(report["worst_il_db"][0] -
                                saved["performance"]["worst_IL_db"]), .015)


if __name__ == "__main__":
    unittest.main()
