#!/usr/bin/env python3
"""Phase 2 W4 read-only replay/dependency gate for 225 preserved experiment files.

Pure source/metadata inspection and syntax parsing. Never execute LPF solvers or
rewrite immutable original runs; never equate parsing with numerical replay.
"""
from __future__ import annotations

import argparse
import ast
import collections
import csv
import hashlib
import io
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "fd8c3fb4dc9f972dfd3d646009facb25cf344a0b"
SOURCE_CSV = ROOT / "data/repository_reviews/w4_unindexed_225_review_20261017.csv"
PREVIOUS_WORKFLOWS = ROOT / "data/repository_reviews/w4_workflow_runs_20261017.csv"
PROTECTED_CSV = ROOT / "data/repository_reviews/step4_retention_46_20261017.csv"
AREAS = ("experiments/chatgpt_topology_search/runs/", "data/validation/")
FIELDS = [
    "source_path", "git_blob_sha1", "bytes", "group", "source_kind",
    "constraint_from_manifest", "manifest_execution_status",
    "original_manifest_blob_sha1", "manifest_full_path_literal",
    "manifest_basename_mention_unverified", "readme_basename_mention_unverified",
    "workflow_exact_path_reference", "source_mentions_external_s2p",
    "source_mentions_tool_fetch", "source_mentions_dynamic_path_construct",
    "source_mentions_checkpoint", "syntax_test", "syntax_result",
    "replay_performed", "replay_claim", "disposition", "owner_delete_approval",
]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def filename_mentioned(text, filename):
    # This is a lexical *hint*, including ambiguity for 'README.md' or shared
    # basenames. It is never claimed to be a validated runtime reference.
    return bool(re.search(r"(?<![A-Za-z0-9_./-])" + re.escape(filename) +
                          r"(?![A-Za-z0-9_./-])", text))


def source_context(group):
    path = ROOT / "experiments/chatgpt_topology_search/runs" / group
    m = path / "manifest.json"
    r = path / "README.md"
    if not m.is_file():
        return {"manifest": None, "manifest_text": "", "readme_text": "",
                "constraint": "unknown", "execution": "unknown", "sha": ""}
    data = json.loads(m.read_text(encoding="utf-8"))
    raw_exec = data.get("execution", {})
    if isinstance(raw_exec, dict):
        execution = raw_exec.get("status") or "unknown"
        platform = raw_exec.get("platform") or raw_exec.get("source_method") or ""
        if platform:
            execution += " (" + str(platform)[:120] + ")"
    else:
        execution = str(raw_exec)
    raw_constraint = data.get("constraint_id")
    if not raw_constraint and isinstance(data.get("constraints"), dict):
        raw_constraint = data["constraints"].get("constraint_id")
    return {
        "manifest": data,
        "manifest_text": m.read_text(encoding="utf-8"),
        "readme_text": r.read_text(encoding="utf-8") if r.is_file() else "",
        "constraint": str(raw_constraint or "unknown"),
        "execution": str(execution),
        "sha": blob_sha(m.read_bytes()),
    }


