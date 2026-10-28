#!/usr/bin/env python3
"""Atomically reserve next EXP ID on GitHub main by a non-force push.

This is a CI-only command. Simultaneous writers race via Git fast-forward
protection; losers fetch the winning commit and choose the next ID. No number
is acknowledged until a fresh fetch confirms the committed request key.
Branch protections can reject pushes; if so the workflow fails closed and the
main-ledger change must be merged using the repository's review path.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time

from experiment_id_registry import (
    PATH, as_csv, next_reservation, read_ledger, is_reserved_on_main,
)

ROOT = Path(__file__).resolve().parents[1]


def git(*args, check=True):
    proc = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True,
        check=False)
    if check and proc.returncode:
        raise RuntimeError("git " + args[0] + " failed: " + proc.stderr[-400:])
    return proc


def valid_constraint(id_string):
    registry = json.loads((ROOT / "rf/constraints/registry.json")
                          .read_text(encoding="utf-8"))
    if id_string == registry["active_formal_id"]:
        return True
    entry = registry["trial"].get(id_string)
    return bool(entry and entry.get("state") == "study_authorized")


def run(*, owner, purpose, constraint_id, request_id, attempts=12):
    if not (os.getenv("GITHUB_ACTIONS") == "true"
            and os.getenv("GITHUB_REF") == "refs/heads/main"
            and os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch"
            and os.getenv("GITHUB_ACTOR") == owner):
        raise RuntimeError("This writer can run only in authenticated manual GitHub Actions on main")
    if attempts < 1 or attempts > 30:
        raise ValueError("attempts must be 1..30")
    if not valid_constraint(constraint_id):
        raise ValueError("Constraint must be current formal or authorized trial")
    if git("status", "--porcelain").stdout.strip():
        raise RuntimeError("Refusing to overwrite a non-clean CI checkout")
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for attempt in range(1, attempts + 1):
        git("fetch", "--no-tags", "origin", "+refs/heads/main:refs/remotes/origin/main")
        git("checkout", "-q", "-B", "experiment-reservation-ci", "origin/main")
        ledger_path = ROOT / PATH
        rows = read_ledger(ledger_path.read_text(encoding="utf-8"))
        new_rows, candidate, created = next_reservation(
            rows, owner=owner, purpose=purpose, constraint_id=constraint_id,
            request_id=request_id, reserved_at_utc=timestamp)
        if not created:
            confirmed = is_reserved_on_main(ROOT, candidate)
            return candidate, False, confirmed
        # Fail rather than recycle a number which existed outside the ledger.
        index_path = ROOT / "data/experiment_index.csv"
        if candidate in index_path.read_text(encoding="utf-8"):
            raise RuntimeError("New ID already present in indexed experiments")
        existing = ROOT / f"experiments/chatgpt_topology_search/runs/{candidate}"
        if existing.exists():
            raise RuntimeError("New ID already has a run directory on main")
        ledger_path.write_text(as_csv(new_rows), encoding="utf-8")
        git("add", "--", PATH)
        git("commit", "-m", f"Reserve {candidate} for {owner} ({request_id})")
        pushed = git("push", "origin", "HEAD:refs/heads/main", check=False)
        git("fetch", "--no-tags", "origin", "+refs/heads/main:refs/remotes/origin/main")
        try:
            match = is_reserved_on_main(ROOT, candidate)
        except ValueError:
            match = None
        if (pushed.returncode == 0 and match and match["request_id"] == request_id):
            return candidate, True, match
        # If server accepted the first push but network failed, do not allocate a
        # second number for the same request key.
        original = git("show", f"origin/main:{PATH}").stdout
        seen = next((row for row in read_ledger(original)
                     if row["request_id"] == request_id), None)
        if seen:
            if (seen["owner"], seen["purpose"], seen["constraint_id"]) != (
                    owner, purpose, constraint_id):
                raise RuntimeError("Request key collision")
            return seen["experiment_id"], False, seen
        if ("protected branch" in pushed.stderr.lower()
                or "repository rule" in pushed.stderr.lower()
                or "protected branch hook" in pushed.stderr.lower()):
            raise RuntimeError(
                "Main branch protection denies reservation push; no reservation "
                "was created. Submit ledger reservation through a PR, merge it "
                "first, and recheck origin/main before starting any run.")
        if attempt == attempts:
            raise RuntimeError("Concurrent reservation updates did not settle; "
                               "NO experiment ID confirmed. Retry manually.")
        time.sleep(min(0.1 * attempt, 1.0))
    raise AssertionError("unreachable")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", required=True)
    ap.add_argument("--purpose", required=True)
    ap.add_argument("--constraint-id", required=True)
    ap.add_argument("--request-id", required=True)
    args = ap.parse_args()
    experiment_id, created, record = run(
        owner=args.owner, purpose=args.purpose,
        constraint_id=args.constraint_id, request_id=args.request_id)
    summary = {
        "experiment_id": experiment_id,
        "reservation_created": created,
        "source": "refs/heads/main",
        "state": record["state"], "actor": record["owner"],
        "request_id": record["request_id"], "can_start": True,
    }
    print(json.dumps(summary, ensure_ascii=False))
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:
            out.write(f"### Confirmed main reservation: {experiment_id}\n\n")
            out.write(f"Actor: {record['owner']}; constraint: "
                      f"{record['constraint_id']}; request: {record['request_id']}\n")
            out.write("\nStart a new run only after verifying this ID on current main.\n")


if __name__ == "__main__":
    main()
