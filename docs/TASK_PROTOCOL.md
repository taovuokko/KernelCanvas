# KernelCanvas — Agent Task Protocol

> **Status:** Foundation specification v0.1 — manual coordination is operational; autonomous scheduling is **not implemented**.
> **Applies to:** Maintainers, planner agents, implementation agents, reviewers, and future orchestration software.
> **Companion documents:** `AGENTS.md`, `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/INTEGRATION.md`, `docs/TESTING.md`.

## 1. Purpose and operating model

This protocol makes work safe, repeatable, and transferable between independent agents. It adapts the public Craft projects' bounded-module work and test evidence, plus iw4L's isolated-workspace/explicit-handover idea, to a local-first Yocto IDE.

**Current stage — manual coordinator:** A human maintainer explicitly assigns tasks, ensures ownership is unique, creates/approves an agent worktree, and decides which changes merge. An agent autonomously implements its *assigned* bounded task. A GitHub issue, Markdown card, or `READY` label is **not an atomic distributed lock**. Do not launch two agents on the same task or shared files merely because both see an available issue.

**Future stage — orchestrated:** A scheduler may atomically claim tasks, grant time-bounded leases, run agents and request independent reviews. The future service must implement the invariants in §10 before it is trusted. Nothing in this document claims that service already exists.

## 2. Authority and source of truth

1. Owner-approved `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, and accepted entries in `docs/DECISIONS.md` govern product behavior.
2. `AGENTS.md` governs general safety and agent behavior.
3. This file governs task state, assignment, handover, and agent coordination.
4. `docs/INTEGRATION.md` governs branches, CI and merge decisions; `docs/TESTING.md` governs test evidence.
5. The individual issue/task card defines the permitted scope and acceptance criteria. It cannot override security rules or accepted architecture.

**Canonical shared task record for the initial phase:** a GitHub issue (or a maintainer-controlled local task card when offline), with the task ID and current owner. Pull requests link to it. An ignored `.agent-work/` folder is scratch space **only**; never rely on it to communicate between worktrees or machines. Avoid a frequently edited central `STATUS.md` that every concurrent agent must modify.

## 3. Task identity and required fields

Task IDs use `KC-NNN` (e.g., `KC-008`), assigned once by the coordinator; **do not infer a GitHub issue number equals the task ID**. One card describes one reviewable outcome, not an entire product subsystem.

Each card must include:

| Field | Required content |
| --- | --- |
| ID and title | `KC-008 — Read-only kas manifest import` |
| Milestone / priority | `M1`, `P0/P1/P2` from `docs/ROADMAP.md` |
| Owner and reviewer | Distinct named humans/agent runs; reviewer cannot self-approve |
| Status | One of the task states in §4 |
| Goal / user-visible outcome | What demonstrably works when finished |
| Allowed paths | File and directory ownership; list shared-file exceptions |
| Forbidden scope | What must not change in this task |
| Dependencies | IDs and needed contracts; each must be satisfied before coding |
| API/format contracts | DTOs, fixtures, errors, changes requiring approval |
| Acceptance criteria | Objective, testable checklist |
| Expected verification | Commands/fixtures and Yocto evidence tier |
| Risk / approval | Any filesystem write, network access, code execution or license review |
| Handover link | PR/commit and evidence, once available |

**Suggested GitHub labels:** `status:ready`, `status:in-progress`, `status:blocked`, `status:review`, `status:done`, `area:frontend`, `area:core`, `area:yocto`, `area:qa`, `risk:high`. Labels aid filtering but do not reserve a task.

### Copyable issue template

```md
# KC-XXX — <short outcome>
Milestone: M0 | M1 | M2 | M3 | M4 | M5 | M6
Priority: P0 | P1 | P2
Owner: <person/agent-run ID or UNASSIGNED>
Reviewer: <different person/agent-run ID>
Status: BACKLOG | READY | IN_PROGRESS | BLOCKED | REVIEW | DONE | CANCELLED

## Outcome
<one measurable user or engineering outcome>

## Scope
Allowed paths: ...
Forbidden paths/behaviors: ...
Dependencies: ...
Agreed contracts/fixtures: ...

## Acceptance
- [ ] ...
- [ ] ...

## Verification
Expected: ...
Yocto evidence tier: none | fixture | metadata | image-build | QEMU-boot | hardware

## Risks and authorizations
<e.g. no external downloads, no real BitBake execution>

## Handover
<filled by implementing agent; link PR/commit/evidence>
```

## 4. State machine (task-level versus agent-level)

**Task-level states** are persisted in the shared task record:

```text
BACKLOG -> READY -> IN_PROGRESS -> REVIEW -> DONE
               \         |          |
                \        v          v
                 +----> BLOCKED <---+
                            |
                            +--> READY (reassigned/re-scoped)
