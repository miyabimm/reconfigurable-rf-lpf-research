#!/usr/bin/env python3
"""W1 read-only tracked Markdown links and current-status consistency gate.

This gate scans the *current checked-out revision*, unlike the historically
pinned W0 evidence. It does not validate remote URLs or every fragment anchor.
"""
from __future__ import annotations

import collections
import json
import posixpath
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LOCAL_RE = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")
REF_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(\S+)")
HTML_REF = re.compile(r"""(?:href|src)\s*=\s*["']([^"']+)["']""")
ACTIVE_ENTRYPOINTS = (
    "README.md",
    "docs/README.md",
    "docs/chatgpt_project_instructions.md",
    "docs/roadmap.md",
    "docs/results.md",
    "docs/specification.md",
    "docs/governance/phase2_experiment_storage_policy.md",
    "data/README.md",
    "experiments/README.md",
)

def tracked():
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return {p for p in raw.decode("utf-8", "surrogateescape").split("\x00") if p}


def strip_markdown_literal(line):
    # Do not treat ordinary single-delimited inline code as active links.
    return re.sub(r"\x60[^\x60]*\x60", "", line)


def all_links(md, known):
    issues, stats = [], collections.Counter()
    for source in md:
        contents = (ROOT / source).read_text(encoding="utf-8", errors="replace")
        fence = None
        for i, raw_line in enumerate(contents.splitlines(), 1):
            stripped = raw_line.lstrip()
            if fence:
                if re.match(re.escape(fence[0]) + "{" + str(fence[1]) + ",}", stripped):
                    fence = None
                continue
            mark = re.match(r"(\x60{3,}|~{3,})", stripped)
            if mark:
                fence = (mark.group(1)[0], len(mark.group(1)))
                continue
            line = strip_markdown_literal(raw_line)
            found = [m.group(1) for m in LOCAL_RE.finditer(line)]
            ref = REF_DEF.match(line)
            if ref:
                found.append(ref.group(1))
            found.extend(m.group(1) for m in HTML_REF.finditer(line))
            for destination in found:
                stats["all_links"] += 1
                raw = destination.strip()
                if raw.startswith("<") and ">" in raw:
                    raw = raw[1:raw.find(">")]
                else:
                    raw = raw.split(" ", 1)[0]
                if not raw:
                    stats["empty"] += 1
                    issues.append((source, i, destination, "empty"))
                    continue
                if raw.startswith("#"):
                    stats["anchor_unchecked"] += 1
                    continue
                parts = urlsplit(raw)
                if parts.scheme or parts.netloc or raw.startswith("//"):
                    stats["external_unchecked"] += 1
                    continue
                rel = unquote(parts.path)
                if not rel:
                    stats["anchor_unchecked"] += 1
                    continue
                target = posixpath.normpath(
                    rel.lstrip("/") if rel.startswith("/")
                    else posixpath.join(posixpath.dirname(source), rel)
                )
                if target in ("..", ".") or target.startswith("../"):
                    stats["outside_repository"] += 1
                    issues.append((source, i, destination, "outside_repository"))
                elif target in known or any(p.startswith(target.rstrip("/") + "/") for p in known):
                    stats["local_resolved"] += 1
                else:
                    stats["local_missing"] += 1
                    issues.append((source, i, destination, "missing"))
    return issues, stats


