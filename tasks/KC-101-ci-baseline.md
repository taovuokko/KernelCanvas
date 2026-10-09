# KC-101 — Baseline GitHub Actions CI

> **Seed task specification**, not a claim of assignment or reservation. Before starting, coordinator must confirm ID uniqueness, create/link its GitHub issue, set named owner and *different* reviewer, and mark `IN_PROGRESS` there.

- Milestone: M0 | Priority: P0
- Role: `agents/INFRA.md`
- Status: READY (unassigned)
- Owner: UNASSIGNED | Reviewer: UNASSIGNED
- Dependencies: Rust workspace + React app present on `main`; inspect actual source before implementation.
- Product requirement: foundation infrastructure, not a new Yocto feature.

## Outcome
On PRs and pushes to `main`, GitHub Actions checks the **existing** Rust workspace and React frontend. No real BitBake run, secrets or self-hosted workers.

## Allowed paths
- `.github/workflows/ci.yml` (create; choose another filename only with coordinator approval)

## Forbidden scope
- No edits to Rust/React application code, package lockfiles, `Cargo.toml`, root policy docs, repository settings or secrets.
- No bypass (`|| true`), no intentionally non-blocking test failures, no mock green steps.
- No automatic release, push, deploy, merge or unapproved external services.

## Acceptance criteria
- [ ] GitHub Actions triggers on PRs to `main` and `main` push.
- [ ] Workflow uses least-privilege permissions and checks out code.
- [ ] Rust fmt/check/clippy/test run and cause a failing status on failure.
- [ ] Frontend dependencies install reproducibly using the **actual tracked lockfile** (`npm ci` when npm lockfile is present), and production build runs.
- [ ] If the scaffold/lockfile is missing, task is marked BLOCKED with an exact prerequisite, not a fake pass.
- [ ] Workflow avoids expensive Yocto builds, dangerous privilege grants and untrusted secret injection.
- [ ] PR run and `main` run handling is sensible (e.g. PR concurrency cancellation but keep main checks).
- [ ] CI run URL or reason `NOT RUN` recorded; reviewer validates results independently.

## Verification
Before PR: list real `Cargo.toml`, `apps/web/package.json`, `apps/web/package-lock.json` status; run available local baseline checks from `docs/TESTING.md`; lint YAML if available. Only claim CI PASS after actual GitHub Actions completes on the PR.

## Authorization required
Maintainer authorizes GitHub pushes and PR creation. No auth token/config change or secrets access. Merge remains maintainer-controlled.

## Handover
Task, branch, PR link, exact jobs/steps, environment/tool versions, local checks status, CI URL/status, risks, reviewer questions, next task.
