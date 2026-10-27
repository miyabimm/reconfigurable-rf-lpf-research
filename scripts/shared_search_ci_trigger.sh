#!/usr/bin/env bash
# Print run or skip. Unknown history/events fail open to running the tests.
set -u
event=${1:-} before=${2:-} head=${3:-}
if ! git cat-file -e "${head}^{commit}" 2>/dev/null; then
  echo run; exit 0
fi
case "$event" in
  pull_request)
    base=$(git merge-base origin/main "$head" 2>/dev/null) || { echo run; exit 0; }
    ;;
  push)
    if [[ ! "$before" =~ ^[0-9a-f]{40}$ || "$before" =~ ^0+$ ]] ||
       ! git cat-file -e "${before}^{commit}" 2>/dev/null ||
       ! git merge-base --is-ancestor "$before" "$head" 2>/dev/null; then
      echo run; exit 0
    fi
    base=$before
    ;;
  *) echo run; exit 0 ;;
esac
changes=$(git diff --no-renames --name-only "$base" "$head") || { echo run; exit 0; }
# Broad dependency groups are deliberate: shared tests import multiple modules
# and fixtures, including dependencies not named after the test itself.
if grep -Eq '^(src/|scripts/|tests/|data/|experiments/|candidates/|actions/|results/|artifacts/|checkpoints/|scratch/|tmp/|\.github/workflows/|\.gitignore$|pyproject\.toml$|requirements\.txt$|uv\.lock$)' <<< "$changes"; then
  echo run
else
  echo skip
fi
