"""S4B record/Pareto regressions: synthetic callbacks, no real optimizer."""
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from test_phase2_problem_seed import make, seed
from test_phase2_staged_optimization import status
from lpf.phase2_models.staged_optimization import run_c1_staged
from lpf.phase2_models.candidate_records import (
    CandidateRecord, record_candidate, recheck_record, pareto_report,
)


def provenance():
    return {"kind": "synthetic", "optimizer_kind": "synthetic_callback", "git_head": "a"*40,
            "dirty_patch_sha256": hashlib.sha256(b"synthetic patch").hexdigest(),
            "input_source_sha256": hashlib.sha256(b"synthetic fixture").hexdigest()}


def staged(p, x, codes=(0, 0), source=None):
    initial = seed(p, x)
    codes = iter(codes)
    return run_c1_staged(p.circuit, initial, coarse_points=1, fine_points=2,
        optimize_stage=lambda p, v, m, t: (v, status(next(codes))),
        source_provenance=provenance() if source is None else source)


class CandidateRecordTests(unittest.TestCase):
    def test_enumerated_not_run_and_json_roundtrip_all_trials(self):
        from test_phase2_topology_enumeration import first
        for trial in ("RF-T005", "RF-T007", "RF-T008"):
            for n in (3, 4):
                c, row = first(trial, n)
                r = record_candidate("sample", c, row["representative_vector"])
                body = r.as_dict()
                self.assertEqual(body["numerical"]["state"], "not_run")
                self.assertEqual(body["rf"]["state"], "not_run")
                self.assertEqual(body["validation"]["independent_mna"], "not_run")
                self.assertEqual(len(body["values"]["capacitors_pf_by_setting"]), 6)
                self.assertEqual(CandidateRecord.from_json(r.to_json()).to_json(), r.to_json())
                body["vector"][0] = 999
                self.assertNotEqual(body, r.as_dict())
                self.assertTrue(r.as_dict()["candidate_promotion_blocked"])
                self.assertFalse(r.as_dict()["rf_compliance_certified"])

    def test_staged_seed_attempts_and_separate_fresh_observations(self):
        p, x = make("RF-T008", 4)
        s = staged(p, x)
        original = copy.deepcopy(s)
        r = record_candidate("c2", p.circuit, x, staged_record=s, sampled_points=2)
        b = r.as_dict()
        self.assertEqual(s, original)
        self.assertEqual(b["numerical"]["state"], "converged")
        self.assertEqual(b["staged_record"], json.loads(json.dumps(s)))
        self.assertEqual(b["seed_record"], json.loads(json.dumps(s["seed"])))
        self.assertEqual(b["rf"]["state"], "observed")
        self.assertEqual(b["rf"]["evidence_class"], "forward_only")
        self.assertEqual(b["rf"]["grid"]["sample_count"], 56)
        self.assertEqual(b["rf"]["grid"]["segment_count"], 28)
        self.assertEqual(b["validation"]["power_balance"], "not_run")
        for key in ("dense_rf", "continuous_frequency", "physical", "owner_approval"):
            self.assertEqual(b["validation"][key], "not_run")
        self.assertEqual(b["rf"]["metrics"]["worst_il_db"],
                         s["stage_calls"][-1]["observation"]["sampled_rf"]["worst_il_db"])
        default = record_candidate("c2_default_grid", p.circuit, x, staged_record=s).as_dict()
        self.assertEqual(default["rf"], b["rf"])
        self.assertEqual(default["validation"]["independent_mna"], "not_run")

    def test_epigraph_only_violation_is_recordable_but_not_pareto_eligible(self):
        p, x = make("RF-T008", 4)

        def synthetic_il(evaluator, vector):
            # Deterministic forward boundary, NOT simulated RF performance.
            return np.where(evaluator.role == 0, .25, 36.)

        with patch("lpf.phase2_models.coupled_lc.CoupledLCEvaluator.il", synthetic_il):
            for final_t in (0., .25, .5):
                def callback(problem, vector, maxiter, target):
                    # Coarse is always infeasible; only the final output qualifies.
                    vector[-1] = 0. if problem.points_per_interval == 1 else final_t
                    return vector, status(0)

                s = run_c1_staged(p.circuit, seed(p, x), coarse_points=1, fine_points=2,
                    optimize_stage=callback, source_provenance=provenance())
                self.assertEqual(s["numerical_state"], "converged")
                self.assertTrue(all(c["status"]["success"] for c in s["stage_calls"]))
                observed = s["stage_calls"][-1]["observation"]["sampled_rf"]
                self.assertEqual(observed["passband_epigraph_min_residual_db"], final_t - .25)
                self.assertEqual(observed["h2_min_residual_db"], 6.)
                self.assertEqual(observed["h3_min_residual_db"], 6.)
                self.assertEqual(observed["all_sampled_inequalities_nonnegative"], final_t >= .25)
                r = record_candidate("epigraph", p.circuit, x, staged_record=s)
                checked = recheck_record(CandidateRecord.from_json(r.to_json()))
                self.assertEqual(checked.to_json(), r.to_json())
                self.assertEqual(checked.as_dict()["component"]["state"], "pass")
                report = pareto_report([checked])
                row = report["candidates"][0]
                self.assertEqual(row["metrics"]["worst_il_db"], .25)  # Never t.
                self.assertTrue(row["threshold_observations"]["mandatory_harmonics_met"])
                if final_t < .25:
                    self.assertEqual(row["reasons"], ["final_c2_epigraph_inequality_failed_on_grid"])
                    self.assertIsNone(row["pareto_within_group"])
                    self.assertEqual(report["groups"], [])
                else:
                    self.assertEqual(row["reasons"], [])
                    self.assertTrue(row["pareto_within_group"])
                    self.assertEqual(report["groups"][0]["front"], ["epigraph"])
                self.assertTrue(report["candidate_promotion_blocked"])
                self.assertFalse(report["rf_compliance_certified"])

    def test_restored_observations_never_supply_pass_without_recompute(self):
        p, x = make("RF-T008", 4)
        r = record_candidate("roundtrip", p.circuit, x, staged_record=staged(p, x), sampled_points=2)
        restored = CandidateRecord.from_json(r.to_json())
        report = pareto_report([restored])
        self.assertIn("serialized_evidence_not_rechecked", report["candidates"][0]["reasons"])
        checked = recheck_record(restored)
        self.assertEqual(checked.to_json(), r.to_json())
        tampered = r.as_dict()
        tampered["rf"]["metrics"]["min_h2_db"] = 99.
        with self.assertRaises(ValueError):
            recheck_record(CandidateRecord.from_json(json.dumps(tampered)))

    def test_unconverged_exception_and_invalid_outputs_preserved_not_promoted(self):
        p, x = make("RF-T008", 4)
        unconverged = staged(p, x, (4, 0, 8, 0))
        failed = run_c1_staged(p.circuit, seed(p, x), coarse_points=1, fine_points=2,
            optimize_stage=lambda *a: (_ for _ in ()).throw(RuntimeError("synthetic failure")),
            source_provenance=provenance())
        for name, s in (("unconverged", unconverged), ("failed", failed)):
            r = record_candidate(name, p.circuit, x, staged_record=s, sampled_points=2)
            self.assertEqual(r.as_dict()["staged_record"], json.loads(json.dumps(s)))
            self.assertIn("numerical_"+s["numerical_state"], pareto_report([r])["candidates"][0]["reasons"])
        def bad(p, v, m, t):
            v[0] = float("nan")
            return v, status(0)
        s = run_c1_staged(p.circuit, seed(p, x), coarse_points=1, fine_points=2,
                          optimize_stage=bad, source_provenance=provenance())
        r = record_candidate("bad", p.circuit, x, staged_record=s)
        self.assertEqual(r.as_dict()["staged_record"]["stage_calls"][0]["output_vector"][0], "nan")
        json.loads(r.to_json())

    def diagnostic(self, cid, *, trial="RF-T008", n=4, il=.2, stop=34., points=2, source=None):
        p, x = make(trial, n)
        if n == 3:
            x[6] = 0.  # Non-neighbor nominal slot, not a k relaxation.
        # Synthetic forward boundary for ordering only; keep C2 residuals and
        # recomputed summary consistent, with feasible t on both stage grids.
        def synthetic_il(evaluator, vector):
            return np.where(evaluator.role == 0, il, stop)
        with patch("lpf.phase2_models.coupled_lc.CoupledLCEvaluator.il", synthetic_il):
            s = staged(p, x, source=source)
            return record_candidate(cid, p.circuit, x, staged_record=s, sampled_points=points)

    def test_pareto_equals_tradeoffs_dominance_and_legacy_formula_agree(self):
        from scripts.report_research_pareto import dominates
        records = [self.diagnostic("a", n=3), self.diagnostic("b", il=.1, stop=36),
                   self.diagnostic("c"), self.diagnostic("equal_a", n=3),
                   self.diagnostic("d", il=.3)]
        result = pareto_report(records)
        self.assertEqual(len(result["groups"]), 1)
        self.assertEqual(result["groups"][0]["front"], ["a", "b", "equal_a"])
        rows = {r["candidate_id"]: r for r in result["candidates"]}
        self.assertFalse(rows["c"]["pareto_within_group"])
        self.assertFalse(rows["a"]["threshold_observations"]["nominal_harmonics_met"])
        self.assertTrue(rows["a"]["threshold_observations"]["mandatory_harmonics_met"])
        self.assertTrue(rows["b"]["threshold_observations"]["nominal_harmonics_met"])
        for a in rows.values():
            for b in rows.values():
                old_a = {"chip_area_units": a["area_units"], "worst_il_db": a["metrics"]["worst_il_db"]}
                old_b = {"chip_area_units": b["area_units"], "worst_il_db": b["metrics"]["worst_il_db"]}
                expected = a["area_units"] <= b["area_units"] and old_a["worst_il_db"] <= old_b["worst_il_db"] and (
                    a["area_units"] < b["area_units"] or old_a["worst_il_db"] < old_b["worst_il_db"])
                self.assertEqual(dominates(old_a, old_b), expected)
        self.assertEqual(result, pareto_report(reversed(records)))
        self.assertTrue(result["candidate_promotion_blocked"])
        with self.assertRaises(ValueError):
            pareto_report([records[0], records[0]])

    def test_policy_grid_and_source_classes_never_rank_against_each_other(self):
        records = [self.diagnostic("t005", trial="RF-T005"),
                   self.diagnostic("t007", trial="RF-T007"), self.diagnostic("t008"),
                   self.diagnostic("grid1", points=1),
                   self.diagnostic("other_source", source={**provenance(), "kind": "recorded"}),
                   # Simulated metadata class only, NOT an actual SLSQP run.
                   self.diagnostic("other_optimizer", source={**provenance(), "optimizer_kind": "reported_slsqp"})]
        report = pareto_report(records)
        self.assertEqual(len(report["groups"]), 6)
        self.assertTrue(all(g["count"] == 1 for g in report["groups"]))
        failed = self.diagnostic("stop_fail", stop=29.999)
        nominal_il_fail = self.diagnostic("il_goal_fail", il=.301, stop=30.)
        rows = pareto_report([failed, nominal_il_fail])["candidates"]
        by_id = {r["candidate_id"]: r for r in rows}
        self.assertIn("mandatory_harmonics_failed_on_grid", by_id["stop_fail"]["reasons"])
        self.assertIsNone(by_id["stop_fail"]["pareto_within_group"])
        self.assertTrue(by_id["il_goal_fail"]["pareto_within_group"])
        self.assertFalse(by_id["il_goal_fail"]["threshold_observations"]["nominal_il_met"])
        source = provenance()
        del source["optimizer_kind"]
        missing = self.diagnostic("missing_class", source=source)
        self.assertIn("optimizer_evidence_class_missing", pareto_report([missing])["candidates"][0]["reasons"])

    def test_limited_audit_reuses_independent_evidence_and_rejects_saved_pass(self):
        p, x = make("RF-T008", 4)
        r = record_candidate("limited", p.circuit, x, staged_record=staged(p, x), limited_points=2)
        b = r.as_dict()
        self.assertEqual(b["rf"]["evidence_class"], "limited_independent")
        self.assertEqual(b["validation"]["independent_mna"], "passed_limited")
        self.assertEqual(b["validation"]["power_balance"], "passed_limited")
        self.assertLess(b["audit"]["limited_evidence"]["max_abs_power_residual_w"], 1e-12)
        self.assertEqual(len(b["audit"]["limited_evidence"]["segments"]), 28)
        restored = CandidateRecord.from_json(r.to_json())
        self.assertEqual(recheck_record(restored).to_json(), r.to_json())
        corrupted = b.copy()
        corrupted["audit"] = copy.deepcopy(b["audit"])
        corrupted["audit"]["limited_evidence"]["max_abs_power_residual_w"] = 0.
        if corrupted["audit"] == b["audit"]:
            corrupted["audit"]["limited_evidence"]["max_abs_power_residual_w"] = 1e-15
        with self.assertRaises(ValueError):
            recheck_record(CandidateRecord.from_json(json.dumps(corrupted)))
        with patch("lpf.phase2_models.limited_candidate_evidence.recompute_limited_evidence", side_effect=ValueError("synthetic audit failure")):
            with self.assertRaises(ValueError):
                recheck_record(restored)
            failed = record_candidate("failure", p.circuit, x, limited_points=2)
        self.assertEqual(failed.as_dict()["validation"]["independent_mna"], "failed")
        self.assertIn("independent_validation_failed", pareto_report([failed])["candidates"][0]["reasons"])

    def test_missing_provenance_component_failure_c1_and_series_not_promoted(self):
        p, x = make("RF-T008", 4)
        c1 = seed(p, x)
        r = record_candidate("seed", p.circuit, x, seed_record=c1)
        self.assertEqual(r.as_dict()["numerical"]["vector_binding"], "c1_seed_output")
        reasons = pareto_report([r])["candidates"][0]["reasons"]
        self.assertIn("source_provenance_missing", reasons)
        self.assertIn("numerical_not_run", reasons)
        y = x.copy()
        y[0] += .1
        with self.assertRaises(ValueError):
            record_candidate("bad_seed", p.circuit, y, seed_record=c1)
        y = x.copy()
        y[4] = 0.  # Excluded fixed GJM lower bound, keep complete failing vector.
        r = record_candidate("component_fail", p.circuit, y, sampled_points=2)
        self.assertEqual(r.as_dict()["component"]["state"], "fail")
        self.assertIn("component_not_verified", pareto_report([r])["candidates"][0]["reasons"])
        d = replace(p.circuit.definition, variable_roles=("shunt_to_ground", "series"))
        from lpf.phase2_models.api import build_nominal_circuit
        c = build_nominal_circuit(p.circuit.resolved_policy, d)
        r = record_candidate("series", c, x)
        self.assertIn("declared_role_not_proven_by_l_tree", pareto_report([r])["candidates"][0]["reasons"])

    def test_json_incomplete_six_settings_nonfinite_and_claims_rejected(self):
        p, x = make("RF-T008", 4)
        base = record_candidate("base", p.circuit, x).as_dict()
        mutations = [lambda b: b["values"]["capacitors_pf_by_setting"].pop(),
                     lambda b: b.update(policy_id="RF-T007"),
                     lambda b: b.update(policy_sha256="0"*64),
                     lambda b: b.update(candidate_promotion_blocked=False),
                     lambda b: b.update(rf_compliance_certified=True),
                     lambda b: b["validation"].update(dense_rf="pass"),
                     lambda b: b["validation"].update(independent_mna="passed_limited"),
                     lambda b: b["numerical"].update(state="converged"),
                     lambda b: b["vector"].__setitem__(0, float("nan")),
                     lambda b: b["stamped_topology"]["inductor_q"].__setitem__(0, 99.)]
        for mutate in mutations:
            b = copy.deepcopy(base)
            mutate(b)
            with self.assertRaises(ValueError):
                CandidateRecord.from_json(json.dumps(b))
        with self.assertRaises(ValueError):
            CandidateRecord.from_json('{"schema":"one", "schema":"two"}')

    def test_contradictory_bindings_status_provenance_and_nonfinite_rejected(self):
        p, x = make("RF-T008", 4)
        s = staged(p, x)
        mutations = [lambda d: d.update(policy_id="RF-T007"),
                     lambda d: d.update(policy_fingerprint="0"*64),
                     lambda d: d["stage_calls"][-1]["status"].update(success=False),
                     lambda d: d["attempts"][-1].update(converged=False),
                     lambda d: d["stage_calls"][-1]["observation"]["sampled_rf"].update(min_h2_db=99),
                     lambda d: d.update(numerical_state="failed"),
                     lambda d: d["grids"]["fine"].update(grid_sha256="0"*64)]
        for mutate in mutations:
            changed = copy.deepcopy(s)
            mutate(changed)
            with self.assertRaises(ValueError):
                record_candidate("bad", p.circuit, x, staged_record=changed)
        with self.assertRaises(ValueError):
            record_candidate("bad", p.circuit, x[:-1])
        bad = x.copy()
        bad[0] = float("nan")
        with self.assertRaises(ValueError):
            record_candidate("bad", p.circuit, bad)
        with self.assertRaises(ValueError):
            record_candidate("bad", p.circuit, x, staged_record=s,
                             source_provenance={**provenance(), "input_source_sha256": "0"*64})
        for points in (0, 4, True):
            with self.assertRaises(ValueError):
                record_candidate("bad", p.circuit, x, sampled_points=points)


if __name__ == "__main__":
    unittest.main()
