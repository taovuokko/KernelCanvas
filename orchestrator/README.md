# KernelCanvas Orchestrator

This package is a local, standard-library-only scheduler and bounded single-task
execution loop. It stores durable task state, leases, attempts, evidence locations,
and transition history in SQLite. It does not contact GitHub or verify issue URLs
over the network.

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
python3 -m orchestrator attempts KC-106
```

An expired lease is not stolen or reassigned. It requires manual inspection and recovery.
Lease durations must be between 1 and 604800 seconds (seven days), inclusive.
Heartbeats preserve the original duration and reject invalid stored durations rather
than extending them.

## Autonomous run

`run` claims one queued task atomically, verifies its exact worktree and branch,
invokes the KC-105 isolated Codex implementer, runs fixed quality checks inside
Bubblewrap, and invokes the read-only KC-105 Claude reviewer. The reviewer must
return a strictly parsed `APPROVE` or `REQUEST_CHANGES` JSON verdict. At most two
correction rounds follow the initial implementation.

The task card's `## Allowed paths` list is authoritative. A run rejects changes
outside that list, changed symlinks, unsafe/unbounded review input, a main checkout,
the wrong branch, and worktrees outside the approved workspace root. Review input
contains the branch diff, staged diff, unstaged diff, and bounded UTF-8 contents of
relevant untracked files.

The only current quality-check IDs are `orchestrator-tests` and
`orchestrator-help`. They map to fixed argument vectors and run inside Bubblewrap
with an empty home, cleared environment, private process namespace, read-only
system mounts, and only the assigned worktree mounted writable. As in KC-105,
this does not provide kernel-enforced network egress filtering. There is no
direct-host fallback when Bubblewrap is missing or fails.

Example dry run (does not open or mutate SQLite, launch a process, or create logs):

```bash
python3 -m orchestrator run KC-106 \
  --worker local-codex-KC-106 \
  --reviewer local-claude-KC-106 \
  --workspace-root /home/user/worktrees \
  --worktree /home/user/worktrees/kc-KC-106-autonomous-loop \
  --branch agent/KC-106-autonomous-loop \
  --evidence-root /home/user/.local/state/kernelcanvas/runs \
  --dry-run
```

An actual run additionally requires `--authorize-real-execution`. The flag records
explicit authorization; it does not provide credentials. By default the adapters
still use empty sandbox homes and do not inherit personal API, GitHub, SSH, cloud,
or model CLI credentials, so an unauthenticated real CLI fails closed. In
particular, `~/.claude` and `~/.codex` are never selected automatically. If a
non-system CLI binary is used, its narrow non-sensitive runtime directory must be
passed with `--codex-runtime-root` or `--claude-runtime-root`.

```bash
python3 -m orchestrator run KC-106 \
  --worker local-codex-KC-106 \
  --reviewer local-claude-KC-106 \
  --workspace-root /home/user/worktrees \
  --worktree /home/user/worktrees/kc-KC-106-autonomous-loop \
  --branch agent/KC-106-autonomous-loop \
  --lease-seconds 1800 \
  --timeout-seconds 300 \
  --check orchestrator-tests \
  --check orchestrator-help \
  --evidence-root /home/user/.local/state/kernelcanvas/runs \
  --authorize-real-execution
```

## Supervised subscription-auth profiles

Optional live Claude and Codex authentication is restricted to explicitly selected
profiles with this exact layout:

```text
~/.local/share/kernelcanvas/auth/
├── claude/<profile-name>/
└── codex/<profile-name>/
```

The auth root, provider directory, and profile directory must already exist, be
owned by the current user, and grant no group/other permissions (normally mode
`0700`). A profile must be an absolute path and one direct child of its provider
directory. Traversal, symlink escapes, broad/sensitive roots, filesystem mount
points, and profiles for the other provider are rejected. The orchestrator neither
discovers profiles nor falls back to a personal CLI home.

Use `CLAUDE_CONFIG_DIR` or `CODEX_HOME` while interactively creating/logging into
the dedicated profile. Do not copy or print its token files. Once the maintainer
has prepared it, select it for a supervised run with both the existing execution
authorization and the additional exposure acknowledgement:

```text
  --codex-auth-profile /home/user/.local/share/kernelcanvas/auth/codex/supervised \
  --claude-auth-profile /home/user/.local/share/kernelcanvas/auth/claude/supervised \
  --acknowledge-auth-profile-exposure \
  --authorize-real-execution
```

Each selected profile is writable-mounted only at the relevant sandbox path and
exposed to the CLI through `CODEX_HOME` or `CLAUDE_CONFIG_DIR`. This permits CLI
configuration reads and token refresh without binding host home or `/`.

**Security limitation:** anything running inside that model sandbox may be able to
read the mounted authentication files. This supervised mode preserves the
Bubblewrap filesystem boundary around the rest of the host, but it is not a
credential-isolation solution and does not protect the profile from an adversarial
agent-controlled shell command. Log redaction, including JSON token-field
redaction, is defense in depth only and is not an exfiltration boundary.

The lease duration must cover every bounded phase. The loop renews and validates
the owner plus opaque lease token before each phase, holds an immediate SQLite
ownership guard while that bounded external phase runs, and revalidates before
releasing the guard. It stops without further work if ownership is invalid or
expired. A successful independent review releases the lease in `READY_FOR_PR`;
this never pushes, opens a PR, merges, publishes, or deploys.

## Task states

The scheduler's manual v0 path remains `QUEUED` → `CLAIMED`, followed by release
to `REVIEW`, `BLOCKED`, or `FAILED`. The autonomous loop adds lease-retaining
`CLAIMED` → `RUNNING` → `REVIEW`, bounded `REVIEW` → `RUNNING` correction rounds,
and final `REVIEW` → `READY_FOR_PR`. `DONE` remains a maintainer-only reviewed
integration operation.

## Scope and unattended-use limits

The loop is single-task and synchronous. It does not create/delete worktrees,
execute BitBake, call GitHub, push, open a PR, merge, publish, or deploy. It does
not provision model authentication. Optional dedicated profiles support supervised
live runs with the exposure limitation above; unattended credential-isolated runs
remain unsupported. Parallel workers and automatic expired-lease recovery remain
out of scope.

## Tests

```bash
python3 -m orchestrator --help
python3 -m unittest discover -s orchestrator/tests -v
```
