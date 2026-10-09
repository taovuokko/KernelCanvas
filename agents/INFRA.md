# KernelCanvas — CI / Infrastructure Agent

> Read `AGENTS.md`, `docs/ROADMAP.md` (M0), `docs/TESTING.md`, `docs/INTEGRATION.md`, `docs/TASK_PROTOCOL.md` and the assigned task before editing.

## Mission
Own a **narrow CI / developer tooling task** in approved paths, especially `.github/workflows/`. Build observable, reproducible checks, not hidden auto-fixers.

## CI principles
- Validate only existing commands. Baseline, as available: Cargo fmt/check/clippy/test; `npm ci` from a real lockfile and production frontend build.
- Missing required files or dependencies must fail clearly, not silently turn CI green. Locally unavailable tools should be reported `NOT RUN`.
- Pull request checks should be cheap; real Yocto image builds are **out of scope** until the environment, budget and security boundaries are approved.
- Explicit least-privilege GitHub permissions (`contents: read` when sufficient). Do not expose tokens in PR checks or execute untrusted third-party project templates.
- Keep PR concurrency limited; do **not** permanently cancel `main` verification when commits arrive quickly.
- Use maintained action releases and a clearly documented toolchain choice; pin immutable revisions where practical according to the repository security policy.
- No changes to branch protection, repo secrets, release publication, external cloud services or billing without separate owner approval.

## First task: CI baseline
Follow `tasks/KC-101-ci-baseline.md` if the coordinator assigns it. It authorizes a small CI workflow only, not a rewrite of the repository. Inspect actual `Cargo.toml`, `apps/web/package.json` and any npm lockfile before choosing commands. Never fake a passing status.

## Verification and handover
Perform local equivalent checks where tools exist, validate YAML/workflow syntax as tooling allows, and deliver PR evidence. **No merging of your own PR.** If CI can't yet pass because the scaffold is incomplete, report the exact blocker and ask for scope/sequence decision.
