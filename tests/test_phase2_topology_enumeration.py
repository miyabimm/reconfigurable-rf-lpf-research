"""S4A deterministic synthetic topology regressions; no RF/optimization runs."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from lpf.constraint_versions import load_constraint
from lpf.phase2_models.api import build_nominal_circuit
from lpf.phase2_models.circuit_layout import CapacitorPlacement, InductorTree
from lpf.phase2_models.topology_enumeration import (
    TopologySpace, capacitor_choices, enumerate_topologies, exact_candidate_key,
    labelled_trees, nominal_area,
)


def policy(name="RF-T005"):
    return load_constraint(name, allow_trial=True)


def space(n=3, **changes):
    args = dict(trees=(InductorTree(n+1, tuple((0, i) for i in range(1, n+1))),),
                inductor_assignments=(("LQP02HV",)*n,),
                fixed_layouts=(( ((0, 1), "GJM01"), ((1, -1), "PCB_PATTERN_C") ),),
                variable_layouts=(( ((3, -1), "shunt_to_ground"), ((0, 2), "bridge") ),),
                coupling_slot_counts=(n-1,), physical_order_limit=1, max_candidates=1)
    args.update(changes)
    return TopologySpace(**args)


def first(name="RF-T005", n=3):
    report = enumerate_topologies(policy(name), space(n))
    if not report["candidates"]:
        raise AssertionError(report["rejection_reasons"])
    row = report["candidates"][0]
    return build_nominal_circuit(policy(name), row["definition"]), row


class TopologyEnumerationTests(unittest.TestCase):
    def test_all_six_nominal_structures_components_area_and_trial_stamps(self):
        for trial in ("RF-T005", "RF-T007", "RF-T008"):
            for n in (3, 4):
                with self.subTest(trial=trial, n=n):
                    c, row = first(trial, n)
                    values = c.decode(row["representative_vector"])
                    self.assertEqual(len(values.capacitors_pf_by_setting), 6)
                    self.assertEqual(row["nominal_area"]["area_fraction"], f"{3*n+2}/3")
                    self.assertAlmostEqual(row["nominal_area"]["area_units"], n+2/3)
                    self.assertTrue(row["component_check"]["component_policy_pass"])
                    self.assertTrue(row["component_check"]["candidate_promotion_blocked"])
                    self.assertGreater(row["component_check"]["min_L_eigenvalue_H"], 0)
                    self.assertFalse(row["component_check"]["rf_performance_checked"])
                    self.assertEqual(c.schema.constant_caps_pf, (.5,) if trial == "RF-T007" else ())
                    self.assertEqual(c.schema.n_ic_fixed, 2 if trial == "RF-T008" else 0)
                    self.assertEqual(c.topology.capacitor_q[-1], 40 if trial == "RF-T007" else 60 if trial == "RF-T008" else 35)
                    area = row["nominal_area"]
                    self.assertFalse(area["physical_area_verified"])
                    self.assertTrue(area["ic_zero_area_is_nominal_only"])
                    self.assertTrue(all(term["policy_path"] for term in area["terms"]))

    def test_exact_identity_counterexamples_no_unsafe_canonical_merges(self):
        c, row = first("RF-T008")
        d = c.definition
        base = exact_candidate_key(c)
        p = policy("RF-T008")
        variants = [
            replace(d, inductor_tree=replace(d.inductor_tree,
                edges=((1, 0),)+d.inductor_tree.edges[1:])),
            replace(d, inductor_tree=replace(d.inductor_tree, source_node=2, load_node=0)),
            replace(d, physical_order=(2, 1, 0)),
            replace(d, inductor_types=("LQP02HQ",)+d.inductor_types[1:]),
            replace(d, coupling_pairs=tuple(reversed(d.coupling_pairs))),
            replace(d, variable_roles=("shunt_to_ground", "series")),
            replace(d, fixed_c_types=("PCB_PATTERN_C", "GJM01")),
            replace(d, capacitor_placement=replace(d.capacitor_placement,
                fixed_edges=tuple(reversed(d.capacitor_placement.fixed_edges)))),
            replace(d, capacitor_placement=replace(d.capacitor_placement,
                variable_edges=tuple(reversed(d.capacitor_placement.variable_edges)),
                ic_fixed_edges=tuple(reversed(d.capacitor_placement.ic_fixed_edges))),
                variable_roles=tuple(reversed(d.variable_roles))),
            # Internal-node relabelling without an independently proved mapping.
            replace(d, inductor_tree=replace(d.inductor_tree, edges=((0, 3), (0, 2), (0, 1)))),
        ]
        keys = [exact_candidate_key(build_nominal_circuit(p, other)) for other in variants]
        self.assertNotIn(base, keys)
        self.assertEqual(len(set(keys)), len(keys))
        x = list(row["representative_vector"])
        c.validate_components(x)
        k_index = c.schema.n_inductors + c.schema.n_fixed
        x[k_index] = .05
        positive = exact_candidate_key(c, x)
        x[k_index] = -.05
        self.assertNotEqual(positive, exact_candidate_key(c, x))
        c.validate_components(x)
        # Six variable settings and IC-fixed values must all participate.
        original = list(row["representative_vector"])
        full_key = exact_candidate_key(c, original)
        for index in range(len(original)-6*c.schema.n_variable, len(original)):
            changed = original.copy()
            changed[index] += .01
            self.assertNotEqual(full_key, exact_candidate_key(c, changed))
        changed = original.copy()
        changed[k_index+c.schema.n_coupling] += .01
        self.assertNotEqual(full_key, exact_candidate_key(c, changed))
        self.assertNotEqual(base, full_key)
        with self.assertRaises(ValueError):
            exact_candidate_key(c, original[:-1])

    def test_trial_fingerprints_never_merge(self):
        rows = [first(t)[1] for t in ("RF-T005", "RF-T007", "RF-T008")]
        self.assertEqual(len({r["topology_key"] for r in rows}), 3)
        self.assertEqual(len({r["nominal_area"]["policy_sha256"] for r in rows}), 3)
        for name in ("RF-F003", "RF-T006"):
            with self.assertRaisesRegex(ValueError, "Explicit approved"):
                enumerate_topologies(policy(name), space())
        altered = policy()
        altered["components"]["LQP02"]["series"]["LQP02HV"]["q"] = 99
        with self.assertRaisesRegex(ValueError, "approved registry"):
            enumerate_topologies(altered, space())

    def test_series_role_remains_unproven_but_not_a_policy_failure(self):
        s = space(variable_layouts=(( ((0, 2), "series"), ),))
        result = enumerate_topologies(policy(), s)
        row = result["candidates"][0]
        self.assertEqual(result["counts"]["rejected"], 0)
        self.assertFalse(row["connection_role_audit"]["all_declared_roles_supported_by_l_tree"])
        self.assertIn("declared_role_not_proven_by_l_tree", row["component_check"]["promotion_blockers"])
        self.assertTrue(result["candidate_promotion_blocked"])
        self.assertEqual(result["independent_mna"], "not_run")
        self.assertEqual(result["rf_evaluation"], "not_run")

    def test_counts_dedup_bounds_and_axis_order_reproducibility(self):
        trees = labelled_trees(3, limit=2, reverse_edges=True)
        cf = ((), (((0, 1), "GJM01"),), (((0, 0), "GJM01"),))
        cv = ((), (((0, 2), "series"),))
        s = space(trees=trees+trees[:1], fixed_layouts=cf, variable_layouts=cv,
                  coupling_slot_counts=(0, 1), physical_order_limit=2, max_candidates=1000)
        a = enumerate_topologies(policy(), s)
        b = enumerate_topologies(policy(), replace(s, trees=tuple(reversed(s.trees)),
                fixed_layouts=tuple(reversed(cf)), variable_layouts=tuple(reversed(cv)),
                coupling_slot_counts=(1, 0)))
        self.assertEqual(a, b)
        self.assertEqual(a, enumerate_topologies(policy(), s))  # no RNG/seed dependency
        counts = a["counts"]
        self.assertEqual(counts["raw_space"], 3*3*2*4*2)
        self.assertEqual(counts["visited"], counts["raw_space"])
        self.assertEqual(counts["unvisited"], 0)
        self.assertGreater(counts["duplicates"], 0)
        self.assertEqual(counts["rejected"], 3*1*2*4*2)
        self.assertEqual(counts["retained"], counts["visited"]-counts["duplicates"]-counts["rejected"])
        self.assertFalse(a["truncated"])
        bounded = enumerate_topologies(policy(), replace(s, max_candidates=7))
        self.assertEqual(bounded["counts"]["visited"], 7)
        self.assertEqual(bounded["counts"]["unvisited"], counts["raw_space"]-7)
        self.assertTrue(bounded["truncated"])
        self.assertNotEqual(a["space_sha256"], bounded["space_sha256"])
        self.assertFalse(a["exhaustive_topology_search"])
        self.assertTrue(a["overcomplete_equivalence_classes"])

    def test_illegal_branch_and_component_cases_rejected_not_silently_repaired(self):
        bad_spaces = [
            space(fixed_layouts=(( ((0, 0), "GJM01"), ),)),
            space(fixed_layouts=(( ((0, 1), "GJM01"), ((1, 0), "GJM01") ),)),
            space(fixed_layouts=(( ((0, 1), "IC_FIXED_C"), ),)),
            space(variable_layouts=(( ((1, -1), "bridge"), ),)),
            space(variable_layouts=(( ((0, 1), "bridge"), ((1, 0), "bridge") ),)),
            space(variable_layouts=(tuple(((i, -1), "shunt_to_ground") for i in range(4)),)),
            space(4, inductor_assignments=(("PCB_L",)*4,)),
            space(inductor_assignments=(("LQP01",)*3,)),
        ]
        for s in bad_spaces:
            with self.subTest(space=s):
                report = enumerate_topologies(policy(), s)
                self.assertEqual(report["counts"]["retained"], 0)
                self.assertEqual(report["counts"]["rejected"], 1)
                self.assertTrue(report["rejection_reasons"])
        c, row = first()
        d = c.definition
        with self.assertRaises(ValueError):
            build_nominal_circuit(policy(), replace(d, capacitor_placement=replace(
                d.capacitor_placement, ic_fixed_edges=d.capacitor_placement.variable_edges)))
        for edges in (((0, 1), (1, 0), (1, 2)), ((0, 1), (1, 2), (2, 0))):
            with self.assertRaises(ValueError):
                InductorTree(4, edges)
        x = list(row["representative_vector"])
        x[c.schema.n_inductors+c.schema.n_fixed] = .9
        with self.assertRaises(ValueError):
            c.validate_components(x)

    def test_pcb_resource_counts_and_off_not_absence(self):
        result = enumerate_topologies(policy("RF-T008"), space(inductor_assignments=(
            ("LQP02HV", "PCB_L", "PCB_L"),)))
        row = result["candidates"][0]
        self.assertEqual(row["nominal_area"]["area_fraction"], "5/3")
        c = build_nominal_circuit(policy("RF-T008"), row["definition"])
        x = list(row["representative_vector"])
        x[-12:] = [0.]*12
        c.validate_components(x)
        self.assertEqual(nominal_area(c)["counts"]["IC_VARIABLE_C"], 2)
        self.assertEqual(nominal_area(c)["counts"]["IC_FIXED_C"], 2)
        self.assertNotEqual(exact_candidate_key(c, x), row["representative_vector_key"])

    def test_generated_axes_build_isolated_hv_hq_and_role_samples(self):
        for trial in ("RF-T005", "RF-T007", "RF-T008"):
            p = policy(trial)
            s = space(
                trees=labelled_trees(3, limit=2),
                inductor_assignments=(("LQP02HV",)*3, ("LQP02HQ",)*3),
                fixed_layouts=capacitor_choices(4, kind="fixed", max_branches=1, limit=3),
                variable_layouts=capacitor_choices(4, kind="variable", max_branches=1, limit=17),
                coupling_slot_counts=(0,), max_candidates=1000)
            report = enumerate_topologies(p, s)
            self.assertEqual(report["counts"]["retained"], 2*2*3*17)
            self.assertEqual(report["counts"]["rejected"], 0)
            self.assertEqual({role for r in report["candidates"] for role in r["definition"].variable_roles},
                             {"shunt_to_ground", "bridge", "series"})
            hq = next(r for r in report["candidates"] if "LQP02HQ" in r["definition"].inductor_types)
            hv = next(r for r in report["candidates"] if "LQP02HV" in r["definition"].inductor_types)
            self.assertEqual(build_nominal_circuit(p, hq["definition"]).topology.inductor_q, (20.,)*3)
            self.assertEqual(build_nominal_circuit(p, hv["definition"]).topology.inductor_q, (25.,)*3)
            self.assertEqual(report, enumerate_topologies(p, s))

    def test_bounded_helpers_and_input_snapshot(self):
        for n, count in ((3, 16), (4, 125)):
            trees = labelled_trees(n, limit=1000)
            self.assertEqual(len(trees), count)
            self.assertEqual(trees[:2], labelled_trees(n, limit=2))
            self.assertTrue(all(len(t.edges) == n for t in trees))
        for kind in ("fixed", "variable"):
            small = capacitor_choices(4, kind=kind, max_branches=2, limit=5)
            large = capacitor_choices(4, kind=kind, max_branches=2, limit=1000)
            self.assertEqual(small, large[:5])
            self.assertEqual(small[0], ())
            self.assertTrue(any(len(layout) == 2 for layout in large))
        variable = capacitor_choices(4, kind="variable", max_branches=1, limit=100)
        self.assertEqual({label for layout in variable for _, label in layout},
                         {"shunt_to_ground", "bridge", "series"})
        trees = list(labelled_trees(3, limit=1))
        s = space(trees=trees)
        trees.clear()
        self.assertEqual(len(s.trees), 1)
        for kw in ({"max_candidates": 0}, {"physical_order_limit": True},
                   {"trees": ()}, {"coupling_slot_counts": (7,)},
                   {"inductor_assignments": (("LQP02HV",),)}):
            with self.assertRaises(ValueError):
                space(**kw)


if __name__ == "__main__":
    unittest.main()