def validate_syntax(path, raw):
    suffix = path.suffix.lower()
    if suffix == ".py":
        try:
            ast.parse(raw.decode("utf-8"), filename=str(path))
            return "python_ast_parse", "parsed_syntax_only"
        except (SyntaxError, UnicodeDecodeError) as e:
            return "python_ast_parse", "syntax_error:" + type(e).__name__
    if suffix == ".js":
        node = shutil.which("node")
        if not node:
            return "node_module_parse", "not_executed_node_missing"
        test = subprocess.run(
            [node, "--input-type=module", "--check"],
            input=raw, cwd=ROOT, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=8
        )
        if test.returncode == 0:
            return "node_module_parse", "parsed_syntax_only"
        # Original Code Mode files may require an async function wrapper. Compile
        # source in that context without ever *calling* the resulting function.
        wrapper = subprocess.run(
            [node, "-e", (
                "const fs=require('fs');"
                "const source=fs.readFileSync(0,'utf8');"
                "const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;"
                "new AsyncFunction('tools','text',source);"
            )],
            input=raw, cwd=ROOT, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=8
        )
        return ("node_async_function_compile",
                "compiled_without_execution" if wrapper.returncode == 0
                else "incompatible_with_both_static_parser_contexts")
    return "not_applicable", "not_a_source_file"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--emit-csv-chunks", action="store_true")
    a = p.parse_args()

    assert git("rev-parse", BASE) == BASE
    deleted = git("diff", "--diff-filter=D", "--name-only", BASE, "HEAD")
    assert not deleted, "No deletions permitted in W4 audit"
    modified = git("diff", "--name-only", BASE, "HEAD").splitlines()
    assert not any(x.startswith(AREAS) or x.startswith((
        "data/constraints/", "data/parasitics/", "candidates/"
    )) or x in ("data/bands.csv", "data/design_constraints.json") for x in modified), (
        "Original RF and experiment sources must not change"
    )

    with SOURCE_CSV.open(newline="", encoding="utf-8") as f:
        items = list(csv.DictReader(f))
    assert len(items) == 225
    with PROTECTED_CSV.open(newline="", encoding="utf-8") as f:
        protected = list(csv.DictReader(f))
    assert len(protected) == 46
    protected_paths = {x["path"] for x in protected}
    assert all(blob_sha((ROOT / x["path"]).read_bytes()) == x["git_blob_sha1"]
               for x in protected)
    assert all(x["path"] not in protected_paths for x in items)
    with PREVIOUS_WORKFLOWS.open(newline="", encoding="utf-8") as f:
        historical_workflows = list(csv.DictReader(f))
    assert len(historical_workflows) == 39
    workflows = {}
    for w in historical_workflows:
        path = w["workflow_path"]
        assert (ROOT / path).is_file(), "Original workflow missing: " + path
        workflows[path] = (ROOT / path).read_text(encoding="utf-8")

    context_cache = {}
    rows = []
    for item in items:
        path = item["path"]
        assert path.startswith(AREAS) and item["delete_status"] == "retained_no_deletion_authorized"
        actual = ROOT / path
        assert actual.is_file() and not actual.is_symlink(), "Original evidence missing: " + path
        raw = actual.read_bytes()
        assert blob_sha(raw) == item["git_blob_sha1"], "Archived original changed: " + path
        assert len(raw) == int(item["bytes"]), "Original byte size changed: " + path
        group = item["run_or_validation_group"]
        ctx = context_cache.setdefault(group, source_context(group))
        text = raw.decode("utf-8", errors="replace")
        from_workflow = sorted(name for name, body in workflows.items() if path in body)
        name = actual.name
        suffix = actual.suffix.lower()
        static_names = (
            "source_code" if suffix in (".js", ".py") else
            "data_or_checkpoint" if suffix in (".json", ".jsonl", ".csv") else
            "narrative_or_other"
        )
        syntax, verdict = validate_syntax(actual, raw)
        rows.append({
            "source_path": path, "git_blob_sha1": item["git_blob_sha1"],
            "bytes": item["bytes"], "group": group,
            "source_kind": static_names,
            "constraint_from_manifest": ctx["constraint"],
            "manifest_execution_status": ctx["execution"],
            "original_manifest_blob_sha1": ctx["sha"],
            "manifest_full_path_literal": str(path in ctx["manifest_text"]).lower(),
            "manifest_basename_mention_unverified": str(filename_mentioned(ctx["manifest_text"], name)).lower(),
            "readme_basename_mention_unverified": str(filename_mentioned(ctx["readme_text"], name)).lower(),
            "workflow_exact_path_reference": ";".join(from_workflow),
            "source_mentions_external_s2p": str(
                suffix in (".js", ".py") and
                (".s2p" in text or "data/parasitics/" in text)).lower(),
            "source_mentions_tool_fetch": str(
                suffix in (".js", ".py") and
                ("mcp__GitHub__fetch_file" in text or "urllib.request" in text)).lower(),
            "source_mentions_dynamic_path_construct": str(
                suffix in (".js", ".py") and
                any(z in text for z in ("join(", "Path(", "readFile", "open(", "fetch_file("))).lower(),
            "source_mentions_checkpoint": str(
                suffix in (".js", ".py") and
                any(z in text for z in ("checkpoint", "results/", "manifest"))).lower(),
            "syntax_test": syntax, "syntax_result": verdict,
            "replay_performed": "false",
            "replay_claim": "none_static_inspection_only",
            "disposition": "retain_pending_replay_and_dynamic_dependency_validation",
            "owner_delete_approval": "not_granted",
        })

    groups = collections.Counter(r["group"] for r in rows)
    syntax = collections.Counter((r["syntax_test"], r["syntax_result"]) for r in rows)
    by_constraint = collections.Counter(r["constraint_from_manifest"] for r in rows)
    assert len(rows) == 225
    assert sum(r["source_kind"] == "source_code" and
               Path(r["source_path"]).suffix.lower() == ".js" for r in rows) == 59
    assert sum(r["source_kind"] == "source_code" and
               Path(r["source_path"]).suffix.lower() == ".py" for r in rows) == 27
    out = a.output_dir
    out.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    data = buf.getvalue()
    (out / "w4_replay_dependency_225.csv").write_text(data, encoding="utf-8")
    summary = {
        "baseline_main": BASE,
        "checked_out_sha": git("rev-parse", "HEAD"),
        "reviewed_originals": len(rows),
        "original_bytes": sum(int(x["bytes"]) for x in rows),
        "protected_46_sha_pass": len(protected),
        "groups": dict(sorted(groups.items())),
        "constraint_from_manifest": dict(sorted(by_constraint.items())),
        "manifest_exact_path_literals": sum(r["manifest_full_path_literal"] == "true" for r in rows),
        "manifest_basename_hints_not_proof": sum(r["manifest_basename_mention_unverified"] == "true" for r in rows),
        "readme_basename_hints_not_proof": sum(r["readme_basename_mention_unverified"] == "true" for r in rows),
        "workflow_exact_path_refs": sum(bool(r["workflow_exact_path_reference"]) for r in rows),
        "source_mentions_external_s2p": sum(r["source_mentions_external_s2p"] == "true" for r in rows),
        "source_mentions_tool_fetch": sum(r["source_mentions_tool_fetch"] == "true" for r in rows),
        "source_mentions_dynamic_path_construct": sum(r["source_mentions_dynamic_path_construct"] == "true" for r in rows),
        "source_mentions_checkpoint": sum(r["source_mentions_checkpoint"] == "true" for r in rows),
        "syntax": {k[0] + "/" + k[1]: v for k, v in sorted(syntax.items())},
        "replay_executions": 0,
        "deletions": 0,
        "owner_delete_approvals": 0,
        "limitations": [
            "Regex lexical analysis cannot prove dynamic runtime paths or unused files.",
            "Manifest/README basename hints may match unrelated same-name files.",
            "Python AST and Node module syntax checks do not execute solvers or validate math.",
            "Historical in-chat scripts can require a Code Mode wrapper and custom tools.",
            "No 28x1001 or 84-point independent MNA rerun occurred.",
        ],
    }
    (out / "w4_replay_dependency_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("W4_REPLAY_GATE_SUMMARY=" + json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    if a.emit_csv_chunks:
        for start in range(0, len(data), 5500):
            print("W4_REPLAY_GATE_CHUNK=" + json.dumps({
                "seq": start // 5500, "text": data[start:start + 5500]
            }, ensure_ascii=False, separators=(",", ":")))
    print("W4_REPLAY_GATE_PASS: exact original SHA, manifest source context, syntax-only inspection, 0 reruns/deletions")


if __name__ == "__main__":
    main()
