# KernelCanvas — Testing, Quality Gates and Evidence

> **Status:** Foundation quality policy v0.1. Commands shown below must be run **only when their projects and scripts actually exist**. No passing tests are implied by this document.
> **Companions:** `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/TASK_PROTOCOL.md`, `docs/INTEGRATION.md`.

## 1. Principle: tests prove behavior, not the existence of code

PhotoCraft-style measured verification is adapted to real embedded Linux workflows. Rust compilation is not evidence of BitBake compatibility; a mocked build is not a real image; a successful image is not a successful QEMU boot; QEMU boot is not validation on physical hardware. Every PR must state **which level was actually tested**.

Never replace a failing test with a stub, discard an unsupported input silently, or claim that passing UI tests prove a Yocto build.

## 2. Verification levels (report literally)

| Level | Meaning | Example evidence |
| --- | --- | --- |
| `NOT RUN` | Test unavailable, not attempted, or blocked | Exact blocker/reason |
| `UNIT` | Deterministic pure Rust/TypeScript functions | Command, test names, result |
| `FIXTURE` | File/parser/round-trip checks on checked-in inputs | Fixture name/hash, assertion result |
| `CONTRACT` | Typed HTTP/command adapter tests, fake external tools | Request/response test, error-path assertions |
| `METADATA` | Actual compatible BitBake/kas environment resolves data | Tool/release versions, command, log |
| `IMAGE BUILD` | Real BitBake finishes and produces specified artifact | Environment, image/target, exit, artifact name/hash |
| `QEMU BOOT` | Produced image boots in verified QEMU scenario | Boot procedure, observable success criteria |
| `HARDWARE` | Tested on named physical device/BSP | Hardware/revision, steps, result |

These are **evidence categories**, not a global linear certification. A PR can contain multiple categories and separate `PASS`, `FAIL`, `NOT RUN` entries.

## 3. Local baseline — run what exists

```bash
# Rust workspace, from repo root
cargo fmt --all -- --check
cargo check --workspace
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace

# Web app after npm dependencies exist
npm run build --prefix apps/web
```

Before running optional scripts, check `apps/web/package.json` rather than assuming a `lint`, `typecheck` or `test` script exists. Run configured scripts when present. If the workspace is only scaffolded or tools are missing, record `NOT RUN` with the reason.

**Examples of future commands (not currently available by documentation alone):** `cargo xtask layers`, `cargo xtask ci`, generated command-schema checks, real pinned Yocto build runners, visual snapshots. Add a real implementation and CI step before including them in mandatory gates.

## 4. Change-type matrix

| Change | Minimum relevant checks | Important edge cases |
| --- | --- | --- |
| `crates/core` models | Rust unit tests + baseline | Malformed input, overflow, unknown states |
| Engine command/DTO | Contract tests + permission/side-effect tests | Invalid ID, unauthenticated access, cancellation |
| API transport | HTTP integration + negative authorization/origin tests | Loopback bind, invalid request, leakage |
| React UI | Type/build checks + interaction state test or walkthrough | Error, loading, empty, unsupported state |
| `kas` import | Fixture tests + **no execution/no network** verification | Unsupported syntax, invalid path, private URL leakage |
| Yocto Python bridge | Fake adapter + real pinned version verification when enabled | Missing tooling, version mismatch, bad metadata |
| Config preview/apply | Diff/round trip + stale-write / failed-write tests | Comment preservation, symlinks, read-only files |
| Local build runner | Process/stream/cancel tests with fake worker | Exit status, child cleanup, timeout, log truncation |
| `.kcanvas` / template | Round trip + hostile input + provenance checks | Zip slip, zip bomb, symlinks, secrets, license metadata |
| Shared architecture | Dependency boundary check when implemented | Forbidden inward/outward dependencies |

Use small focused regression tests for discovered bugs before attempting broad platform compatibility.

## 5. Trust-boundary and security tests

**Import is not execution.** A read-only import of a local project must not automatically clone Git repos, run scripts, invoke `kas build`, evaluate BitBake recipes, or contact external services. Tests should instrument the executable/network adapters to assert **zero calls** in this mode.

**Build is code execution.** The local runner may execute explicitly approved project/toolchain code, but must never silently claim isolation from the host. Hosted builds will require separate tenant workers, sandbox policy, network controls, resource budgets and an independent threat-model review.

Required negative-case coverage as features arrive:

- File traversal, absolute path escapes and symlink-following outside approved workspace.
- Unsafe archive extraction (duplicate entries, symlinks, oversized/decompression ratios).
- `Origin`/host/session violations for local HTTP endpoints; restrictive CORS.
- Shell injection prevention through argv-based subprocess execution.
- Partial config writes, stale preview replay and process cancellation.
- Secret, Git credential, private path and environment-value redaction in API errors/logs.
- External command output size, malformed JSON, encoding and timeout limits.

