# KernelCanvas — Development Orchestration Architecture

> Status: PROPOSED v0.3; no orchestrator implementation is assumed to exist.
> Applies to: the local AI-assisted **development process**, not KernelCanvas's user-facing Yocto application runtime.
> See also: `AGENTS.md`, `docs/TASK_PROTOCOL.md`, `docs/INTEGRATION.md`, `docs/TESTING.md`, and `docs/DECISIONS.md`.

## 1. Purpose

Build a small, reliable controller for assigning narrow engineering tasks to independent local CLI agents while preserving file ownership, auditable test evidence, and human control of PRs/merges. Use the existing CLI binaries (`claude`, `codex`) rather than vendoring their packages or building another LLM framework into the product.

Python owns workflow state and process lifecycle. Claude and Codex are replaceable, bounded subprocess adapters. SQLite is the **single local authority for active leases** once installed. GitHub Issues are an external tracking mirror, not an atomic lock. A local Markdown file or Issue comment alone must not be treated as a distributed lock.

## 2. Roles and boundaries

| Component | Responsibility | May edit product files? |
| --- | --- | --- |
| Human maintainer | Authorize tasks, trust-boundary decisions, push/PR, final merge | Yes |
| Python coordinator | Atomic lease, working directories, subprocess control, events, budgets | No by default |
| Claude planner | Read instructions; produce proposed plan, tests and file scope | No |
| Codex implementer | Edit only allowed paths in its assigned worktree | Yes, scoped |
| Deterministic test runner | Execute explicitly approved commands; retain exit codes/logs | No corrective edits |
| Claude reviewer (fresh session) | Independently review changed files, acceptance criteria and evidence | No |
| Integrator | Prepare PR with maintainer authorization; verify CI | No automatic merge |

The locally installed Claude Codex MCP connection can remain available for **interactive** sessions. The scripted coordinator must **not** enable nested agent dispatch through MCP: it invokes one designated CLI process per phase and explicitly disables reviewer MCP tools. This prevents untracked agent fan-out.

## 3. Versioned development phases

### v0 — KC-104: persistent scheduler foundation

- Python >= 3.11, standard library only (`sqlite3`, `argparse`, `pathlib`, `json`, `unittest`).
- A functioning `python3 -m orchestrator` CLI for initializing, registering, listing, claiming, heartbeating and transitioning tasks.
- SQLite transactional leases with unique owner, separate reviewer, expiration and event history.
- Local database under `${XDG_STATE_HOME:-~/.local/state}/kernelcanvas/orchestrator.sqlite3` (override via `KERNELCANVAS_ORCHESTRATOR_DB` for tests).
- No LLM subprocess spawning, no automatic GitHub API access, no push, no merge, no network, no third-party packages.

### v1 — KC-105: CLI adapters

- `ClaudeCLI` planner/reviewer and `CodexCLI` implementer behind testable Python interfaces.
- Explicit command argv, cwd, timeout, process-group cancellation, exit-code reporting and bounded logs.
- Read-only Claude reviewer session; Codex restricted to its task worktree; no nested MCP dispatch.
- A dry-run driver that prints the planned argv and redacted input without launching agents.

### v2 — KC-106: bounded repair loop

- Plan → implement → deterministic tests → independent review → limited fixes → candidate for PR.
- 3 repair rounds maximum, clear BLOCKED/FAILED states, no auto-approval or merge.
- Reproducible handovers, attempt directories and structured evidence.

### v3 — KC-107: two parallel implementers

- At most two simultaneously running Codex workers plus one serialized independent reviewer initially.
- Separate Git worktrees, Cargo target dirs, leases, locks and resource quotas.
- Shared files/contracts assigned to exactly one active task at a time.
- Crash recovery never launches a duplicate worker while the original process could still be alive.

Do not implement future phases in KC-104 merely because they are described here.

## 4. State model

Task states:

`QUEUED → CLAIMED → RUNNING → REVIEW → READY_FOR_PR → DONE`

Alternates: `BLOCKED`, `FAILED`, `CANCELLED`. `DONE` means a maintainer verified integration, not that an agent reported completion. An implementation failure may return to `RUNNING` only through an explicitly recorded retry transition under a valid lease.

