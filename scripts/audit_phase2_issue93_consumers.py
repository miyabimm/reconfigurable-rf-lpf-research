#!/usr/bin/env python3
"""Non-destructive, source-wide literal consumer scan for Issue #93.

This searches tracked UTF-8 source files only; it does not query external GitHub
settings, run GitHub Actions, or authorize workflow/source retirement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

TOKENS = (
    "phase2_first_wave_retention_parity.yml",
    "phase2_first_wave_retention_parity",
    "first-wave-exp042-crosswalk",
    "first-wave-exp042-six-original-members",
    "first-wave-exp046-exp047-provenance",
    "phase2-bc-first-wave-parity-evidence",
    "five-original-checks-without-retirement",
    "w2-topology",
    "w3-source-restoration",
    "exp042-crosswalk",
    "exp042-six-original-members",
    "exp046-exp047-provenance",
)


def category(path: str) -> str:
    if path.startswith(".github/workflows/"):
        return "workflow"
    if path.startswith("docs/"):
        return "documentation"
    if path.startswith(("scripts/", "tests/", "src/", "actions/", ".github/")):
        return "code_or_config"
    return "other_tracked"


def audit(repo: Path, *, self_path: str) -> dict:
    proc = subprocess.run(
        ["git", "ls-files", "-z"], cwd=repo, capture_output=True, check=True
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True,
        check=True,
    ).stdout.strip()
    files = sorted(x.decode("utf-8", "surrogateescape") for x in proc.stdout.split(b"\0") if x)
    result = {
        "schema_version": 1,
        "source_commit": commit,
        "source_scope": "all git-tracked UTF-8 text files except this self-referential audit script",
        "excluded_self": self_path,
        "literal_tokens": list(TOKENS),
        "tracked_file_count": len(files),
        "scanned_text_file_count": 0,
        "scanned_text_byte_count": 0,
        "binary_or_non_utf8_skip_paths": [],
        "missing_or_out_of_root_skip_paths": [],
        "matches": [],
        "external_and_dynamic_consumers_verified": False,
        "github_required_checks_verified": False,
        "workflow_retirement_authorized": False,
        "original_evidence_deletions": 0,
    }
    root = repo.resolve()
    for relative in files:
        if relative == self_path:
            continue
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            result["missing_or_out_of_root_skip_paths"].append(relative)
            continue
        data = path.read_bytes()
        if b"\0" in data:
            result["binary_or_non_utf8_skip_paths"].append(relative)
            continue
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            result["binary_or_non_utf8_skip_paths"].append(relative)
            continue
        result["scanned_text_file_count"] += 1
        result["scanned_text_byte_count"] += len(data)
        found = []
        for number, line in enumerate(content.splitlines(), 1):
            for token in TOKENS:
                if token in line:
                    found.append({"line": number, "token": token, "excerpt": line.strip()[:240]})
        if found:
            result["matches"].append({
                "path": relative,
                "category": category(relative),
                "source_sha256": hashlib.sha256(data).hexdigest(),
                "occurrences": found,
            })
    result["matching_file_count"] = len(result["matches"])
    result["matching_code_or_config_paths"] = [
        entry["path"] for entry in result["matches"]
        if entry["category"] == "code_or_config"
    ]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="artifacts/phase2_reports/bc/issue93_reference_scan")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    script_path = Path(__file__).resolve().relative_to(root).as_posix()
    results = audit(root, self_path=script_path)
    destination = root / args.output_dir / "issue93_tracked_reference_scan.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("ISSUE93_STATIC_REFERENCE_SCAN_COMPLETE", json.dumps({
        "commit": results["source_commit"],
        "tracked": results["tracked_file_count"],
        "scanned_text": results["scanned_text_file_count"],
        "skipped_binary": len(results["binary_or_non_utf8_skip_paths"]),
        "matching_files": results["matching_file_count"],
        "code_or_config_consumers": results["matching_code_or_config_paths"],
        "report": str(destination.relative_to(root)),
        "retirement_authorized": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
