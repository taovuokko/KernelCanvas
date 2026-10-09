# KernelCanvas Orchestrator v0

This package is a local, standard-library-only scheduler for development tasks. It stores durable task state, leases, and transition history in SQLite. It does not contact GitHub and does not verify issue URLs over the network.

Python 3.11 or newer is required.

## Database

The default database is:

```text
${XDG_STATE_HOME:-~/.local/state}/kernelcanvas/orchestrator.sqlite3
```

Set `KERNELCANVAS_ORCHESTRATOR_DB` to use another path. Tests always use temporary paths. SQLite schema version 1 is validated on every non-`init` command; unsupported versions fail without automatic repair.

## Commands

From the repository root:

```bash
python3 -m orchestrator init
python3 -m orchestrator add KC-104 \
  --task-file tasks/KC-104-orchestrator-foundation.md \
  --issue-url https://github.com/taovuokko/KernelCanvas/issues/104
python3 -m orchestrator status
python3 -m orchestrator status KC-104
python3 -m orchestrator claim KC-104 \
  --worker local-codex-orchestrator-01 \
  --reviewer local-claude-review-02 \
  --lease-seconds 1800
python3 -m orchestrator heartbeat KC-104 --worker local-codex-orchestrator-01
python3 -m orchestrator release KC-104 \
  --worker local-codex-orchestrator-01 \
  --to REVIEW \
  --reason 'Implementation candidate ready'
python3 -m orchestrator history KC-104
```

An expired lease is not stolen or reassigned. It requires manual inspection and recovery.

## Scope limit

There is no `run` command. Launching Claude, Codex, shell commands, BitBake, worktrees, pull requests, or background workers is not implemented in v0. Those capabilities require separately reviewed later tasks.

## Tests

```bash
python3 -m orchestrator --help
python3 -m unittest discover -s orchestrator/tests -v
```
