#!/usr/bin/env python3
"""Read-only registry and new EXP manifest provenance check.

Checks central main (not a proposed PR ledger) for any *new experiment path*
being introduced. Legacy EXP-001..041 additions remain exempt. Does not create or reserve an ID.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

from scripts.experiment_id_registry import PATH, is_reserved_on_main, read_ledger

ROOT = Path(__file__).resolve().parents[3]
NEW_EXPERIMENT_PATH = re.compile(
    r"^experiments/(?:chatgpt_topology_search|matching_limit)/runs/"
    r"(EXP-\d{3,})/"
)


def git(root, *args):
    return subprocess.check_output(
        ["git", *args], cwd=root, stderr=subprocess.PIPE)


def audit(root=ROOT, main_ref="origin/main"):
    root = Path(root)
    local = read_ledger((root / PATH).read_text(encoding="utf-8"))
    # Once deployed, only main is the authority. A pending PR cannot reserve.
    on_main = False
    try:
        remote_bytes = git(root, "show", f"{main_ref}:{PATH}")
        on_main = True
        remote = read_ledger(remote_bytes.decode("utf-8"))
        if len(local) < len(remote):
            raise ValueError("Local ledger lost previously allocated IDs")
        for a, b in zip(local, remote):
            if a["experiment_id"] != b["experiment_id"]:
                raise ValueError("Main reservation ID reordering detected")
            fixed = ("experiment_id", "owner", "request_id", "purpose",
                     "constraint_id", "reserved_at_utc", "origin")
            if any(a[field] != b[field] for field in fixed):
                raise ValueError("Existing main reservation provenance was rewritten")
            if b["state"] in ("legacy_recorded", "legacy_gap_retired"):
                if a["state"] != b["state"]:
                    raise ValueError("Historical registry row changed")
            elif b["state"] in ("completed", "cancelled"):
                if a["state"] != b["state"]:
                    raise ValueError("Terminal experiment number state was reopened")
            elif b["state"] == "active" and a["state"] == "reserved":
                raise ValueError("Experiment state regressed from active to reserved")
    except subprocess.CalledProcessError:
        # Bootstrapping PR #53 is allowed; start checks below still fail
        # closed if a new EXP manifest was added without central reservation.
        pass
    new_paths = git(root, "diff", "--diff-filter=A", "--name-only", "-z",
                    main_ref, "HEAD").split(b"\0")
    new_ids = sorted(set(
        m.group(1) for raw in new_paths if raw
        if (m := NEW_EXPERIMENT_PATH.match(raw.decode("utf-8")))
        if int(m.group(1).split("-")[1]) >= 42
    ))
    for exp_id in new_ids:
        if not on_main:
            raise ValueError(f"Cannot start {exp_id}; registry is not yet on main")
        is_reserved_on_main(root, exp_id, main_ref=main_ref)
    return {
        "phase": "Phase 2", "central_registry_on_main": on_main,
        "registered_ids": len(local),
        "historical_and_gap_ids": 41,
        "new_experiment_manifests": new_ids,
        "new_manifests_with_main_reservations": len(new_ids),
        "reservation_written_by_audit": False,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--main-ref", default="origin/main")
    args = ap.parse_args()
    report = audit(ROOT, main_ref=args.main_ref)
    print("PASS Phase 2 main EXP reservation audit:", json.dumps(
        report, ensure_ascii=False))


if __name__ == "__main__":
    main()
