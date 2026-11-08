#!/usr/bin/env python3
"""Create Phase 2 provenance before running; audit or refresh the derived index."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from src.lpf.experiment_manifest import (
    RUNS, audit_provenance, experiment_index, new_manifest, validate_manifest, write_manifest,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("audit")
    sub.add_parser("index", help="Validate manifests and regenerate data/experiment_index.csv")
    create = sub.add_parser("create", help="Create a manifest once; does not run an experiment")
    create.add_argument("experiment_id")
    create.add_argument("--purpose", required=True)
    create.add_argument("--scope", type=Path, required=True, help="JSON object of computational search settings")
    create.add_argument("--objective", choices=("matching_only", "full_lpf"), required=True)
    create.add_argument("--constraint-id")
    create.add_argument("--allow-trial", action="store_true", help="Still requires a study-authorized registered trial")
    create.add_argument("--seed", type=int)
    args = parser.parse_args()
    if args.command == "audit":
        issues = audit_provenance(root=ROOT)
        if issues:
            raise SystemExit("FAILED:\n- " + "\n- ".join(issues))
        print("PASS: constraint registry, manifests, indexes and scoped evidence "
              "(EXP-034..041 retired runtime evidence excluded; not a complete historical audit)")
    elif args.command == "index":
        manifests = []
        for path in sorted((ROOT / RUNS).glob("EXP-*/manifest.json")):
            m = validate_manifest(json.loads(path.read_text()), root=ROOT)
            if m["experiment_id"] != path.parent.name:
                raise SystemExit("Manifest/directory identity mismatch")
            manifests.append((path.relative_to(ROOT).as_posix(), m))
        (ROOT / "data/experiment_index.csv").write_text(experiment_index(manifests), encoding="utf-8")
    else:
        manifest = new_manifest(args.experiment_id, args.purpose, json.loads(args.scope.read_text()),
                                objective=args.objective, seed=args.seed, constraint_id=args.constraint_id,
                                allow_trial=args.allow_trial, root=ROOT)
        directory = ROOT / RUNS / args.experiment_id
        directory.mkdir(parents=True, exist_ok=True)
        write_manifest(directory / "manifest.json", manifest, root=ROOT)
        print(directory / "manifest.json")
        print("Run 'python scripts/experiment_manifests.py index' after updating the manifest.")


if __name__ == "__main__":
    main()
