#!/usr/bin/env bash
# OWNER: M1
# Merge-window helper (run from YOUR branch, in Git Bash):
#   fetch, merge origin/main into the branch, run the tests, push the branch, then push to main.
# Needs no `make`. Installs requirements if pytest/flask/requests are missing. Never force-pushes.
set -e
cd "$(git rev-parse --show-toplevel)"

branch=$(git rev-parse --abbrev-ref HEAD)
if [ "$branch" = "main" ]; then echo "STOP: run this from your own branch, not main."; exit 1; fi
if git ls-files --error-unmatch CONTEXT.md >/dev/null 2>&1; then
  echo "STOP: CONTEXT.md is tracked. Run: git rm --cached CONTEXT.md, commit, then run this again."; exit 1
fi
if ! git diff-index --quiet HEAD --; then
  echo "STOP: you have uncommitted changes. Commit them (or stash them), then run this again."; exit 1
fi

# Find a working Python (on Windows `python` can be a Microsoft Store placeholder; `py` is the launcher).
PY=""
for cand in python py python3; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import sys" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then echo "STOP: Python not found. Install Python 3.12+ and add it to PATH."; exit 1; fi

if ! "$PY" -c "import pytest, flask, requests" >/dev/null 2>&1; then
  echo "Installing requirements (one time)..."
  "$PY" -m pip install -q -r requirements.txt
fi

git fetch origin
if ! git merge origin/main --no-edit; then
  echo "STOP: merge conflict with main. Nothing was pushed. Run 'git merge --abort' and tell M1."; exit 1
fi

if ! "$PY" -m pytest -q; then
  echo "STOP: tests failed. Nothing was pushed to main. Fix the failures, commit, then run this again."; exit 1
fi

git push origin HEAD
if ! git push origin HEAD:main; then
  echo "STOP: main moved while you were testing (someone else merged). Run this script again."; exit 1
fi
echo "Done: $branch merged into main. Post your status line in the team chat."
