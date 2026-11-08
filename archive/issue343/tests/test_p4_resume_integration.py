"""Small real-SLSQP interruption/resume test for the P4-A runner."""
import math
import multiprocessing
import json
import os
import signal
import shutil
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "matching_limit"))
import p4_batch


def _args(checkpoint, output, resume=False, resume_run_id=None, max_graphs_per_batch=None):
    return Namespace(
        attempts=1,
        per_bin=1,
        starts=1,
        layouts=1,
        iterations=1,
        coarse_points=2,
        validation_points=3,
        seed=20261011,
        output=str(output),
        checkpoint=str(checkpoint),
        failure_report=None,
        shard_count=1,
        shard_index=0,
        resume=resume,
        resume_run_id=resume_run_id,
        resume_artifact_missing=False,
        max_graphs_per_batch=max_graphs_per_batch,
        max_batch_seconds=None,
    )


def _separate_process_run(checkpoint, output, result_queue, interrupt_after_one=False,
                          resume=False, resume_run_id=None, max_graphs_per_batch=None,
                          interrupt_after_one_candidate=False):
    signal.signal(signal.SIGTERM, p4_batch.handle_termination)
    signal.signal(signal.SIGINT, p4_batch.handle_termination)
    args = _args(checkpoint, output, resume=resume, resume_run_id=resume_run_id,
                 max_graphs_per_batch=max_graphs_per_batch)

    def stop_after_first_completed_unit(payload, _row):
        if interrupt_after_one and len(payload["unit_execution_log"]) == 1:
            os.kill(os.getpid(), signal.SIGTERM)

    def stop_after_first_saved_candidate(payload, candidate):
        if (interrupt_after_one_candidate
                and payload["completed_graph_ids"]
                and candidate["graph_id"] in payload["partial_optimization_runs"]):
            os.kill(os.getpid(), signal.SIGTERM)

    report = p4_batch.run(
        args,
        progress_callback=stop_after_first_completed_unit if interrupt_after_one else None,
        candidate_progress_callback=(
            stop_after_first_saved_candidate if interrupt_after_one_candidate else None
        ),
    )
    result_queue.put({
        "status": report["status"],
        "completed_graph_ids": report["completed_graph_ids"],
        "optimized_graphs": report["optimized_graphs"],
        "completed_optimizer_candidates": report["completed_optimizer_candidates"],
    })