def verify_status():
    required = {
        "README.md": ["RF-F003", "docs/roadmap.md", "docs/results.md"],
        "docs/roadmap.md": ["Stage 1", "Stage 2", "#163", "IL≤0.30dB"],
        "docs/results.md": ["RF-T005", "RF-F003", "experiment_index.csv"],
        "data/README.md": ["constraints/registry.json", "experiment_index.csv"],
        "docs/README.md": ["chatgpt_project_instructions.md", "roadmap.md"],
        "experiments/README.md": ["experiment_index.csv", "EXP-NNN"],
        "scripts/README.md": ["--catalog", "build_phase2_candidate_catalog.py", "39028160775"],
    }
    for file, tokens in required.items():
        txt = (ROOT / file).read_text(encoding="utf-8")
        current = txt
        for token in tokens:
            if token not in current:
                raise ValueError("W1 current-status reference missing: " + file + ":" + token)

    legacy = (ROOT / "experiments/chatgpt_topology_search/runs/EXP-004/README.md").read_text()
    # EXP-004's README is part of manifest-hash-pinned *original evidence*.
    # Do not edit it simply to fix its outdated relative navigation link.
    legacy_path = "experiments/chatgpt_topology_search/runs/EXP-004/README.md"
    legacy_old = subprocess.check_output(
        ["git", "rev-parse", "055b222c79c73c7fbeacb19383f21c1da0625195:" + legacy_path],
        cwd=ROOT).decode().strip()
    legacy_now = subprocess.check_output(
        ["git", "hash-object", legacy_path], cwd=ROOT).decode().strip()
    if legacy_old != legacy_now:
        raise ValueError("EXP-004 original README checksum changed")
    if "../../../../actions/workflows/lpf-target040.yml" not in legacy:
        raise ValueError("Original EXP-004 workflow link no longer matches stored evidence")
    # The original EXP-004 YAML was retired from main. Verify its pinned Git
    # object rather than requiring a deleted live workflow to reappear.
    historic = "055b222c79c73c7fbeacb19383f21c1da0625195:.github/workflows/lpf-target040.yml"
    historic_blob = subprocess.check_output(
        ["git", "rev-parse", historic], cwd=ROOT, text=True).strip()
    if historic_blob != "9bdb97ff365a626a614bc0198c04cfe419771a8b":
        raise ValueError("EXP-004 historical Actions source changed")
    alias = ROOT / "actions/workflows/lpf-target040.yml"
    if not alias.is_file() or alias.is_symlink():
        raise ValueError("Missing regular legacy EXP-004 navigation note")
    alias_text = alias.read_text(encoding="utf-8")
    if not all(k in alias_text for k in (
        "NOT a GitHub Actions workflow",
        "git show " + historic,
        "retired from main",
    )):
        raise ValueError("EXP-004 legacy note must point to pinned historical source")

    original_sha = "055b222c79c73c7fbeacb19383f21c1da0625195"
    # The registry changes when Phase 2 trial policies are approved;
    # unlike the snapshots below, its bytes are not immutable.
    registry = json.loads((ROOT / "data/constraints/registry.json").read_text(encoding="utf-8"))
    if registry["active_formal_id"] != "RF-F003" or registry["trial"]["RF-T008"]["state"] != "study_authorized":
        raise ValueError("Unexpected current formal or trial registry status")
    untouched = ["data/bands.csv",
                 "data/constraints/formal/RF-F003.json",
                 "data/constraints/trial/RF-T005.json",
                 "data/design_constraints.json",
                 "experiments/chatgpt_topology_search/runs/EXP-047/manifest.json"]
    for rel in untouched:
        old = subprocess.check_output(["git", "rev-parse", original_sha + ":" + rel],
                                      cwd=ROOT).decode().strip()
        now = subprocess.check_output(["git", "hash-object", rel],
                                      cwd=ROOT).decode().strip()
        if old != now:
            raise ValueError("W1 modified a protected RF/source original: " + rel)
    return len(required), len(untouched)


def main():
    args = sys.argv[1:]
    if args not in ([], ["--active-only"]):
        raise SystemExit("Usage: verify_phase2_cleanup_w1_links.py [--active-only]")
    known = tracked()
    md = sorted(p for p in known if p.endswith((".md", ".mdx", ".markdown")))
    if args:
        missing = sorted(set(ACTIVE_ENTRYPOINTS) - known)
        if missing:
            raise SystemExit("Missing active documentation: " + ", ".join(missing))
        md = list(ACTIVE_ENTRYPOINTS)
    issues, stats = all_links(md, known)
    verified_pages, source_files = verify_status()
    result = {
        "phase": "Phase 2", "scope": ("active entrypoints" if args else "W1 current checked-out tracked files"),
        "tracked_files": len(known), "markdown_files": len(md),
        "markdown_links": stats["all_links"],
        "local_resolved": stats["local_resolved"],
        "external_unchecked": stats["external_unchecked"],
        "anchor_unchecked": stats["anchor_unchecked"],
        "missing_or_invalid_local_links": len(issues),
        "current_status_pages_checked": verified_pages,
        "protected_source_blob_checks": source_files,
        "source_files_deleted_or_moved_by_test": 0,
        "limitations": ["No external web link reachability test",
                       "GitHub Markdown fragments are not fully validated",
                       "Regex parser may miss nested destinations and dynamic links"],
        "issues": issues,
    }
    print(json.dumps(result, ensure_ascii=False))
    if issues:
        raise SystemExit("W1 link resolution failed: " + json.dumps(issues[:30], ensure_ascii=False))


if __name__ == "__main__":
    main()
