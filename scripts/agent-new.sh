#!/usr/bin/env bash
set -euo pipefail

usage() { echo 'Usage: bash scripts/agent-new.sh KC-101 ci-baseline' >&2; exit 2; }
[[ $# -eq 2 ]] || usage
id="$1"; topic="$2"
[[ "$id" =~ ^KC-[0-9]{3,}$ ]] || { echo "Invalid task id: $id" >&2; usage; }
[[ "$topic" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || { echo "Invalid topic: $topic" >&2; usage; }
repo="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo 'Not inside a git repository' >&2; exit 1; }
cd "$repo"
[[ "$(git branch --show-current)" == 'main' ]] || { echo 'Switch PRIMARY checkout to main first' >&2; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo 'Main checkout must be clean; inspect git status and commit changes first' >&2; exit 1; }
git show-ref --verify --quiet refs/heads/main || { echo 'Missing local main branch' >&2; exit 1; }
branch="agent/${id}-${topic}"
folder="$(dirname "$repo")/kc-${id}-${topic}"
if git show-ref --verify --quiet "refs/heads/$branch"; then
  echo "Branch already exists: $branch" >&2; exit 1
fi
if [[ -e "$folder" ]]; then
  echo "Destination already exists: $folder" >&2; exit 1
fi
# The task's owner/issue must be assigned by the coordinator *before* running this.
git worktree add -b "$branch" "$folder" main
printf '\nReady:\n  Branch:   %s\n  Worktree: %s\n\n' "$branch" "$folder"
printf 'Next:\n  cd %q\n  export CARGO_TARGET_DIR="$PWD/target/agent-%s"\n' "$folder" "$id"
printf '  bash scripts/agent-prompt.sh %s <ROLE>\n\n' "$id"
echo 'Reminder: this does not reserve tasks or start any AI agent.'
