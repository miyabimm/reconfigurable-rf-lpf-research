"""Deterministic P4-A shard IDs, atomic checkpoints, and completeness checks."""
from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
import sys

_SRC = str(Path(__file__).resolve().parents[2] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
from lpf.checkpoint_io import canonical_config_hash, atomic_write_json  # noqa: E402


CHECKPOINT_SCHEMA_VERSION = 2
MAX_SHARDS = 64


class CheckpointError(ValueError):
    """Base class for checkpoints that cannot safely be consumed."""


class CheckpointCorruptError(CheckpointError):
    """The checkpoint bytes or internal result state are malformed."""


class CheckpointCompatibilityError(CheckpointError):
    """The checkpoint is valid but does not match the requested calculation."""


def _is_graph_id(value):
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        bytes.fromhex(value)
    except ValueError:
        return False
    return True


def _canonical_edges(graph):
    node_count, edges = graph
    node_count = int(node_count)
    if node_count < 3:
        raise ValueError("A grounded graph needs ground, input, and output nodes")

    normalized = []
    for edge in edges:
        if len(edge) != 3:
            raise ValueError("Every graph edge must have two nodes and a component type")
        a, b, component = int(edge[0]), int(edge[1]), str(edge[2])
        if a == b or not (0 <= a < node_count and 0 <= b < node_count):
            raise ValueError("Graph edge contains an invalid node")
        normalized.append((a, b, component))

    best = None
    internal_nodes = range(3, node_count)
    for permutation in itertools.permutations(internal_nodes):
        mapping = {0: 0, 1: 1, 2: 2}
        mapping.update(zip(internal_nodes, permutation))
        mapped = tuple(sorted(
            (min(mapping[a], mapping[b]), max(mapping[a], mapping[b]), component)
            for a, b, component in normalized
        ))
        if best is None or mapped < best:
            best = mapped
    return node_count, best or ()


def canonical_graph_id(graph) -> str:
    """Return a process-independent SHA-256 ID, invariant to internal labels."""
    node_count, edges = _canonical_edges(graph)
    payload = {"node_count": node_count, "edges": [list(edge) for edge in edges]}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def shard_for_graph(graph_id: str, shard_count: int) -> int:
    """Assign a graph to a shard using its stable ID, never Python's hash()."""
    if not 1 <= shard_count <= MAX_SHARDS:
        raise ValueError(f"shard_count must be between 1 and {MAX_SHARDS}")
    if not _is_graph_id(graph_id):
        raise ValueError("graph_id must be a SHA-256 hex digest")
    digest = bytes.fromhex(graph_id)
    return int.from_bytes(digest[:8], "big") % shard_count


def load_checkpoint(path, *, config_hash, shard_index, shard_count, expected_graph_ids):
    """Load a compatible checkpoint or reject stale/corrupt resume state."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Resume checkpoint not found: {source}")
    try:
        checkpoint = json.loads(source.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CheckpointCorruptError(f"Invalid checkpoint JSON: {source}") from exc
    if not isinstance(checkpoint, dict):
        raise CheckpointCorruptError("Checkpoint root must be a JSON object")
    if checkpoint.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
        raise CheckpointCompatibilityError("Unsupported checkpoint schema version")
    expected = list(expected_graph_ids)
    checks = {
        "config_hash": config_hash,
        "shard_index": shard_index,
        "shard_count": shard_count,
        "expected_graph_ids": expected,
    }
    for key, value in checks.items():
        if checkpoint.get(key) != value:
            raise CheckpointCompatibilityError(f"Checkpoint {key} does not match this run")
    if checkpoint.get("status") not in {
        "running", "interrupted", "partial", "completed", "failed"
    }:
        raise CheckpointCorruptError("Checkpoint has an invalid status")
    results = checkpoint.get("results")
    completed = checkpoint.get("completed_graph_ids")
    if not isinstance(results, list) or not isinstance(completed, list):
        raise CheckpointCorruptError("Checkpoint result state is malformed")
    result_ids = [row.get("graph_id") for row in results if isinstance(row, dict)]
    if (len(result_ids) != len(results)
            or any(not _is_graph_id(graph_id) for graph_id in result_ids)
            or any(not _is_graph_id(graph_id) for graph_id in completed)
            or len(result_ids) != len(set(result_ids))
            or len(completed) != len(set(completed))):
        raise CheckpointCorruptError("Checkpoint has malformed or duplicate graph results")
    if set(result_ids) - set(expected) or sorted(result_ids) != sorted(completed):
        raise CheckpointCorruptError("Checkpoint results do not match its completed graph IDs")
    if checkpoint["status"] == "completed" and set(result_ids) != set(expected):
        raise CheckpointCorruptError("Completed checkpoint is missing expected graph results")
    optimizer_keys = []
    for row in results:
        runs = row.get("optimization_runs")
        if not isinstance(runs, list):
            raise CheckpointCorruptError("Checkpoint optimization run list is malformed")
        for optimization_run in runs:
            if not isinstance(optimization_run, dict):
                raise CheckpointCorruptError("Checkpoint optimization candidate is malformed")
            candidate_key = optimization_run.get("candidate_key")
            if (not isinstance(candidate_key, str)
                    or not candidate_key.startswith(row["graph_id"] + ":")):
                raise CheckpointCorruptError("Checkpoint optimization candidate key is malformed")
            optimizer_keys.append(candidate_key)
    partial_runs = checkpoint.get("partial_optimization_runs")
    if not isinstance(partial_runs, dict):
        raise CheckpointCorruptError("Checkpoint partial optimization state is malformed")
    for graph_id, graph_runs in partial_runs.items():
        if (not _is_graph_id(graph_id) or graph_id not in expected or graph_id in completed
                or not isinstance(graph_runs, list)):
            raise CheckpointCorruptError("Checkpoint partial graph state is malformed")
        for optimization_run in graph_runs:
            if not isinstance(optimization_run, dict) or optimization_run.get("graph_id") != graph_id:
                raise CheckpointCorruptError("Checkpoint partial candidate is malformed")
            candidate_key = optimization_run.get("candidate_key")
            if (not isinstance(candidate_key, str)
                    or not candidate_key.startswith(graph_id + ":")):
                raise CheckpointCorruptError("Checkpoint partial candidate key is malformed")
            optimizer_keys.append(candidate_key)
    if len(optimizer_keys) != len(set(optimizer_keys)):
        raise CheckpointCorruptError("Checkpoint contains duplicate optimizer candidates")
    candidate_log = checkpoint.get("candidate_execution_log")
    if not isinstance(candidate_log, list) or any(not isinstance(item, dict) for item in candidate_log):
        raise CheckpointCorruptError("Checkpoint candidate execution log is malformed")
    logged_candidate_keys = [item.get("candidate_key") for item in candidate_log
                             if item.get("status") == "completed"]
    if (len(logged_candidate_keys) != len(candidate_log)
            or any(not isinstance(key, str) for key in logged_candidate_keys)
            or len(logged_candidate_keys) != len(set(logged_candidate_keys))
            or set(logged_candidate_keys) != set(optimizer_keys)):
        raise CheckpointCorruptError("Checkpoint candidate log does not match saved optimizer results")
    in_flight = checkpoint.get("in_flight_candidate_attempt")
    if in_flight is not None:
        graph_id = in_flight.get("graph_id") if isinstance(in_flight, dict) else None
        key = in_flight.get("candidate_key") if isinstance(in_flight, dict) else None
        if (graph_id not in expected or graph_id in completed
                or not isinstance(key, str) or not key.startswith(graph_id + ":")
                or key in optimizer_keys):
            raise CheckpointCorruptError("Checkpoint in-flight candidate state is malformed")
    run_config = checkpoint.get("run_config")
    if not isinstance(run_config, dict):
        raise CheckpointCorruptError("Checkpoint is missing its compatibility configuration")
    if canonical_config_hash(run_config) != config_hash:
        raise CheckpointCorruptError("Checkpoint configuration hash is internally inconsistent")
    global_expected = checkpoint.get("global_expected_graph_ids")
    topology_search = run_config.get("topology_search")
    if (not isinstance(global_expected, list)
            or any(not _is_graph_id(value) for value in global_expected)
            or len(global_expected) != len(set(global_expected))
            or not isinstance(topology_search, dict)
            or topology_search.get("selected_graph_ids") != global_expected
            or not set(expected).issubset(global_expected)):
        raise CheckpointCorruptError("Checkpoint global graph assignment is malformed")
    unit_log = checkpoint.get("unit_execution_log")
    if not isinstance(unit_log, list) or any(not isinstance(item, dict) for item in unit_log):
        raise CheckpointCorruptError("Checkpoint execution log is malformed")
    completed_log_ids = [item.get("graph_id") for item in unit_log
                         if item.get("status") == "completed"]
    if (any(not _is_graph_id(value) for value in completed_log_ids)
            or len(completed_log_ids) != len(set(completed_log_ids))
            or set(completed_log_ids) != set(completed)):
        raise CheckpointCorruptError("Checkpoint execution log does not match completed graphs")
    execution_history = checkpoint.get("execution_history")
    if (not isinstance(execution_history, list) or not execution_history
            or any(not isinstance(item, dict) for item in execution_history)):
        raise CheckpointCorruptError("Checkpoint execution history is malformed")
    source_commits = checkpoint.get("source_commits")
    if not isinstance(source_commits, list) or any(not isinstance(item, str) for item in source_commits):
        raise CheckpointCorruptError("Checkpoint source commit history is malformed")
    interrupted_attempts = checkpoint.get("interrupted_candidate_attempts")
    if (not isinstance(interrupted_attempts, list)
            or any(not isinstance(item, dict) for item in interrupted_attempts)):
        raise CheckpointCorruptError("Checkpoint interrupted candidate history is malformed")
    return checkpoint


def aggregate_checkpoints(checkpoint_paths, expected_shards, matrix_result="success",
                           failure_paths=()):
    """Aggregate shard artifacts while distinguishing progress and failure states."""
    if not 1 <= expected_shards <= MAX_SHARDS:
        raise ValueError(f"expected_shards must be between 1 and {MAX_SHARDS}")

    errors = []
    corrupt_paths = []
    shards = {}
    for path in sorted(map(Path, checkpoint_paths)):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            errors.append(f"invalid_checkpoint:{path}")
            corrupt_paths.append(str(path))
            continue
        if not isinstance(payload, dict):
            errors.append(f"invalid_checkpoint:{path}")
            corrupt_paths.append(str(path))
            continue
        index = payload.get("shard_index")
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < expected_shards:
            errors.append(f"invalid_shard_index:{path}")
            corrupt_paths.append(str(path))
            continue
        if index in shards:
            errors.append(f"duplicate_shard:{index}")
            corrupt_paths.append(str(path))
            continue
        shards[index] = payload

    missing = sorted(set(range(expected_shards)) - set(shards))
    config_hashes = set()
    source_commits = set()
    expected_ids = []
    result_rows = []
    shard_states = {
        index: {"status": "not_run", "reason": "checkpoint_artifact_missing"}
        for index in missing
    }
    for failure_path in sorted(map(Path, failure_paths)):
        try:
            failure = json.loads(failure_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            errors.append(f"invalid_failure_report:{failure_path}")
            corrupt_paths.append(str(failure_path))
            continue
        if not isinstance(failure, dict):
            errors.append(f"invalid_failure_report:{failure_path}")
            corrupt_paths.append(str(failure_path))
            continue
        index = failure.get("shard_index")
        state = failure.get("state")
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < expected_shards:
            errors.append(f"invalid_failure_report_shard:{failure_path}")
            corrupt_paths.append(str(failure_path))
            continue
        if state not in {"failed", "incompatible", "corrupt", "not_run"}:
            errors.append(f"invalid_failure_report_state:{index}")
            corrupt_paths.append(str(failure_path))
            continue
        shard_states[index] = {
            "status": state,
            "reason": failure.get("message", "failure report recorded"),
        }
        if state == "incompatible":
            errors.append(f"incompatible_shard:{index}")
        elif state == "corrupt":
            errors.append(f"corrupt_shard:{index}")
        elif state == "failed":
            errors.append(f"failed_shard:{index}")
        elif state == "not_run":
            errors.append(f"shard_not_run:{index}")
    if matrix_result != "success":
        errors.append(f"matrix_job_result:{matrix_result}")

    global_expected_sets = []
    for index, payload in sorted(shards.items()):
        state = payload.get("status")
        previous_state = shard_states.get(index)
        if previous_state and previous_state.get("status") in {
            "failed", "incompatible", "corrupt", "not_run"
        }:
            shard_states[index] = {
                **previous_state,
                "checkpoint_status": state if isinstance(state, str) else "corrupt",
            }
        else:
            shard_states[index] = {"status": state if isinstance(state, str) else "corrupt"}
        partial_candidate_total = None
        partial_state_for_summary = payload.get("partial_optimization_runs", {})
        if isinstance(partial_state_for_summary, dict):
            partial_candidate_total = 0
            for records in partial_state_for_summary.values():
                if isinstance(records, list):
                    partial_candidate_total += len(records)
        shard_states[index].update({
            "completed_graphs": len(payload.get("completed_graph_ids", []))
            if isinstance(payload.get("completed_graph_ids"), list) else None,
            "expected_graphs": len(payload.get("expected_graph_ids", []))
            if isinstance(payload.get("expected_graph_ids"), list) else None,
            "batch_stop_reason": payload.get("batch_stop_reason"),
            "resume_recovery": payload.get("resume_recovery", []),
            "partial_optimizer_candidates": partial_candidate_total,
        })
        if payload.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
            errors.append(f"unsupported_checkpoint_schema:{index}")
        shard_count = payload.get("shard_count")
        if isinstance(shard_count, bool) or not isinstance(shard_count, int) or shard_count != expected_shards:
            errors.append(f"shard_count_mismatch:{index}")
        config_value = payload.get("config_hash")
        source_value = payload.get("source_commit")
        if isinstance(config_value, str) and config_value:
            config_hashes.add(config_value)
        if isinstance(source_value, str) and source_value:
            source_commits.add(source_value)
        commit_history = payload.get("source_commits", [])
        if isinstance(commit_history, list):
            source_commits.update(value for value in commit_history
                                  if isinstance(value, str) and value)
        execution_history = payload.get("execution_history", [])
        if isinstance(execution_history, list):
            source_commits.update(
                segment.get("source_commit") for segment in execution_history
                if isinstance(segment, dict)
                and isinstance(segment.get("source_commit"), str)
                and segment.get("source_commit")
            )
        run_config = payload.get("run_config")
        if not isinstance(run_config, dict):
            errors.append(f"missing_compatibility_config:{index}")
        elif config_value != canonical_config_hash(run_config):
            errors.append(f"invalid_config_hash:{index}")

        global_expected = payload.get("global_expected_graph_ids")
        if not isinstance(global_expected, list) or any(
            not _is_graph_id(graph_id) for graph_id in global_expected
        ):
            errors.append(f"malformed_global_expected_graph_ids:{index}")
        else:
            global_expected_sets.append(tuple(global_expected))
            topology_search = run_config.get("topology_search") if isinstance(run_config, dict) else None
            if (not isinstance(topology_search, dict)
                    or topology_search.get("selected_graph_ids") != global_expected):
                errors.append(f"global_expected_config_mismatch:{index}")

        shard_expected = payload.get("expected_graph_ids")
        rows = payload.get("results")
        completed = payload.get("completed_graph_ids")
        if not isinstance(shard_expected, list) or not isinstance(rows, list) or not isinstance(completed, list):
            errors.append(f"malformed_checkpoint:{index}")
            continue
        if any(not _is_graph_id(graph_id) for graph_id in shard_expected):
            errors.append(f"malformed_expected_graph_ids:{index}")
            continue
        if any(not _is_graph_id(graph_id) for graph_id in completed):
            errors.append(f"malformed_completed_graph_ids:{index}")
            continue
        if len(shard_expected) != len(set(shard_expected)):
            errors.append(f"duplicate_expected_graph:{index}")
        expected_ids.extend(shard_expected)

        valid_rows = [row for row in rows if isinstance(row, dict)
                      and _is_graph_id(row.get("graph_id"))]
        row_ids = [row["graph_id"] for row in valid_rows]
        if len(row_ids) != len(rows) or len(row_ids) != len(set(row_ids)):
            errors.append(f"duplicate_or_malformed_result:{index}")
        if set(row_ids) - set(shard_expected) or sorted(row_ids) != sorted(completed):
            errors.append(f"result_graph_id_mismatch:{index}")
        if state not in {"running", "interrupted", "partial", "completed", "failed"}:
            errors.append(f"invalid_shard_status:{index}")
        if state == "completed" and set(row_ids) != set(shard_expected):
            errors.append(f"completed_shard_missing_results:{index}")
        if state == "failed":
            errors.append(f"failed_shard:{index}")

        optimization_keys = []
        for row in valid_rows:
            runs = row.get("optimization_runs", [])
            if not isinstance(runs, list):
                errors.append(f"malformed_optimization_runs:{index}")
                continue
            for optimization_run in runs:
                if not isinstance(optimization_run, dict):
                    errors.append(f"malformed_optimization_run:{index}")
                    continue
                candidate_key = optimization_run.get("candidate_key")
                if (optimization_run.get("graph_id") != row["graph_id"]
                        or not isinstance(candidate_key, str)
                        or not candidate_key.startswith(row["graph_id"] + ":")):
                    errors.append(f"malformed_optimization_candidate:{index}")
                optimization_keys.append((
                    row["graph_id"], candidate_key if isinstance(candidate_key, str) else None
                ))

        partial_runs = payload.get("partial_optimization_runs")
        if not isinstance(partial_runs, dict):
            errors.append(f"malformed_partial_optimization_state:{index}")
            partial_runs = {}
        for graph_id, runs in partial_runs.items():
            if (not _is_graph_id(graph_id) or graph_id not in shard_expected
                    or graph_id in completed or not isinstance(runs, list)):
                errors.append(f"malformed_partial_graph_state:{index}")
                continue
            for optimization_run in runs:
                if not isinstance(optimization_run, dict):
                    errors.append(f"malformed_partial_optimization_run:{index}")
                    continue
                candidate_key = optimization_run.get("candidate_key")
                if (optimization_run.get("graph_id") != graph_id
                        or not isinstance(candidate_key, str)
                        or not candidate_key.startswith(graph_id + ":")):
                    errors.append(f"malformed_partial_candidate:{index}")
                optimization_keys.append((
                    graph_id, candidate_key if isinstance(candidate_key, str) else None
                ))
        if len(optimization_keys) != len(set(optimization_keys)):
            errors.append(f"duplicate_optimization_candidate:{index}")
        candidate_log = payload.get("candidate_execution_log")
        if not isinstance(candidate_log, list):
            errors.append(f"malformed_candidate_execution_log:{index}")
        else:
            logged = [item.get("candidate_key") for item in candidate_log
                      if isinstance(item, dict) and item.get("status") == "completed"]
            if (len(logged) != len(candidate_log)
                    or any(not isinstance(key, str) for key in logged)
                    or len(logged) != len(set(logged))
                    or set(logged) != {key for _graph, key in optimization_keys}):
                errors.append(f"candidate_log_result_mismatch:{index}")
        result_rows.extend(valid_rows)

    if len(expected_ids) != len(set(expected_ids)):
        errors.append("graph_assigned_to_multiple_shards")
    if len(config_hashes) != 1:
        errors.append("missing_or_mixed_config_hashes")
    if len(config_hashes) > 1:
        errors.append("mixed_config_hashes")
    if len(global_expected_sets) > 1 and len(set(global_expected_sets)) > 1:
        errors.append("mixed_global_expected_graph_ids")
    global_expected = list(global_expected_sets[0]) if global_expected_sets else []
    if global_expected and len(global_expected) != len(set(global_expected)):
        errors.append("duplicate_global_expected_graph_id")
    if expected_ids and sorted(expected_ids) != sorted(global_expected):
        errors.append("shard_assignment_missing_or_extra_graphs")
    if global_expected and len(shards) == expected_shards:
        for graph_id in global_expected:
            assigned = [index for index, payload in shards.items()
                        if graph_id in payload.get("expected_graph_ids", [])]
            if len(assigned) != 1:
                errors.append("graph_assignment_count_mismatch")
            elif assigned[0] != shard_for_graph(graph_id, expected_shards):
                errors.append("graph_assigned_to_wrong_shard")
    all_result_ids = [row.get("graph_id") for row in result_rows if isinstance(row, dict)]
    if len(all_result_ids) != len(set(all_result_ids)):
        errors.append("duplicate_aggregated_graph_result")
    partial_candidate_count = 0
    for payload in shards.values():
        partial_state = payload.get("partial_optimization_runs")
        if isinstance(partial_state, dict):
            partial_candidate_count += sum(
                len(records) for records in partial_state.values() if isinstance(records, list)
            )

    unique_errors = sorted(set(errors))
    incompatible = (len(config_hashes) > 1 or any(
        error.startswith(("mixed_config_hashes", "incompatible_shard:",
                          "shard_count_mismatch:", "graph_assigned_to_wrong_shard"))
        for error in unique_errors
    ))
    corrupt = bool(corrupt_paths) or any(
        "malformed" in error or "invalid_checkpoint" in error
        or "invalid_failure_report" in error or "unsupported_checkpoint_schema" in error
        or error.startswith(("missing_or_mixed_config_hashes",
                             "missing_compatibility_config:", "invalid_config_hash:"))
        or error.startswith(("corrupt_shard:", "duplicate_shard:", "invalid_shard_index:"))
        or error.startswith(("global_expected_config_mismatch:",
                             "graph_assigned_to_multiple_shards",
                             "duplicate_expected_graph:",
                             "duplicate_aggregated_graph_result",
                             "duplicate_or_malformed_result:",
                             "result_graph_id_mismatch:",
                             "completed_shard_missing_results:"))
        or (error == "shard_assignment_missing_or_extra_graphs" and not missing)
        for error in unique_errors
    )
    failed = matrix_result != "success" or any(
        error.startswith(("failed_shard:", "matrix_job_result:")) for error in unique_errors
    )
    complete = (
        not unique_errors
        and not missing
        and len(shards) == expected_shards
        and all(payload.get("status") == "completed" for payload in shards.values())
    )
    if complete:
        status = "completed"
    elif incompatible:
        status = "incompatible"
    elif corrupt:
        status = "corrupt"
    elif failed:
        status = "failed"
    elif missing:
        status = "incomplete"
    elif any(error.startswith("shard_not_run:") for error in unique_errors):
        status = "incomplete"
    else:
        status = "in_progress"
    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "status": status,
        "overall_complete": complete,
        "search_claim": "bounded_seeded_sample_not_exhaustive_or_global_optimum",
        "expected_shards": expected_shards,
        "received_shards": sorted(shards),
        "missing_shards": missing,
        "shard_states": shard_states,
        "corrupt_checkpoint_paths": corrupt_paths,
        "selected_graphs": len(global_expected) if global_expected else len(expected_ids),
        "missing_graph_assignments": sorted(set(global_expected)-set(expected_ids)),
        "missing_graph_results": sorted(set(global_expected)-set(all_result_ids)),
        "optimized_graphs": len(result_rows),
        "completed_optimizer_candidates": sum(
            len(row.get("optimization_runs", [])) for row in result_rows
            if isinstance(row.get("optimization_runs", []), list)
        )+partial_candidate_count,
        "partial_optimizer_candidates": partial_candidate_count,
        "config_hash": next(iter(config_hashes)) if len(config_hashes) == 1 else None,
        "source_commits": sorted(source_commits),
        "analysis_mode": "matching_only; full-lpf harmonic requirements are not optimizer constraints",
        "errors": unique_errors,
        "results": sorted(result_rows, key=lambda row: row.get("graph_id", "")),
    }
