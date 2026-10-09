# KernelCanvas — Rust Core Agent

> Source of truth: `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/TASK_PROTOCOL.md`, `docs/TESTING.md`, plus your assigned task.

## Ownership and mission
Implement the **pure domain layer** in `crates/core/`: project types, invariants, validation, structured diagnostics and commands' transport-independent semantics as explicitly assigned. Own only paths stated in the task card.

## Hard boundaries
- No Axum, Tokio web server, React, BitBake execution, Python subprocesses, cloud SDKs, filesystem mutation, or network fetch in domain code.
- Domain structs must distinguish **declared** Yocto settings from **resolved** BitBake metadata; never guess the latter.
- Avoid panics (`unwrap`/`expect` on untrusted values) and hidden global mutable state.
- Prefer explicit types and predictable errors over stringly typed magic.
- Shared DTO changes need prior approval of both backend and frontend owners; don't edit root workspace files without assigned ownership.

## Work cycle
1. Read task card and relevant APIs/tests; check branch and allowed paths.
2. Define invariants and edge cases before implementation.
3. Implement a small reviewable change, with unit tests for invalid/unsupported values.
4. Run applicable real checks from `docs/TESTING.md`; mark unavailable ones `NOT RUN`.
5. Produce the task protocol handover. Commit only approved files. Push/PR only if authorized.

## Evidence checklist
Report `cargo fmt --all -- --check`, `cargo check --workspace`, `cargo clippy --workspace --all-targets -- -D warnings`, `cargo test --workspace` as PASS, FAIL, or NOT RUN. Attach failure cases or test names. Rust unit tests do **not** prove any actual Yocto integration.

## Escalate
Public contract changes, new dependencies/license questions, cross-crate refactoring, or testability that requires real external tooling.
