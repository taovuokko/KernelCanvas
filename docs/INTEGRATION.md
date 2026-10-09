# KernelCanvas — Git, Pull Request and Integration Policy

> **Status:** Initial manual integration procedure v0.1. GitHub branch protection, CI workflows and auto-merge are **not presumed to exist**.
> **Companions:** `AGENTS.md`, `docs/TASK_PROTOCOL.md`, `docs/TESTING.md`, `docs/ARCHITECTURE.md`.

## 1. Integration goals

Make independent agent changes easy to inspect, reproduce and combine **without losing anyone's work**. Adapt the Craft projects' focused commits/architecture gates and iw4L-style isolated workspaces to a conservative GitHub PR flow.

**Invariants:**

- One explicitly assigned task → one responsible implementation owner → one task branch → one PR (unless a reviewer explicitly approves a split).
- A separately designated reviewer verifies readiness; agent self-report is not a merge authorization.
- Protected `main` contains only reviewed integration points; **no routine direct pushes by feature agents**.
- Shared schema/dependency changes are contract-first and serialized.
- A failed check or conflict stops integration; no force merge, history rewrite, bypass or test-suppression by default.
- `git worktree`, PR checks, branch protection and workflow scripts serve different purposes; none automatically replaces the others.

## 2. Repository branch and naming conventions

- Integration branch: `main`.
- Agent branches: `agent/KC-XXX-short-topic` (e.g. `agent/KC-008-kas-import`).
- Human fix branches: `fix/KC-XXX-short-topic` when needed.
- Commit examples: `feat(project-io): import declared kas manifest (KC-008)`; `test(api): reject invalid project path (KC-010)`.
- Do not put secrets, generated Yocto images, caches, private vendor sources or large build artifacts into commits.

`KC-001`–`KC-007` in `docs/PRODUCT.md` identify product requirements. A coordinator assigns unique development task IDs and records which requirements each one covers; do not treat example IDs as already-open GitHub issues.

## 3. Configure GitHub repository (maintainer action)

Before multiple agents submit code, the maintainer should configure a `main` branch ruleset/branch protection in GitHub repository settings:

1. Require pull requests before merging; prevent direct pushes from ordinary agents.
2. Require at least one **independent review** for material changes; protect against self-approval.
3. Require status checks **after the CI workflow exists and its check names are known**. Do not guess check names now.
4. Prefer dismissing stale approvals on changes to sensitive areas and prevent force pushes/deletion of `main`.
5. Restrict who may bypass the rules, and enable secret scanning/dependency alerts where available.

These are **configuration recommendations**, not claims that GitHub enforces them already. Avoid putting AI-agent credentials into shared local environments.

## 4. Branch setup (coordinator; manual mode)

On the primary checkout:

```bash
cd ~/HDD-koodaus/KernelCanvas
git status --short --branch
# Proceed only if this checkout is in a safe/clean state.
git fetch origin
git switch main
git pull --ff-only origin main

git worktree add ../kc-KC-008-kas-import \
  -b agent/KC-008-kas-import main
```

The task ID and path are **illustrative**. Use a new unique ID and directory for each assignment.

In the new worktree:

```bash
cd ../kc-KC-008-kas-import
export CARGO_TARGET_DIR="$PWD/target/agent-KC-008"
git status --short --branch
```

`CARGO_TARGET_DIR` isolates Cargo build output for this task; don't reuse another agent's target directory. Add `target/` to `.gitignore`, and monitor disk capacity as parallel Rust builds grow.

Never use `git worktree add --force` merely to reuse an actively owned directory. Check `git worktree list` when diagnosing collisions.

## 5. Before implementation: interface and file ownership agreement

Record allowed paths and shared-file exceptions on the task card. The coordinator must explicitly serialize edits to:

- Root `Cargo.toml`, `Cargo.lock`, and workspace-wide tooling.
- Command/API schema or public DTO definitions.
- CI workflows and security/policy configuration.
- Central registries and high-churn docs such as architecture/roadmap.

If backend and frontend depend on the same new command, approve a typed schema/fixture in a separate contract-first change before running both agents. Implementers can then work against that contract in their separate branches.

An agent may inspect any code needed to understand the system, but **editing a shared file without authorization is not permitted**.

## 6. Prepare and publish a PR

In the task worktree, after the relevant checks:

```bash
# Review exactly what is staged and commit only assigned paths.
git status --short
git diff --check
git diff --stat

git add <explicit-approved-paths>
git diff --cached --check
git commit -m "feat(project-io): add safe kas importer (KC-008)"

# Only if remote pushes were authorized for this task:
git push -u origin agent/KC-008-kas-import

# Requires GitHub CLI authentication and permission to create a PR:
gh pr create --base main --head agent/KC-008-kas-import \
  --title "KC-008: read-only kas import" \
  --body-file /path/to/approved-pr-description.md
```