Do not expose an insecure local-process API to arbitrary websites or non-loopback interfaces.

## 6. Yocto integration fixtures and reference matrix

**Before claiming real metadata/build support**, pin and document these in `docs/DECISIONS.md` and/or a fixture manifest:

- Host OS/distribution, relevant runtime and storage requirements.
- Exact Poky/Yocto release/tag or commit, BitBake version, `kas` version.
- QEMU machine, image target and selected layers, with Git commit hashes.
- Approved tool installation/build preparation and optional network policy.
- Expected outputs, log collection and artifact retention.

Suggested fixture groups (initially placeholders, **not yet checked in**):

```text
fixtures/
  kas/
    valid-minimal.yml
    invalid-syntax.yml
    unsupported-feature.yml
  config/
    comments-preserved.conf
    stale-file-case.conf
  contracts/
    project-open-success.json
    project-open-error.json
```

A fixture is valid only when it is licensed/owned appropriately, contains no secrets and has assertions. Use pinned small inputs for fast CI and a separate provisioned Linux runner for expensive image builds.

## 7. Tiered CI pipeline

### Tier A — quick PR checks (target)

- Formatting, workspace check, Clippy and unit tests.
- React production build and configured frontend lint/typechecks.
- DTO/schema compatibility and dependency-rule checks **once implemented**.
- Fast fixture tests, negative permission tests, changed-path ownership review.

PR CI should stop safely on failures. Do not suppress findings or change metrics just to get a green check.

### Tier B — integration checks (target)

- Rust API ↔ engine ↔ fake Yocto adapter.
- Real supported BitBake metadata inspection on a prepared runner.
- Config preview/apply round trip, subprocess cancellation, log streaming.
- Cross-platform frontend checks as relevant; Linux remains the primary supported host for local Yocto.

### Tier C — expensive reference checks (target)

- Pinned QEMU image build on a dedicated Linux worker with resource budget and sstate/download cache management.
- Optional QEMU boot smoke test, with explicit criteria and evidence.
- Nightly/manual/release schedule; not implied by every lightweight PR.

Avoid having many agents trigger expensive parallel builds unintentionally. Use concurrency/resource quotas and cache controls. Main-branch verification must not be permanently starved by cancelling every run during frequent merges.

## 8. Evidence format for PRs and handover

Use the format from `docs/TASK_PROTOCOL.md`. For each check record:

```text
Check: cargo test --workspace
Environment: Fedora <version>, rustc <version>, local worktree
Status: PASS | FAIL | NOT RUN
Result: <test count or precise error; no invented values>
Artifacts: <link to CI logs or sanitized local log excerpt>
Yocto evidence level: NOT RUN | METADATA | IMAGE BUILD | QEMU BOOT | HARDWARE
```

Logs may be shortened but must not misrepresent failures. Never check credentials or enormous build output into Git. Use CI artifacts/object storage with bounded retention if needed.

## 9. Architecture fitness and future scorecards

Proposed measurable checks:

1. `core` must not gain Axum, Tokio process execution, React, Python bridge or cloud SDK dependencies.
2. API controllers may not directly parse/write BitBake config or start unsupervised processes.
3. Each command has an input/output contract, side-effect classification and at least one headless success and failure test.
4. GUI uses engine/API contracts rather than private duplicate project semantics.
5. Project import and export preserve untouched user files where supported.
6. Every claimed supported Yocto version has dated actual evidence.

A future `docs/SCORECARD.md` can track source fixture coverage, real metadata/build pass rates, supported version matrix, bug regressions and import/build latency. **Do not add unchecked parity percentages.**

## 10. Failure and waiver policy

- Reproducible failure must be resolved or PR remains blocked.
- Infrastructure outages may be recorded as `NOT RUN`/blocked; absence of a test is not a pass.
- A narrow temporary test waiver requires named maintainer approval, reason, risk, expiration and follow-up issue; security-critical gates cannot be silently waived.
- A flaky test gets an owner and root-cause issue; retries must not mask sustained failure.
- CI result alone never overrides review of an unauthorized file write, leaked secret, unsafe executable or missing product decision.

## 11. MVP end-to-end acceptance scenario

1. Start from clean documented supported local Linux/Yocto toolchain.
2. Import the pinned `kas` fixture with no hidden execution.
3. Inspect declared repositories/layers, then obtain selected *resolved* metadata through installed BitBake.
4. Preview and approve one supported config edit; inspect exact diff and verify standard file compatibility.
5. Start/cancel/inspect a test build, then complete the named reference image build.
6. Export the standard files, re-open externally using supported Yocto/`kas` tools.
7. Record exact versions, outputs, failures and limitations; do not claim QEMU or hardware proof unless run.

**MVP passes only when** the scenario has real documented evidence, not just API/UI scaffolding.