Each transition records actor, UTC timestamp, prior and next state, attempt ID when relevant, reason, and bounded/redacted evidence pointers. Transitions must be validated in code; never accept an arbitrary status update simply because the CLI received a string.

Use SQLite `BEGIN IMMEDIATE` for claim transactions, `PRAGMA busy_timeout` for contention, and foreign keys. WAL mode is appropriate for a local single-host database, but do not move the same SQLite database onto an unreliable network filesystem.

Minimum tables (or equivalent normalized design):

- `tasks`: stable ID, issue reference, task-card path, state, allowed paths, last update.
- `leases`: task, owner, reviewer, lease token/identifier, expiry, heartbeat, active/released status.
- `attempts`: attempt number, worker, phase, start/end times, outcome, log location.
- `events`: append-only task history with actor, transition, reason and timestamp.

V0 tests must prove two competing claims cannot both win. An expired lease is **not proof that its old worker has stopped**. Automated reclaim/termination needs a later process-liveness design; until then, expired leases require human inspection before reassignment.

## 5. Assignment trust and GitHub

During KC-104 bootstrap a human coordinator verifies the live GitHub Issue from the Fedora host and explicitly authorizes the worktree. The local issue assignee may be the human maintainer; the local implementer/reviewer are separately recorded logical identities.

A future coordinator may fetch the Issue itself and atomically acquire a **SQLite** lease. The worker then receives an assignment envelope including task ID, allowed paths, branch/worktree, role, reviewer, issued/expiry time and lease ID. This envelope is operational evidence, **not** a cryptographic security boundary. Workers never need GitHub credentials merely to verify task assignment.

GitHub tracking may be temporarily unreachable. Fail closed for *new unverified work*; do not corrupt an active task or pretend a comment is a locking primitive. Never leak GitHub credentials into Codex/Claude worker environments or artifacts.

## 6. Security and cost limits

- Never use shell interpolation for subprocess execution; pass `list[str]` argv and explicit `cwd`.
- Protect state DB, logs and local paths; never commit them. Keep `.agent-work/` ignored.
- Redact tokens, environment variable secrets, authorization headers, private URLs and credential-bearing command lines before writing logs.
- Refuse unapproved worktree paths, repo edits, network installs, BitBake builds, deploys and destructive Git operations.
- No `danger-full-access`, unconditional bypass approvals or blanket use of `claude --dangerously-skip-permissions`.
- Track per-run time and optional API spend when exposed by the CLI. Do not treat an agent's textual 'PASS' as a test result.
- Use fresh Claude sessions for code review. Do not allow reviewer Edit/Bash/Agent/MCP tools in the automated path unless a narrow exception is approved.
- A non-zero exit code, timeout, interrupted test, malformed JSON or missing report is not a successful phase.

## 7. CLI contract: v0 design target

```console
python3 -m orchestrator init
python3 -m orchestrator add KC-104 --task-file tasks/KC-104-orchestrator-foundation.md --issue-url https://github.com/taovuokko/KernelCanvas/issues/N
python3 -m orchestrator status
python3 -m orchestrator claim KC-104 --worker local-codex-orchestrator-01 --reviewer local-claude-review-02 --lease-seconds 1800
python3 -m orchestrator heartbeat KC-104 --worker local-codex-orchestrator-01
python3 -m orchestrator release KC-104 --worker local-codex-orchestrator-01 --to REVIEW --reason 'Implementation candidate ready'
python3 -m orchestrator history KC-104
```

`N` is a placeholder until an Issue is created. These commands are **specifications**, not commands the repository can run before KC-104 is implemented. Final syntax should be tested and documented in the implementation PR.

## 8. Acceptance philosophy

KC-104 counts as implemented only if its real CLI executes and its concurrency/state-transition tests pass. KC-105 counts only if mocked process tests and at least one opt-in, authorized real Claude/Codex smoke test run. KC-106 counts only with failed-test/review/fix/retry scenarios. KC-107 counts only after a controlled two-worker experiment proves disjoint files and safe completion. Every milestone has independent review and human-controlled merge.
