# KernelCanvas — Architecture Decision Register

> **Status:** Foundation decision register v0.1. Entries marked **PROPOSED/OPEN** are not approved implementation mandates.
> **Decision owner:** KernelCanvas repository maintainer.
> **Related:** `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `AGENTS.md`.

## 1. Purpose and rules

Use concise Architecture Decision Records (ADRs) to prevent independent agents from making incompatible choices. Craft-style multi-agent development works only if interfaces and major architectural boundaries are agreed before parallel work.

- Only the repository maintainer (or an explicitly delegated decision-maker) changes a record to `ACCEPTED`.
- `PROPOSED` and `OPEN` mean implementation must not assume a final choice when behavior depends on it.
- Never silently change an accepted decision during implementation. Submit a new superseding ADR with migration and backwards-compatibility implications.
- Add rationale, alternatives, security/licensing implications, and measurable consequences.
- Store secrets and credentials outside this document.
- A maintainer may explicitly approve a narrow task without accepting a long-term architecture choice; record the temporary constraint in that task.

## 2. Decision states

`OPEN` → alternatives still being investigated; `PROPOSED` → a recommended choice awaiting review; `ACCEPTED` → approved; `SUPERSEDED` → replaced by named ADR; `REJECTED` → evaluated and declined.

## 3. Current decision register

| ADR | Topic | Status | Next action / blocker |
| --- | --- | --- | --- |
| ADR-001 | Primary GUI shell for M0 | **PROPOSED** | Confirm React/Vite + locally hosted Rust API, not Tauri packaging yet |
| ADR-002 | First Yocto release, `kas` version, QEMU machine and image target | **OPEN** | Pin exact supported reference toolchain before M2/M4 |
| ADR-003 | Local API startup, session credential, origin/host checks | **OPEN** | Security design before project file/process routes |
| ADR-004 | API DTO/schema source of truth | **OPEN** | Choose schema generation/versioning and compatibility policy |
| ADR-005 | Yocto Python bridge protocol/version negotiation | **OPEN** | Define external process JSON contract before M2 |
| ADR-006 | Safe config editing source and algorithm | **OPEN** | Choose supported fields + file-preserving edit strategy before M3 |
| ADR-007 | Portable `.kcanvas` schema and extension | **PROPOSED** | Post-MVP design; no implementation mandate |
| ADR-008 | Repository license and open-core/commercial model | **OPEN** | Explicit owner legal/business decision before public licensing claims |
| ADR-009 | Local build isolation and host/tool approval model | **OPEN** | Document host risk and execution policy before M4 |
| ADR-010 | Architecture dependency checker/`xtask` location | **PROPOSED** | Implement only after meaningful crate boundaries exist |

The product docs already prescribe **Yocto-native behavior, local-first MVP, no mandatory cloud account and explicit side effects**. These are current product principles, not permission to decide unresolved security/toolchain or licensing details automatically.

## 4. First decisions to resolve

### ADR-001 — M0 presentation shell

**Status:** PROPOSED  
**Context:** Need a useful developer experience and clean headless command boundary without a packaging project distracting from the MVP.  
**Proposed:** React + TypeScript + Vite GUI calling a Rust Axum API restricted to localhost. Tauri remains a potential later shell over the same application engine.  
**Alternatives:** Tauri from day one; native Rust widget UI; cloud-only website.  
**Reasons:** Existing scaffold direction, API/headless testability, fast UI iteration.  
**Risk/condition:** A localhost service is not automatically secure. Do not expose project-write/build routes until ADR-003 is accepted and enforced.  
**Validation:** M0 frontend build and local API smoke test.

### ADR-002 — Pinned Yocto reference platform

**Status:** OPEN  
**Context:** Claims about Yocto metadata and builds must specify a concrete supported version/toolchain.  
**Candidates:** Select one maintained Yocto/Poky release, a tested `kas` release, a QEMU machine such as `qemuarm64` only if supported by chosen reference, and an image target such as `core-image-minimal`.  
**Required decision:** Exact tags/commits and approved download/bootstrap procedure, host requirements, expected artifacts, and validation commands.  
**Validation:** Real pinned BitBake metadata and successful reference image build on a prepared Linux worker.

### ADR-003 — Localhost API security model

**Status:** OPEN  
**Context:** A browser-accessible local API that reads/writes projects or launches builds is a high-risk capability.  
**Required decision:** Session credential mechanism, browser origin and host validation, CORS, loopback binding, token handling, process lifetime, allowable workspace roots, CSRF protections and shutdown behavior.  
**Validation:** Negative API tests against unauthorized/cross-origin requests, path traversal and unapproved execution.

### ADR-004 — API and command contract format

**Status:** OPEN  
**Context:** Frontend, Rust API, engine and future CLI/MCP must not invent divergent DTOs.  
**Candidates:** OpenAPI/schema-first generation; Rust-derived JSON Schema with versioned generated clients; a deliberately small manually maintained shared contract with conformance fixtures for M0.  
**Required decision:** Single source, versioning policy, backwards compatibility and generated-file ownership.  
**Validation:** Contract tests and CI drift checks when implemented.

### ADR-005 — Versioned Python/BitBake bridge

**Status:** OPEN  
**Context:** BitBake/Tinfoil semantics are version-sensitive; Rust must not emulate them.  
**Required decision:** Executable discovery, supported Python environment, request/response JSON framing, capabilities negotiation, timeout/cancellation behavior, redaction and failure handling.  
**Validation:** Fake-bridge tests plus a real pinned supported BitBake environment.

### ADR-006 — Safe edit strategy

**Status:** OPEN  
**Context:** `.conf`/BitBake override syntax must not be rewritten through a lossy parser.  
**Alternatives:** Narrow targeted edit with byte-preserving spans; separate managed include/config file with explicit precedence; refuse editing unsupported constructs.  
**Required decision:** Initial supported field(s), provenance/conflict handling, atomic write and rollback strategy.  
**Validation:** Exact diffs, comment/unknown-input preservation, stale preview and failure tests.

### ADR-007 — Optional portable project snapshot

**Status:** PROPOSED (post-MVP)  
**Proposed:** `.kcanvas` is a portable, versioned archive containing KernelCanvas metadata plus ordinary Yocto/`kas` project definitions or pinned references. The Git-friendly project directory remains canonical for editing.  
**Risks:** Archive traversal, secret inclusion, duplicate paths, external license/redistribution, stale refs and binary Git churn.  
**Required decision:** Final extension, schema versioning, contents/size rules and migration policy.  
**Validation:** Import/export round trip, no proprietary lock-in, hostile archive tests.

### ADR-008 — License and distribution model

**Status:** OPEN; **owner/legal decision**  
**Context:** A commercial SaaS and local GUI can coexist, but repo/license choice and obligations of embedded tools/layers must be deliberately decided.  
**Required decision:** Public repository license, third-party component inventory, trademark usage policy, free/local versus paid/hosted feature boundary.  
**Validation:** Documented license review before distributing code/binaries; do not assume a GitHub repository is automatically open source without a license.

### ADR-009 — Local build trust boundary

**Status:** OPEN  
**Context:** Yocto recipe execution may run arbitrary project-supplied code. Local execution is not a sandbox.  
**Required decision:** Approval UX, environment sanitation, allowed paths, resource controls, subprocess group cancellation, log redaction and whether any optional isolation is supported.  
**Validation:** Hostile-input/command argv tests, process lifecycle tests and user-confirmation checks.

### ADR-010 — Architecture fitness automation

**Status:** PROPOSED  
**Proposed:** Implement `cargo xtask layers`/equivalent with `cargo metadata` once the workspace has clear application, adapter and domain crate boundaries.  
**Risk:** Prematurely introducing empty crates and brittle checks.  
**Validation:** Positive allowed-dependency fixture, negative forbidden-dependency fixture, CI step only when command exists.

## 5. Copyable ADR template

```md
## ADR-0XX — <decision title>
Status: OPEN | PROPOSED | ACCEPTED | SUPERSEDED | REJECTED
Date: YYYY-MM-DD
Owner/approver: ...
Affected milestones/tasks: ...

### Context
<Problem and constraints>

### Decision
<One unambiguous choice; use TBD while OPEN>

### Alternatives considered
- ...

### Consequences and risks
- ...

### Tests / acceptance evidence
- ...

### Migration or reversal plan
- ...

### Approval
<Explicit maintainer approval link/record, if ACCEPTED>
```

## 6. Decision review cadence

- **Before M0 implementation:** Confirm ADR-001 and define a safe M0-only API surface.
- **Before M1/M2:** Approve contract and bridge decisions (ADR-004, ADR-005); pin reference toolchain before real metadata testing (ADR-002).
- **Before filesystem/process side effects:** Approve ADR-003, ADR-006 and ADR-009 as applicable.
- **Before releasing or selling:** Resolve ADR-008 and product-related commercial/trademark questions.
- **Before `.kcanvas` or Template Hub:** Finalize ADR-007 and import/provenance policies.

**No agent may declare its personal preference `ACCEPTED` without explicit owner approval.**