class P4ResumeIntegrationTests(unittest.TestCase):
    def assert_float_lists_close(self, first, second):
        np.testing.assert_allclose(first, second, rtol=1e-9, atol=1e-11)

    def test_runner_history_does_not_change_calculation_compatibility_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            args = _args(Path(directory) / "unused.json", Path(directory) / "unused.out")
            grid = {"B71": [700.0, 710.0]}
            graph_ids = ["a" * 64]
            with mock.patch.dict(os.environ, {"GITHUB_SHA": "commit-one"}):
                first_config = p4_batch.build_run_config(args, grid, graph_ids)
                first_history = p4_batch._execution_metadata()
            with mock.patch.dict(os.environ, {"GITHUB_SHA": "commit-two"}):
                with mock.patch.object(p4_batch.platform, "platform", return_value="another-runner"):
                    second_config = p4_batch.build_run_config(args, grid, graph_ids)
                    second_history = p4_batch._execution_metadata()
            self.assertEqual(
                p4_batch.canonical_config_hash(first_config),
                p4_batch.canonical_config_hash(second_config),
            )
            self.assertNotEqual(first_history["source_commit"], second_history["source_commit"])
            self.assertNotEqual(first_history["platform"], second_history["platform"])

            changed = _args(Path(directory) / "unused.json", Path(directory) / "unused.out")
            changed.iterations += 1
            changed_config = p4_batch.build_run_config(changed, grid, graph_ids)
            self.assertNotEqual(
                p4_batch.canonical_config_hash(first_config),
                p4_batch.canonical_config_hash(changed_config),
            )

    def test_pre_provenance_algorithm_is_not_checkpoint_compatible(self):
        with tempfile.TemporaryDirectory() as directory:
            args = _args(Path(directory) / "unused.json", Path(directory) / "unused.out")
            current = p4_batch.build_run_config(args, {"B71": [700.0, 710.0]}, ["a" * 64])
            previous = dict(current, algorithm_version="p4-a-bounded-sharded-v3")
            self.assertNotEqual(p4_batch.canonical_config_hash(previous),
                                p4_batch.canonical_config_hash(current))

    def test_policy_series_and_layout_changes_reject_checkpoint_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            base=_args(Path(directory)/'unused.json',Path(directory)/'unused.out')
            legacy=p4_batch.build_run_config(base,{'B71':[700.0,710.0]},['a'*64])
            explicit=_args(Path(directory)/'unused.json',Path(directory)/'unused.out')
            explicit.constraint_id='RF-F001';explicit.series_mode='both'
            explicit.max_variable_layouts=4
            explicit.max_topology_graphs=2;explicit.require_lqp02=True
            formal=p4_batch.build_run_config(explicit,{'B71':[700.0,710.0]},['a'*64])
            trial=_args(Path(directory)/'unused.json',Path(directory)/'unused.out')
            trial.constraint_id='RF-T002';trial.series_mode='both'
            trial.max_variable_layouts=4
            trial_config=p4_batch.build_run_config(trial,{'B71':[700.0,710.0]},['a'*64])
            current=_args(Path(directory)/'unused.json',Path(directory)/'unused.out')
            current.constraint_id='RF-F002';current.series_mode='HV'
            current_config=p4_batch.build_run_config(current,{'B71':[700.0,710.0]},['a'*64])
            current_trial=_args(Path(directory)/'unused.json',Path(directory)/'unused.out')
            current_trial.constraint_id='RF-T004';current_trial.series_mode='HV'
            current_trial_config=p4_batch.build_run_config(
                current_trial,{'B71':[700.0,710.0]},['a'*64])
            hashes={p4_batch.canonical_config_hash(x) for x in
                    (legacy,formal,trial_config,current_config,current_trial_config)}
            self.assertEqual(len(hashes),5)
            self.assertEqual(formal['p4_a_limits']['constraint_id'],'RF-F001')
            self.assertEqual(trial_config['p4_a_limits']['constraint_id'],'RF-T002')
            self.assertEqual(current_config['p4_a_limits']['constraint_id'],'RF-F002')
            self.assertEqual(current_trial_config['p4_a_limits']['constraint_id'],'RF-T004')
            self.assertIn('data/constraints/formal/RF-F002.json',
                          current_config['source_fingerprints'])
            self.assertIn('data/constraints/trial/RF-T004.json',
                          current_trial_config['source_fingerprints'])

    def test_new_constraint_search_rejects_legacy_series_alias(self):
        with mock.patch('sys.argv',['p4_batch.py','--constraint-id','RF-F001',
                                   '--series-mode','legacy']):
            with self.assertRaises(SystemExit) as raised:
                p4_batch._parse_args()
        self.assertEqual(raised.exception.code,2)

    def test_cli_rejects_new_search_without_explicit_policy_id(self):
        with mock.patch("sys.argv", ["p4_batch.py"]):
            with self.assertRaises(SystemExit) as raised:
                p4_batch._parse_args()
        self.assertEqual(raised.exception.code, 2)

    def test_cli_rejects_validation_grid_smaller_than_two_points(self):
        with mock.patch("sys.argv", ["p4_batch.py", "--constraint-id", "RF-F002",
                                     "--validation-points", "1"]):
            with self.assertRaises(SystemExit) as raised:
                p4_batch._parse_args()
        self.assertEqual(raised.exception.code, 2)

    def test_validation_exception_marks_graph_and_job_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(p4_batch, "validate", side_effect=ValueError("bad validation grid")):
                report = p4_batch.run(
                    _args(root / "failed.checkpoint.json", root / "failed.json")
                )

            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["results"], [])
            self.assertEqual(report["completed_graph_ids"], [])
            self.assertEqual(len(report["failures"]), 1)
            self.assertEqual(report["failures"][0]["message"], "bad validation grid")
            self.assertEqual(report["unit_execution_log"][0]["status"], "failed")

    def test_one_graph_artifact_batches_resume_to_completion(self):
        if "fork" not in multiprocessing.get_all_start_methods():
            self.skipTest("Artifact batch test requires a POSIX fork-capable runner")
        context = multiprocessing.get_context("fork")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkpoint = root / "run-0" / "checkpoint.json"
            summaries = []
            for batch_index in range(3):
                if batch_index:
                    restored = root / f"downloaded-run-{batch_index}" / "checkpoint.json"
                    restored.parent.mkdir(parents=True)
                    shutil.copy2(checkpoint, restored)
                    checkpoint = restored
                result_queue = context.Queue()
                process = context.Process(
                    target=_separate_process_run,
                    args=(checkpoint, checkpoint.with_name("result.json"), result_queue,
                          False, batch_index > 0,
                          f"run-{batch_index-1}" if batch_index else None, 1),
                )
                process.start()
                process.join(timeout=120)
                if process.is_alive():
                    process.terminate()
                    process.join()
                    self.fail(f"P4-A graph batch {batch_index} exceeded 120 seconds")
                self.assertEqual(process.exitcode, 0)
                summary = result_queue.get(timeout=5)
                summaries.append(summary)
                payload = json.loads(checkpoint.read_text(encoding="utf-8"))
                if batch_index < 2:
                    self.assertEqual(summary["status"], "partial",
                                 msg=payload.get("failures"))
                    self.assertTrue(payload["batch_limit_reached"])
                    self.assertEqual(len(payload["completed_graph_ids"]), batch_index + 1)
                else:
                    self.assertEqual(summary["status"], "completed")
                    self.assertFalse(payload["remaining_graph_ids"])

            final = json.loads(checkpoint.read_text(encoding="utf-8"))
            completed_logs = [item for item in final["unit_execution_log"]
                              if item["status"] == "completed"]
            self.assertEqual(len(completed_logs), 3)
            self.assertEqual(len({item["graph_id"] for item in completed_logs}), 3)
            self.assertEqual(
                [item["graph_id"] for item in completed_logs
                 if item.get("execution_segment_index") == 0],
                [completed_logs[0]["graph_id"]],
            )
            self.assertEqual(len(final["resume_history"]), 2)
            self.assertEqual(final["resume_history"][0]["artifact_run_id"], "run-0")
            self.assertEqual(final["resume_history"][1]["artifact_run_id"], "run-1")

    def test_real_optimizer_sigterm_resume_matches_uninterrupted_run(self):
        if "fork" not in multiprocessing.get_all_start_methods():
            self.skipTest("SIGTERM integration test requires a POSIX fork-capable runner")
        context = multiprocessing.get_context("fork")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = p4_batch.run(_args(root / "baseline.checkpoint.json", root / "baseline.json"))
            self.assertGreaterEqual(len(baseline["completed_graph_ids"]), 2,
                                    msg=baseline.get("failures"))

            interrupted_checkpoint = root / "interrupted.checkpoint.json"
            interrupted_output = root / "interrupted.json"
            result_queue = context.Queue()
            process = context.Process(
                target=_separate_process_run,
                args=(interrupted_checkpoint, interrupted_output, result_queue,
                      False, False, None, None, True),
            )
            process.start()
            process.join(timeout=120)
            if process.is_alive():
                process.terminate()
                process.join()
                self.fail("small P4-A integration run exceeded 120 seconds")
            self.assertEqual(process.exitcode, 0)
            interrupted = result_queue.get(timeout=5)
            self.assertEqual(interrupted["status"], "interrupted")

            saved = p4_batch.load_checkpoint(
                interrupted_checkpoint,
                config_hash=baseline["config_hash"],
                shard_index=0,
                shard_count=1,
                expected_graph_ids=baseline["expected_graph_ids"],
            )
            self.assertGreaterEqual(len(saved["completed_graph_ids"]), 1)
            self.assertLess(len(saved["completed_graph_ids"]), len(saved["expected_graph_ids"]))
            self.assertEqual(saved["status"], "interrupted")
            self.assertEqual(len(saved["partial_optimization_runs"]), 1)
            saved_partial_graph, saved_partial_candidates = next(
                iter(saved["partial_optimization_runs"].items())
            )
            self.assertEqual(len(saved_partial_candidates), 1)
            saved_partial_keys = {
                candidate["candidate_key"] for candidate in saved_partial_candidates
            }
            self.assertNotIn("in_flight_candidate_attempt", saved)
            saved_before_resume = set(saved["completed_graph_ids"])

            downloaded_artifact = root / "downloaded-artifact" / "checkpoint.json"
            downloaded_artifact.parent.mkdir(parents=True)
            shutil.copy2(interrupted_checkpoint, downloaded_artifact)

            resume_queue = context.Queue()
            resume_process = context.Process(
                target=_separate_process_run,
                args=(downloaded_artifact, root / "resumed.json", resume_queue,
                      False, True, "source-run-123"),
            )
            resume_process.start()
            resume_process.join(timeout=120)
            if resume_process.is_alive():
                resume_process.terminate()
                resume_process.join()
                self.fail("small P4-A resume exceeded 120 seconds")
            self.assertEqual(resume_process.exitcode, 0)
            resumed_summary = resume_queue.get(timeout=5)
            self.assertEqual(resumed_summary["status"], "completed")

            resumed = p4_batch.load_checkpoint(
                downloaded_artifact,
                config_hash=baseline["config_hash"],
                shard_index=0,
                shard_count=1,
                expected_graph_ids=baseline["expected_graph_ids"],
            )
            self.assertEqual(set(resumed["completed_graph_ids"]), set(baseline["expected_graph_ids"]))
            self.assertEqual(resumed["resume_count"], 1)
            self.assertEqual(len(resumed["execution_history"]), 2)
            self.assertEqual(resumed["resume_history"][0]["artifact_run_id"], "source-run-123")
            resumed_candidate_log = resumed["candidate_execution_log"]
            resumed_segment_candidates = {
                item["candidate_key"] for item in resumed_candidate_log
                if item.get("execution_segment_index") == 1
            }
            self.assertTrue(saved_partial_keys.isdisjoint(resumed_segment_candidates))
            self.assertIn(
                saved_partial_graph,
                {item["graph_id"] for item in resumed_candidate_log
                 if item.get("execution_segment_index") == 0},
            )

            baseline_rows = {row["graph_id"]: row for row in baseline["results"]}
            resumed_rows = {row["graph_id"]: row for row in resumed["results"]}
            self.assertEqual(set(baseline_rows), set(resumed_rows))
            self.assertEqual(len(baseline_rows), len(baseline["results"]))
            self.assertEqual(len(resumed_rows), len(resumed["results"]))
            for graph_id, baseline_row in baseline_rows.items():
                resumed_row = resumed_rows[graph_id]
                self.assertEqual(baseline_row["optimization_seed"], resumed_row["optimization_seed"])
                self.assertEqual(baseline_row["best_candidate_key"], resumed_row["best_candidate_key"])
                self.assertEqual(baseline_row["converged"], resumed_row["converged"])
                self.assert_float_lists_close(baseline_row["values"], resumed_row["values"])
                self.assertTrue(math.isclose(
                    baseline_row["coarse_il_db"], resumed_row["coarse_il_db"],
                    rel_tol=1e-9, abs_tol=1e-11,
                ))
                self.assertEqual(len(baseline_row["optimization_runs"]),
                                 len(resumed_row["optimization_runs"]))
                for base_candidate, resumed_candidate in zip(
                    baseline_row["optimization_runs"], resumed_row["optimization_runs"]
                ):
                    self.assertEqual(base_candidate["rng_seed"], resumed_candidate["rng_seed"])
                    self.assertEqual(base_candidate["candidate_key"], resumed_candidate["candidate_key"])
                    self.assertEqual(base_candidate["objective_evaluation_count"],
                                     resumed_candidate["objective_evaluation_count"])
                    self.assert_float_lists_close(base_candidate["initial_values"],
                                                  resumed_candidate["initial_values"])
                    self.assert_float_lists_close(base_candidate["result_values"],
                                                  resumed_candidate["result_values"])
                    self.assertTrue(math.isclose(
                        base_candidate["coarse_il_db"], resumed_candidate["coarse_il_db"],
                        rel_tol=1e-9, abs_tol=1e-11,
                    ))

            baseline_log = [entry["graph_id"] for entry in baseline["unit_execution_log"]]
            resumed_log = [entry["graph_id"] for entry in resumed["unit_execution_log"]]
            self.assertEqual(len(baseline_log), len(set(baseline_log)))
            self.assertEqual(len(resumed_log), len(set(resumed_log)))
            self.assertEqual(set(resumed_log), set(baseline_log))
            self.assertTrue(saved_before_resume.issubset(set(resumed_log)))
            resumed_segment_graphs = {
                item["graph_id"] for item in resumed["unit_execution_log"]
                if item.get("execution_segment_index") == 1
            }
            self.assertEqual(
                resumed_segment_graphs,
                set(resumed["expected_graph_ids"]) - saved_before_resume,
            )
            self.assertEqual(
                baseline["completed_optimizer_candidates"],
                resumed["completed_optimizer_candidates"],
            )
            baseline_candidate_keys = [
                candidate["candidate_key"]
                for row in baseline["results"] for candidate in row["optimization_runs"]
            ]
            resumed_candidate_keys = [
                candidate["candidate_key"]
                for row in resumed["results"] for candidate in row["optimization_runs"]
            ]
            self.assertEqual(len(baseline_candidate_keys), len(set(baseline_candidate_keys)))
            self.assertEqual(len(resumed_candidate_keys), len(set(resumed_candidate_keys)))
            self.assertEqual(set(resumed_candidate_keys), set(baseline_candidate_keys))
            saved_before_candidate_keys = {
                item["candidate_key"] for item in saved["candidate_execution_log"]
            }
            self.assertTrue(saved_before_candidate_keys.issubset(set(resumed_candidate_keys)))
            self.assertEqual(
                len(resumed_candidate_log),
                len({item["candidate_key"] for item in resumed_candidate_log}),
            )
            self.assertEqual(
                sum(item["objective_evaluation_count"] for item in baseline["unit_execution_log"]),
                sum(item["objective_evaluation_count"] for item in resumed["unit_execution_log"]),
            )


if __name__ == "__main__":
    unittest.main()
