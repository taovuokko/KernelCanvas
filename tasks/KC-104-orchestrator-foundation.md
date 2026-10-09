# KC-104 — Python Orchestrator Foundation (SQLite + CLI)

> Seed task: create GitHub Issue and assign **before execution**. This document alone does not reserve the task.

- Milestone: M0 (development automation)
- Priority: P0
- Agent role: `agents/ORCHESTRATOR.md`
- State: IN_PROGRESS
- Owner: local-codex-orchestrator-01
- Reviewer: local-claude-review-02
- Depends on: merged foundation documentation. Independent of KC-101 CI changes; do not edit CI files.

## Goal

Build a small local Python coordinator with durable SQLite task state, atomic claims and a command-line interface. This is **only the scheduler/state foundation**. It must not launch Claude, Codex, shell commands, BitBake, or create PRs.

## Allowed paths

- `orchestrator/__init__.py`
- `orchestrator/__main__.py`
- `orchestrator/cli.py`
- `orchestrator/database.py`
- `orchestrator/models.py`
- `orchestrator/scheduler.py`
- `orchestrator/tests/**`
- `orchestrator/README.md`

New files inside `orchestrator/` are allowed when justified in the PR. No changes outside this area without explicit maintainer approval.

## Required behavior

1. `python3 -m orchestrator init`: initialize a versioned local SQLite DB at `${XDG_STATE_HOME:-~/.local/state}/kernelcanvas/orchestrator.sqlite3`, override with `KERNELCANVAS_ORCHESTRATOR_DB` for tests. Do not create DB artifacts inside tracked repo paths.
2. `add TASK_ID --task-file PATH --issue-url URL`: persist unique task metadata and QUEUED state; reject duplicate IDs, bad paths, missing cards and malformed issue URLs. Do not claim the URL is independently verified by this offline v0.
3. `status [TASK_ID]`: display state, claim owner, reviewer and age; use reliable exit codes and a human-readable format.
4. `claim TASK_ID --worker NAME --reviewer NAME --lease-seconds N`: atomically reserve a QUEUED task; enforce different nonempty worker/reviewer; do not permit a second claimant. Use `BEGIN IMMEDIATE` and transaction rollback on failure.
5. `heartbeat TASK_ID --worker NAME`: refresh the owner's live lease; reject wrong worker, released or expired lease. Correctly handle UTC time.
6. `release TASK_ID --worker NAME --to REVIEW|BLOCKED|FAILED --reason TEXT`: validate ownership and transition; append an immutable event. `DONE` is maintainer-only and requires a separate reviewed-integration operation in a later version.
7. `history TASK_ID`: list events in order with timestamps and actors.
8. Clearly handle missing DB/schema, concurrent contention, interrupted transaction, invalid state transitions and timeout/expired lease. **Do not automatically steal expired leases**; require manual recovery.
9. Standard library only. Add versioned migrations or clearly fail on unsupported schema versions.
10. Add `README.md` instructions including exact commands and disclosure that `run`/Claude/Codex support does not yet exist.

## Safety exclusions

- No GitHub API calls, network, credentials, shell execution or LLM subprocesses.
- No background daemon, infinite loop, subprocess kill, branch/worktree mutation or auto merge.
- No new dependencies, no weakening tests, no fake green outputs, no storing private API tokens in SQLite.

## Verification (exact commands)

```bash
python3 -m orchestrator --help
python3 -m unittest discover -s orchestrator/tests -v
```

Required automated tests:

- Initialize temporary DB, register and query task.
- Duplicate ID and nonexistent task rejection.
- Two separate connections/processes race to claim the same task: **one winner**.
- Worker/reviewer must differ.
- Wrong-worker heartbeat/release rejected.
- Invalid transition rejected.
- Lease expiry does not silently spawn/reassign another worker.
- History is append-only and ordered.
- No test requires internet or CLI auth.

## Handover

Include branch, commit hash, changed paths, CLI sample output, exact PASS/FAIL/NOT RUN results, remaining limitations, DB migration notes, and a clearly scoped proposal for KC-105. No push or PR without explicit maintainer authorization. No merge without independent review + GitHub CI.
