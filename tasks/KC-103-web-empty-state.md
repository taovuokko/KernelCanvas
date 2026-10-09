# KC-103 — Honest visual empty-project screen

> Seed task, not assigned. Coordinator checks ID uniqueness, creates/links GitHub issue, records owner/reviewer, and checks the current UI scaffold.

- Milestone: M0 | Priority: P0
- Role: `agents/FRONTEND.md`
- Status: READY (unassigned)
- Owner: UNASSIGNED | Reviewer: UNASSIGNED
- Dependencies: actual Vite/React app is present; independent of core diagnostics and CI implementation.

## Outcome
A polished, accessible empty state in KernelCanvas Studio that explains the product and the upcoming Yocto project import. The current UI must not pretend import/build functionality exists.

## Allowed paths
- `apps/web/src/**`

## Forbidden scope
- No `apps/web/package.json`, lockfiles, Rust, API, real Yocto calls or shared styles outside `apps/web/src/`.
- No fake build logs, fake device status or active controls that cannot do their advertised actions.

## Acceptance criteria
- [ ] Responsive first screen with clear name and purpose.
- [ ] One or more honest disabled / "coming later" affordances for future import/build functions, or no action control at all.
- [ ] Accessible headings and keyboard-safe design; loading/errors are not faked.
- [ ] Existing frontend production build succeeds, or exact prerequisites are reported.
- [ ] No new packages or silent public API assumptions.

## Verification
`npm run build --prefix apps/web` when npm dependencies are installed. Optional lint/tests only when configured. Describe manual visual/accessibility review and capture screenshot if possible.

## Handover
Paths, screenshot/description, build output, remaining real-backend dependencies, commit/PR link once authorized.
