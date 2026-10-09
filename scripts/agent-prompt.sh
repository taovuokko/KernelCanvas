#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 2 ]] || { echo 'Usage: bash scripts/agent-prompt.sh KC-101 INFRA' >&2; exit 2; }
id="$1"; role="$2"
[[ "$id" =~ ^KC-[0-9]{3,}$ ]] || { echo 'Invalid task id' >&2; exit 2; }
[[ "$role" =~ ^(PLANNER|CORE|BACKEND|FRONTEND|YOCTO|INFRA|REVIEWER)$ ]] || { echo 'Unknown role' >&2; exit 2; }
repo="$(git rev-parse --show-toplevel)"; cd "$repo"
shopt -s nullglob
matches=(tasks/"${id}"-*.md)
[[ ${#matches[@]} -eq 1 ]] || { echo "Expected exactly one task card for $id; found ${#matches[@]}" >&2; exit 1; }
[[ -f "agents/${role}.md" ]] || { echo "Missing agents/${role}.md" >&2; exit 1; }
cat <<EOF
You are the KernelCanvas ${role} implementation/review agent.
Task: ${id}
Task specification: ${matches[0]}
Role instructions: agents/${role}.md

FIRST read AGENTS.md, agents/${role}.md, ${matches[0]},
docs/PRODUCT.md, docs/ARCHITECTURE.md, docs/TASK_PROTOCOL.md,
docs/TESTING.md, docs/INTEGRATION.md and relevant accepted ADRs.

Before editing, verify this checkout/branch is the explicitly assigned worktree.
If the GitHub issue is unassigned or the task has no distinct reviewer,
STOP and ask the maintainer to assign them. A local Markdown seed is not a lock.
Inspect actual repo contents; never assume planned modules or scripts exist.
Edit only paths explicitly allowed in the task card; stop on shared contracts.
Do not install/fetch, access secrets, run BitBake, push, open PR, deploy,
force-push, reset, or merge without the task/maintainer authorization.
Implement smallest tested change; report exact PASS/FAIL/NOT RUN evidence.
Deliver a handover with task ID, commit(s), tests, blockers and review request.
Do not self-approve or merge.
EOF
