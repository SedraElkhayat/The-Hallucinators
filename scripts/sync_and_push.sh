#!/usr/bin/env bash
# OWNER: M1
# Merge-window helper: fetch, merge origin/main, make test, push branch, then push to main. Never force-pushes.
set -e
branch=$(git rev-parse --abbrev-ref HEAD)
if [ "$branch" = "main" ]; then echo "STOP: run this from your own branch, not main."; exit 1; fi
if git ls-files --error-unmatch CONTEXT.md >/dev/null 2>&1; then echo "STOP: CONTEXT.md is tracked. Run: git rm --cached CONTEXT.md"; exit 1; fi
git fetch origin
git merge origin/main --no-edit
if ! make test; then
  echo "STOP: tests failed. Nothing was pushed. Fix the failures, then run this script again."
  exit 1
fi
git push origin HEAD
git push origin HEAD:main
echo "Done: $branch merged into main."