`<explicit-approved-paths>` is a placeholder: replace it with real paths, not the literal token. Prefer explicit `git add path1 path2` over indiscriminate staging of unknown changes. `--body-file` must point to an existing file prepared for the task; otherwise use the interactive `gh pr create` flow.

The PR description must link the task record and contain:

- Scope and user/engineering outcome.
- List of changed modules and API/format contracts.
- Tests actually run: `PASS`, `FAIL` and `NOT RUN` with reasons.
- Yocto verification tier and pinned environment if applicable.
- Filesystem, security, licensing and networking implications.
- Known limitations, reviewer questions and handover.

## 7. PR review checklist

Reviewer should independently verify:

- [ ] Task ID, assigned owner and permitted file paths are correct.
- [ ] Diff stays within product MVP/approved decisions and module boundaries.
- [ ] Tests actually cover claimed behavior and failure cases.
- [ ] Security-sensitive effects (imports, writes, builds, credential handling, localhost API) were considered.
- [ ] Unknown metadata is not silently discarded; false BitBake parity claims are not introduced.
- [ ] Shared contracts have explicit dependent-task coordination.
- [ ] New dependencies/assets have license and provenance review.
- [ ] CI statuses are current, required checks pass, and there are no unexplained failures.
- [ ] PR description/handover names remaining gaps honestly.

When a command writes local configuration, executes BitBake/recipes, changes authorization or imports templates/archives, require heightened review and exact negative-case tests.

## 8. Resolve conflicts without discarding work

A task owner may update their own branch after authorization:

```bash
# In the agent's worktree, with no uncommitted changes.
git fetch origin
git status --short --branch
git rebase origin/main
```

If rebase reports conflicts:

1. Stop and inspect conflicted files; identify the owner of changed contracts.
2. Resolve carefully **only** when the resolution is unambiguous and within task scope; otherwise request coordinator review.
3. Re-run tests affected by conflict resolution.
4. Continue with `git rebase --continue` only when resolution is reviewed as appropriate.
5. If unsafe, use `git rebase --abort`; preserve prior state and escalate.

Rebase changes branch history. **Do not force-push remotely** without explicit owner approval. For a published branch, a maintainer may prefer merging `origin/main` into the feature branch or using a reviewed, narrowly scoped `--force-with-lease` policy; neither is an automatic agent permission. Never use `git reset --hard` or `git clean -fdx` to hide issues.

## 9. Merge decision and post-merge cleanup

1. Reviewer requests changes or approves according to repository rules.
2. Maintainer/integrator confirms relevant green CI, no missing high-risk approvals, and valid handover.
3. Merge via GitHub protected PR flow (preferred); no assumption of automated merger.
4. Confirm merge commit and corresponding issue before marking the task `DONE`.
5. Release ownership/locks manually and schedule dependent tasks.
6. Remove worktree **only after** ensuring there are no uncommitted/untracked important files:

```bash
# From the primary checkout (after verified merge):
git worktree list
git -C ../kc-KC-008-kas-import status --short
# Only when the worktree is genuinely safe to remove:
git worktree remove ../kc-KC-008-kas-import
# Delete local branch only when it is fully integrated and safe:
git branch -d agent/KC-008-kas-import
```

If branch deletion refuses, inspect merge history; don't substitute `-D` without explicit approval. Agent scratch data in the worktree may be ignored by Git yet valuable: check it before removal.

## 10. CI strategy and scarce resources

Start with the checks in `docs/TESTING.md` and add more only when their commands exist. Prefer:

- Fast, predictable, low-cost checks on PRs.
- A small supported platform matrix (Fedora/Linux for local Yocto development).
- Pinned fixtures and deterministic fake-adapter tests.
- Real BitBake metadata checks when prepared tooling exists.
- Expensive image builds on dedicated scheduled/manual/release workers.

PhotoCraft-style CI cancellation can reduce wasted PR work, but **do not cancel all `main` verifications on rapid successive merges**, or the branch may never receive a completed validation run. Merge sequencing must account for jobs and caches.

## 11. Risk-based integration policy

| Change class | Minimum review |
| --- | --- |
| Docs-only, no policy/security change | Normal reviewer + link integrity |
| Pure Rust model or visual shell | Relevant tests + independent review |
| Public command/DTO contract | Contract approval + dependent-worker notification |
| Project write/import/export | Security review + round-trip/negative tests |
| BitBake command/process execution | Execution policy + owned-process/cancel tests + real-tool tier declaration |
| Authentication, CI permissions, remote builders, billing | Explicit maintainer approval and separate threat/design review |

No agent can automatically authorize a broadened trust boundary because its CI checks are green.

## 12. Integration success metrics (optional future scorecard)

Track monthly or per milestone:

- PR review latency and change-request rate.
- File ownership violations and rebase conflicts.
- Failed CI/merge regressions, reopen count and rollback causes.
- Verified feature coverage by tier, not raw branch or commit counts.
- Agent compute/build cost per accepted task.

Do not optimize for the number of branches or merged lines of code. Optimize for safe delivered capability and reliable support of real Yocto projects.