Any non-DONE task -> CANCELLED (maintainer decision)
```

- `BACKLOG`: unscoped idea; agent must not start coding.
- `READY`: dependencies and acceptance criteria are specified; coordinator may assign it.
- `IN_PROGRESS`: one explicit owner, own worktree/branch, assignment timestamp.
- `BLOCKED`: precise blocker and next required decision; preserve work and handover.
- `REVIEW`: PR and reproducible evidence delivered; no further scope expansion without reviewer request.
- `DONE`: reviewed, integrated into protected main, and the task card updated by coordinator.
- `CANCELLED`: explicitly stopped; not silently treated as complete.

Allowed recovery: `REVIEW -> IN_PROGRESS` for requested fixes, or `BLOCKED -> IN_PROGRESS` for an existing owner after the blocker is resolved. Do not auto-mark `DONE` because tests pass locally.

**Agent-level handover status** is different: `PART` (incomplete but transferable), `READY_FOR_REVIEW` (candidate delivered), `BLOCKED` (specific impediment), and `FINAL` (owner's assigned implementation scope completed). `FINAL` does **not** mean task-level `DONE`.

## 5. Manual work cycle: one agent per task

### A. Plan and reserve (coordinator)

1. Choose a `READY` task whose dependencies are merged or whose interface contracts have been approved.
2. Confirm allowed paths do not overlap with currently active task ownership. If they must overlap, serialize tasks or approve a contract-first split.
3. Assign one owner and one *different* reviewer on the shared card. Mark `IN_PROGRESS` and record branch name.
4. Explicitly authorize any fetching, external builds, workspace writes, PR creation/push or installs needed for this task.
5. Ensure the task is small enough for one branch and one coherent PR; split broad tasks.

### B. Start isolated workspace (coordinator or authorized agent)

```bash
# From clean KernelCanvas repository root; main is checked out here.
git status --short --branch
git fetch origin
git pull --ff-only origin main
TASK=KC-008
TOPIC=kas-import
WT="../kc-${TASK}-${TOPIC}"
git worktree add "$WT" -b "agent/${TASK}-${TOPIC}" main
cd "$WT"
export CARGO_TARGET_DIR="$PWD/target/agent-${TASK}"
git status --short --branch
```

This assumes the repository has an `origin` remote, `main` exists, the base worktree has no relevant uncommitted edits, and the chosen branch/worktree name is unused. **Never use `git worktree add -f`, `git clean -fdx`, or force-push to paper over collisions.** The coordinator controls creation when several workers are active.

### C. Execute (implementation agent)

1. Read `AGENTS.md`, project docs, task card, predecessor handover and affected source/tests.
2. Confirm branch, assigned scope, architecture boundaries and pre-existing changes.
3. Implement the smallest complete slice; add failure/edge-case tests.
4. Run the applicable checks in `docs/TESTING.md`. Preserve exact output or reproducible command references.
5. If an external API or shared contract must change, **stop and request contract coordination before editing**. Do not silently modify another agent's branch.
6. Commit small reviewable units to the task branch. Push/open a PR only if the task explicitly authorizes it.
7. Deliver a handover (§7), and mark task `REVIEW` when an actual PR is ready.

### D. Independently review and integrate (reviewer/coordinator)

1. Check changed paths, contracts, security side effects and the evidence tier.
2. Verify mandatory checks independently in CI or a clean checkout as appropriate.
3. Request fixes without broadening the feature scope, or merge using `docs/INTEGRATION.md`.
4. Mark `DONE` only after merge is confirmed; record merged commit/PR.
5. Release file ownership, and only then schedule downstream tasks.

## 6. Dependency coordination

- Prefer **contract-first** tasks when frontend/API/Yocto components depend on the same model. Approve a typed DTO, error schema and fixture; then distribute independent implementations.
- Treat root `Cargo.toml`, `Cargo.lock`, API schemas, `.github/workflows/`, global registries, and policy documents as **shared hotspots**. Only one designated agent edits a shared hotspot at a time.
- An agent that discovers required unassigned work files a follow-up task or adds it to handover; it does not quietly seize that work.
- No agent may modify another agent's active worktree, hidden scratch folder or partially committed task branch.
- A task dependency is satisfied by an accepted contract for independent mock-based work, or by a **merged** implementation when concrete behavior is required. State which in the card.
- Limit initial concurrency to **two implementers plus one independent reviewer**. Increase only after measuring conflict rate, failed CI, PR latency and review load.

## 7. Mandatory handover (durable and reviewable)

Post a handover in the issue/PR (or commit a non-secret task artifact under a coordinator-assigned docs path). Do not place the *only* copy in ignored `.agent-work/`.

```text
Task: KC-XXX — <title>
Owner / branch / commit: <identity> / agent/KC-XXX-... / <sha>
Agent status: PART | READY_FOR_REVIEW | BLOCKED | FINAL
Task status requested: IN_PROGRESS | BLOCKED | REVIEW
Changed paths: ...
Implemented behavior: ...
Contracts / migrations changed: ...
Reproduction steps: ...
Checks (with actual environment):
  PASS: <exact command> — <result>
  FAIL: <exact command> — <result>
  NOT RUN: <exact command> — <why>
