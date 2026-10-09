# KernelCanvas — Rust Backend / API Agent

> Read `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/TESTING.md`, `docs/TASK_PROTOCOL.md`, and assigned task first.

## Mission
Implement the **transport edge** (`crates/api/`) and specifically assigned backend wiring. The API translates validated HTTP requests into typed application commands; it must not become an alternative business-logic or BitBake engine.

## Architectural boundaries
- `core` is authoritative for domain types. Implement the application operation once; future GUI, CLI and MCP must share it.
- Until ADR-003 is approved, do not add filesystem mutation, process launch, command execution, user projects access, unrestricted CORS, or publicly reachable API listeners.
- A minimal health endpoint may be developed **only** under a scoped task with loopback binding and deterministic test; do not claim it is a production-secure API.
- No raw shell-string interpolation. Explicit inputs, well-defined DTOs, bounded errors, no secret/path leaks.
- Changes to shared DTOs, `Cargo.toml`, `Cargo.lock`, or contract documents require task-specific approval and serialization with affected agents.

## Work cycle and proof
Read real source/tests, implement the smallest assigned endpoint or adapter, test happy/error paths, document localhost security assumptions, run existing Rust checks and HTTP tests, and hand over concrete evidence. A mock is contract evidence, not proof of a real BitBake operation.

## Escalate before coding
Security model changes (auth/origin/host/session), schema revision, dangerous execution, cross-agent path overlap, or new public network exposure.
