#!/usr/bin/env python3
"""Validated allocation for the main-branch EXP-NNN reservation ledger.

No network/write actions: use reserve_experiment_number.py for atomic Git pushes.
Historical IDs and gaps cannot be reused; a reservation is authoritative only
after the ledger commit is visible on origin/main.
"""
import argparse
import csv
import io
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = "data/experiment_number_registry.csv"
COLUMNS = ("experiment_id", "state", "owner", "request_id", "purpose",
           "constraint_id", "reserved_at_utc", "origin")
ALLOWED = {"legacy_recorded", "legacy_gap_retired", "reserved", "active",
           "completed", "cancelled"}
RESERVED = {"reserved", "active", "completed", "cancelled"}
ID_PATTERN = re.compile(r"^EXP-(\d{3,})$")
KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{2,79}$")


def _safe(value, label, required=True, limit=200):
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError(f"{label} is required")
    if len(value) > limit or any(x in value for x in "\r\n\0"):
        raise ValueError(f"Invalid {label} length/control characters")
    if value.lstrip().startswith(("=", "+", "-", "@")):
        raise ValueError(f"Unsafe leading character in {label}")
    return value.strip()


def read_ledger(s):
    rd = csv.DictReader(io.StringIO(s, newline=""))
    if tuple(rd.fieldnames or ()) != COLUMNS:
        raise ValueError("Experiment ID registry header mismatch")
    rows = list(rd)
    validate(rows)
    return rows


def validate(rows):
    if len(rows) < 41:
        raise ValueError("Original EXP-001..041 and permanent gaps must be retained")
    seen_ids, seen_requests, nums = set(), set(), []
    for r in rows:
        if set(r) != set(COLUMNS) or None in r:
            raise ValueError("Malformed reservation ledger row")
        m = ID_PATTERN.fullmatch(r["experiment_id"])
        if not m or r["experiment_id"] in seen_ids:
            raise ValueError("Malformed or duplicated experiment ID")
        seen_ids.add(r["experiment_id"])
        nums.append(int(m.group(1)))
        state = r["state"]
        if state not in ALLOWED:
            raise ValueError("Unsupported reservation state")
        if state in RESERVED:
            if not r["owner"] or not KEY_PATTERN.fullmatch(r["request_id"]):
                raise ValueError("New reservation missing identity or request ID")
            _safe(r["purpose"], "purpose")
            _safe(r["owner"], "owner", limit=80)
            if not re.fullmatch(r"RF-[FT]\d{3}", r["constraint_id"]):
                raise ValueError("Invalid constraint ID in reservation")
            if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ",
                                r["reserved_at_utc"]):
                raise ValueError("Invalid reservation UTC timestamp")
            if r["request_id"] in seen_requests:
                raise ValueError("Duplicate reservation request key")
            seen_requests.add(r["request_id"])
    if nums != list(range(1, nums[-1] + 1)):
        raise ValueError("Missing/out-of-order experiment ledger number")
    for n, r in enumerate(rows[:41], 1):
        want = "legacy_gap_retired" if n in (18, 19) else "legacy_recorded"
        if r["state"] != want or r["request_id"]:
            raise ValueError("Historical experiment numbers must never be reassigned")
    return rows


def as_csv(rows):
    validate(rows)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def next_reservation(rows, *, owner, purpose, constraint_id, request_id, reserved_at_utc):
    validate(rows)
    owner = _safe(owner, "owner", limit=80)
    purpose = _safe(purpose, "purpose")
    if not KEY_PATTERN.fullmatch(request_id):
        raise ValueError("Invalid request key")
    if not re.fullmatch(r"RF-[FT]\d{3}", constraint_id):
        raise ValueError("Invalid formal/trial constraint ID")
    if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", reserved_at_utc):
        raise ValueError("Invalid timestamp")
    for row in rows:
        if row["request_id"] == request_id:
            if (row["owner"], row["purpose"], row["constraint_id"]) != (
                    owner, purpose, constraint_id):
                raise ValueError("Request ID already used for a different reservation")
            return rows, row["experiment_id"], False
    num = int(ID_PATTERN.fullmatch(rows[-1]["experiment_id"]).group(1)) + 1
    candidate = f"EXP-{num:03d}"
    new = dict(zip(COLUMNS, (
        candidate, "reserved", owner, request_id, purpose,
        constraint_id, reserved_at_utc, "main_reservation_workflow"
    )))
    result = rows + [new]
    validate(result)
    return result, candidate, True


def is_reserved_on_main(root, experiment_id, *, main_ref="origin/main"):
    if not ID_PATTERN.fullmatch(experiment_id):
        raise ValueError("Experiment ID must be EXP-NNN")
    result = subprocess.check_output(
        ["git", "show", f"{main_ref}:{PATH}"], cwd=root,
        stderr=subprocess.PIPE).decode("utf-8")
    rows = read_ledger(result)
    matches = [r for r in rows if r["experiment_id"] == experiment_id]
    if len(matches) != 1 or matches[0]["state"] not in {"reserved", "active"}:
        raise ValueError(
            f"{experiment_id} is NOT an active reservation in {main_ref}; "
            "do not begin the experiment.")
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description="Verify authoritative main reservation before experiment work")
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--main-ref", default="origin/main")
    parser.add_argument("--owner")
    args = parser.parse_args()
    row = is_reserved_on_main(ROOT, args.experiment_id, main_ref=args.main_ref)
    if args.owner and args.owner != row["owner"]:
        raise SystemExit("Owner mismatch in main-branch reservation")
    print(json.dumps({
        "experiment_id": row["experiment_id"], "state": row["state"],
        "owner": row["owner"], "request_id": row["request_id"],
        "main_ref": args.main_ref, "can_start": True,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
