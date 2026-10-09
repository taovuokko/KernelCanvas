# KC-102 — Typed, side-effect-free core diagnostics

> Seed task, not assigned. Coordinator checks ID uniqueness, creates/links a GitHub issue, records one owner and independent reviewer.

- Milestone: M0 | Priority: P0
- Role: `agents/CORE.md`
- Status: READY (unassigned)
- Owner: UNASSIGNED | Reviewer: UNASSIGNED
- Dependencies: current `crates/core` library builds; no dependency on CI-101 for local implementation.

## Outcome
Provide a small typed diagnostic value for future Yocto import/validation errors. Pure Rust, deterministic behavior, no new external dependencies for this slice.

## Allowed paths
- `crates/core/src/**`

## Forbidden scope
- No `Cargo.toml`, `Cargo.lock`, API, frontend, BitBake, filesystem/process/network or shared architecture-doc edits.

## Agreed provisional contract (confirm before starting)
- `Severity` enum: `Info`, `Warning`, `Error`.
- `Diagnostic` struct: `code`, `message`, `severity`.
- Expose a constructor/validation mechanism that rejects empty/whitespace-only codes and messages without panic.
- Public API details can be refined **within core** if tests make invariants explicit; cross-crate DTO mapping is a separate task.

## Acceptance criteria
- [ ] Types are public, documented and testable.
- [ ] Empty/whitespace code or message yields structured error rather than panic.
- [ ] Deterministic unit tests cover valid/invalid diagnostics.
- [ ] `core` does not gain transport, async runtime or Yocto dependency.
- [ ] Applicable Rust checks pass or exact blockers are reported.

## Handover
Tests and outputs, changed paths, public Rust type sketch, limitations, next integration owner, branch/PR URL when approved.