Yocto evidence: none | fixture | metadata | image-build | QEMU-boot | hardware
Security, licensing, network and data impacts: ...
Known gaps / risks: ...
Next action and owner: ...
PR / issue / artifact links: ...
```

A `PART` handover must include what works, where execution stopped, and a precise next step. **Never invent passing tests, logs, version support or merged commits.** Remove secrets from logs before sharing.

## 8. Failure, timeouts and takeover

**Manual mode:** A task whose owner disappears is flagged by the coordinator; do not let another agent silently take over. Inspect the issue/PR, branch, unpushed work and handover. Explicitly revoke the old assignment before reassigning. If work is missing, mark evidence as unknown and re-run tests.

- CI failure: return `REVIEW -> IN_PROGRESS` for a focused fix; don't weaken tests merely to pass.
- Merge conflict: stop the integration; have the task owner rebase safely or choose an explicit maintainer-approved resolution.
- Scope explosion: split into follow-up tasks; avoid giant multi-feature PRs.
- Risk discovered (untrusted execution, credentials, filesystem corruption): `BLOCKED`, preserve evidence, escalate.
- Retry: use a fresh or clearly owned worktree and track the attempt. Prevent two attempts from independently merging the same outcome.
- Abandoned run: never delete a worktree with uncommitted work until reviewed/backed up and authorized.

## 9. Review and release boundaries

The implementer may run unit tests and self-review, but **cannot be the sole final approver** of their own risky PR. Reviewer must inspect authorization surfaces, input handling, dependency boundaries, reproducibility and meaningful tests. The maintainer retains control over repository permissions, external publishing, production deployment, license policy and security exceptions.

Use `docs/INTEGRATION.md` for the precise merge checklist. Review acceptance is not a permission to release to customers or expose local APIs to the public internet.

## 10. Future orchestration requirements (PLANNED, not implemented)

If a scheduler is added, it MUST provide:

1. **Durable atomic claim:** transactional task state update from `READY -> IN_PROGRESS`, unique `(task_id, active_attempt)` ownership; GitHub labels alone are insufficient.
2. **Lease + heartbeat:** owner/run ID, lease expiry, bounded renewal; expired claims move to a recoverable state after verification, not directly to a second concurrent writer.
3. **Resource locks:** path/contract ownership with deadlock avoidance; shared hotspots are serialized.
4. **Run identity:** link each task attempt to model/tool, branch, worktree, commit, timestamps, authorization and cost ceiling (without storing credentials).
5. **Dependency graph:** dispatch only tasks with satisfied prerequisites; contract dependencies differ from merge dependencies.
6. **Review gate:** agents submit candidates; CI and an independent reviewer decide merge eligibility. No unconditional auto-merge.
7. **Retry policy:** bounded retries, backoff, failure categories, manual escalation for repeated failures or destructive behavior.
8. **Auditability:** append-only state/event history, redacted evidence and exact CI/test outcomes.
9. **Process supervision:** timeouts, cancellation, disk/CPU quotas, orphan cleanup and safe workspace disposal.
10. **Least privilege:** narrow GitHub permissions, no unrestricted shells on trusted hosts, no unapproved remote builds or secret access.

**Do not start building the orchestrator during M0** unless the maintainer explicitly changes the roadmap. Prove the manual protocol first.

## 11. Initial trial: two independent tasks

Once the M0 repo and baseline checks work, assign two non-overlapping tasks (IDs reserved by coordinator):

- **Backend agent:** add a minimal, safe localhost API health/readiness route within `crates/api/`, with a deterministic test. No Yocto execution, no public network binding.
- **Frontend agent:** add a project welcome/empty-state view in `apps/web/` with clear unsupported/not-connected copy and a production build check.

Approve API contracts in advance if the frontend actually calls the backend. An independent reviewer inspects each PR. Measure conflict count, time-to-review, test failures and cleanup effort before adding more agents.

## 12. Non-negotiable success criteria

- Every active task has exactly one assigned owner and one separately identified reviewer.
- Every change maps to a task ID, reviewable branch and evidence-bearing handover.
- No task is `DONE` before integration is verified.
- Overlapping edits and shared contracts are explicitly coordinated.
- Real Yocto execution requires authorization and valid test-environment claims.
- The system remains safe to stop and resume without reconstructing a chat transcript.

---

References for inspiration only (no dependence on unpublished files):
- PhotoCraft public agent instructions: https://github.com/storytold/photocraft/blob/main/AGENTS.md
- WordCraft public agent instructions: https://github.com/storytold/wordcraft/blob/main/AGENTS.md
- iw4L public handover/work-area guidance: https://github.com/vladtrc/iw4L
