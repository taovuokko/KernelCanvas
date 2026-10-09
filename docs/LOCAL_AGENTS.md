# KernelCanvas — Local Agent Pilot Runbook

> Foundation agent kit v0.2. No AI-agent launcher or autonomous task scheduler is bundled. Commands below create separate Git worktrees and **prepare** local development; you choose the Claude Code / Codex / Cursor / other local agent runtime. Read `AGENTS.md`, `docs/TASK_PROTOCOL.md` and `docs/INTEGRATION.md` first.

## Prerequisites
Fedora/Linux host, Git with configured author, current `main`, and optionally `gh` for GitHub issues and PRs. Rust/Node tooling is required to execute corresponding checks. After extracting this kit, first commit these docs/scripts to `main` (the maintainer does this) before branching. Do not run multiple agents against the same checkout.

## First milestone: two implementers + a separate reviewer

1. Maintainer checks whether `KC-101` and `KC-102` identifiers are unused. Create one GitHub issue per `tasks/` seed card; the issue becomes the canonical task record. Assign real owners and a **different** reviewer, mark `IN_PROGRESS`. Tracked seed cards do not reserve tasks by themselves.
2. Maintainer selects **CI (KC-101)** and **core diagnostics (KC-102)** for the first parallel run. Their permitted paths do not overlap. Defer UI task `KC-103` until one slot is free.
3. In the primary checkout, ensure it is clean and up-to-date:

```bash
git switch main
git status --short
git pull --ff-only origin main
bash scripts/agent-new.sh KC-101 ci-baseline
bash scripts/agent-new.sh KC-102 core-diagnostics
git worktree list
```

4. Open **different terminals / agent sessions**:

```bash
cd ../kc-KC-101-ci-baseline
export CARGO_TARGET_DIR="$PWD/target/agent-KC-101"
bash scripts/agent-prompt.sh KC-101 INFRA
# Paste displayed prompt into your chosen local AI agent, operating from THIS directory.
```

```bash
cd ../kc-KC-102-core-diagnostics
export CARGO_TARGET_DIR="$PWD/target/agent-KC-102"
bash scripts/agent-prompt.sh KC-102 CORE
# Paste displayed prompt into another local agent, operating from THIS directory.
```

5. Agents implement **only their assigned paths**, run real applicable tests, commit reviewable changes. They must not push/create PR without maintainer permission. Local shell helper:

```bash
bash scripts/agent-check.sh
bash scripts/agent-handover.sh KC-101 > .agent-work/KC-101-handover.md
```

6. Agent attaches handover to the corresponding **GitHub issue or PR**. A file only in ignored `.agent-work/` is not shared. After maintainer authorizes remote actions, push and open PR as described in `docs/INTEGRATION.md`.
7. Independent reviewer reads `agents/REVIEWER.md`, reviews PR/CI evidence. Only the maintainer authorizes merge; issue moves to `DONE` **after** merge. Later schedule `KC-103`.

## Starter prompt, if your CLI cannot read prompt stdout easily

> You are the KernelCanvas <ROLE> agent working on task <KC-NNN>. Read `AGENTS.md`, your `agents/<ROLE>.md`, `docs/ARCHITECTURE.md`, `docs/TASK_PROTOCOL.md`, `docs/TESTING.md` and the assigned `tasks/<KC-NNN>-*.md`. Check actual repo and branch. Do not edit paths outside the card. Do not change API contracts, dependencies or shared policy without approval. Implement a small tested change, log PASS/FAIL/NOT RUN for applicable checks, then deliver the documented handover. Do not merge. Ask before network, push, PR creation, destructive commands or new privileges.

## Operating guidelines
- Do not assume shell commands in documentation correspond to installed executables: check first.
- `scripts/agent-new.sh` does not claim an issue or start AI software; it requires a clean local `main`, does not fetch automatically, and refuses existing worktree/branch names.
- `scripts/agent-check.sh` runs checks for present source/tooling **without installing dependencies**. A `NOT RUN` status is not PASS. Some failures may be unrelated to a narrow PR; report them exactly.
- Worktree `target` paths are task-local. A lot of Rust worktrees can consume substantial storage.
- Never run `git clean -fdx`, hard resets, force pushes, unreviewed deploys, or BitBake execution just to make the pilot pass.
- CI is a genuine agent task: it should inspect the actual repo and create the workflow; **do not make it green by skipping mandatory checks**.

## What comes after the pilot
Once two non-overlapping PRs have merged cleanly, add task `KC-103` for the frontend, then an API health task only after confirming its security scope. Introduce a true automatic orchestrator **later** with atomic task leasing, bounded retries, spend/CPU limits and review gates. The kit is manual-on-purpose for its first iteration.
