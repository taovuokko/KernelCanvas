# KernelCanvas — Software Architecture

> **Status:** Proposed foundation architecture v0.1  
> **Product:** KernelCanvas Studio  
> **Companion document:** [`PRODUCT.md`](PRODUCT.md)  
> **Scope:** Local-first visual workspace for existing Yocto Project / BitBake projects.  
> **Implementation state:** This document describes the **target design**, not a claim that every crate, API, test, or command already exists. See §15 for the rollout sequence.

## 1. Architecture mission

KernelCanvas is a visual IDE for engineers who build embedded Linux systems using existing Yocto Project tooling. It must make complex configurations understandable **without inventing an incompatible Yocto dialect**.

The architecture must support:

1. An accurate, explainable view of existing Yocto and `kas` projects.
2. Safe, previewable edits to a deliberately limited set of settings.
3. Repeatable, observable local BitBake builds.
4. A headless command interface usable by tests, future CLI/MCP tools, and the GUI.
5. Parallel AI-agent development with module ownership, explicit contracts, and automated quality gates.
6. Later optional collaboration, templates, project snapshots, and remote builders **without redesigning the local core**.

**Out of scope for the foundation:** a replacement for BitBake, arbitrary `.bb` parsing in Rust, a complete Device Tree editor, a hosted build farm, marketplace billing, and universal BSP compatibility.

### Non-negotiable design rules

- **Yocto is authoritative.** BitBake and the selected project's metadata determine effective configuration and build behavior. A Rust or TypeScript approximation must never be presented as the final answer.
- **Headless first.** A user-visible operation is implemented in the application engine once. UI, tests, API, and future CLI/MCP are clients of it.
- **Thin GUI.** React renders state, gathers input, and invokes typed commands; it does not implement project parsing, filesystem changes, or build execution.
- **Explicit side effects.** Importing a manifest is distinct from fetching repositories; inspecting settings is distinct from executing BitBake; previewing edits is distinct from writing them.
- **Portability before lock-in.** The project remains usable with standard Yocto and `kas` tooling. KernelCanvas metadata is additive and optional.
- **Crash-resistance and recoverability.** Bad input produces structured diagnostics; no partial edits or silent data loss.
- **Evidence over completion claims.** A button or stub endpoint does not count as a functional Yocto integration.

## 2. Inspirations and KernelCanvas-specific adaptations

The architectural ideas below are adapted from the public PhotoCraft and WordCraft repositories; **we are not copying their source code, naming conventions, or proprietary/internal development material**.

| Public Craft idea | KernelCanvas adaptation |
| --- | --- |
| Layered Rust workspace with dependency checks | Small initial workspace, later split into domain, adapters, orchestration, and transport; enforceable dependency rules |
| All user actions go through a command engine | Stable command IDs for import, inspect, preview, apply, build, cancel, and export |
| UI is a replaceable shell | React/Vite first; future desktop shell or CLI uses the same API and engine |
| Headless automation and deterministic tests | Commands callable without a browser, typed input/output, structured events, reproducible fixtures |
| Real-file format tests and round-trips | Real `kas`/Yocto fixtures, lossless preservation of unaffected configuration, compatibility tests |
| Explicit task ownership for parallel agents | One worktree/branch per agent, ownership boundaries, shared API contracts, staged integration |
| `xtask`-based architecture and CI checks | Introduce a KernelCanvas layer checker and focused test tasks once the workspace expands |
| Measured parity/scorecards rather than optimistic checklists | Track supported Yocto releases, input constructs, test fixtures, reference builds, and unsupported operations |

Sources for architectural inspiration:
- PhotoCraft agent guide: https://github.com/storytold/photocraft/blob/main/AGENTS.md
- PhotoCraft architecture: https://github.com/storytold/photocraft/blob/main/docs/architecture.md
- WordCraft agent guide: https://github.com/storytold/wordcraft/blob/main/AGENTS.md

**Important difference:** PhotoCraft can implement its own document engine. KernelCanvas must use upstream BitBake/Yocto as an external authority. This creates a trust and process-execution boundary that an image editor does not have.

## 3. System overview

```text
┌─────────────────────────────────────────────────────────────────┐
│ React + TypeScript GUI                                           │
│ Projects · Layers · Config Inspector · Diff Preview · Builds     │
└───────────────────────────┬─────────────────────────────────────┘
                            │ typed HTTP API + event stream
┌───────────────────────────▼─────────────────────────────────────┐
│ Rust API adapter (Axum; localhost only for initial release)      │
│ Validate requests · map errors · stream progress · authenticate  │
└───────────────────────────┬─────────────────────────────────────┘
                            │ invokes registered commands
┌───────────────────────────▼─────────────────────────────────────┐
│ Rust Application Engine                                          │
│ Project sessions · command dispatcher · jobs · audit events      │
│ preview/apply transactions · read models · lifecycle             │
└──────────────┬────────────────────────────────────┬─────────────┘
               │                                    │
┌──────────────▼────────────────────┐  ┌────────────▼────────────┐
│ Rust project model / persistence  │  │ Tool adapters           │
│ typed data · validation · diffs   │  │ Yocto/BitBake (Python)  │
│ normal Yocto/kas files            │  │ kas CLI · local builder │
└───────────────────────────────────┘  └────────────┬────────────┘
                                                   │ external tools
                                     ┌─────────────▼─────────────┐
                                     │ User's Linux environment │
                                     │ Yocto · BitBake · kas     │
                                     │ Git repos · build output │
                                     └───────────────────────────┘
```

The GUI must never call BitBake directly. The API must never encode business rules that differ from the engine. The engine must never silently assume that a `kas` YAML file describes the **effective** values after BitBake overrides have been applied.

### Local-first deployment

MVP: a locally running Rust API bound to `127.0.0.1`, a browser-based React app, and the user's **already configured Linux Yocto environment**. A localhost API is not automatically secure: require an unguessable session credential, validate `Origin`/host, and do not enable wildcard CORS. Exact launch/auth flow is an implementation decision recorded before exposing project or process APIs.

A future Tauri desktop wrapper may embed the web UI, but it must call the same engine and must not require a second application implementation. A future hosted service gets **separate** tenancy, identity, policy, and isolated worker components; do not expose the local development API directly to the internet.

## 4. Repository and workspace layout

Keep the initial project compatible with the foundation already discussed (`apps/web`, `crates/core`, `crates/api`). The additional crates below are **planned**, not prerequisites to the first build.

```text
KernelCanvas/
├── Cargo.toml                       # Rust workspace, shared lint policy
├── apps/
│   └── web/                         # React + TypeScript + Vite (first GUI)
├── crates/
│   ├── core/                        # NOW: stable types, validation, error model
│   ├── api/                         # NOW: Axum adapter / local API binary
│   ├── engine/                      # LATER: command registry, sessions, jobs
│   ├── project-io/                  # LATER: import/export, reviewable file edits
│   ├── yocto-adapter/               # LATER: Rust bridge for tool subprocesses
│   ├── build-runner/                # LATER: process lifecycle, logs, cancellation
│   ├── format/                      # LATER: optional .kcanvas snapshots
│   └── testkit/                     # LATER: fixtures, fake ports, test helpers
├── adapters/
│   └── yocto-python/                # LATER: version-aware BitBake/Tinfoil bridge
├── fixtures/                        # Minimal, licensed, pinned test projects
├── docs/
│   ├── PRODUCT.md
│   ├── ARCHITECTURE.md
│   ├── DECISIONS.md                  # Proposed: accepted design decisions
│   ├── ROADMAP.md                    # Proposed: verified milestones
│   └── TESTING.md                    # Proposed: quality gates and evidence
├── agents/                           # Later: role-specific instructions
├── scripts/                          # Dev scripts and architecture checks
├── xtask/                            # Later: cargo xtask checks
└── .github/workflows/                # CI when implemented
```

**Naming:** Keep directory names short and descriptive. When packages are stabilized, prefer `kernelcanvas-*` Cargo package names while avoiding a disruptive rename before the initial foundation works. A new crate must have a clear owner, responsibility, public API, and dependency justification.

**Avoid premature fragmentation:** Start with `core` and `api`. Introduce a dedicated crate when a meaningful, testable boundary emerges or a parallel agent needs ownership independent of shared files. Do not create ten empty crates merely to resemble PhotoCraft.

## 5. Dependency layers and fitness rules

Proposed target layers (arrows indicate allowed dependency direction):

```text
L5  GUI: apps/web                 (TypeScript, uses HTTP contracts only)
     ↓ HTTP/event contracts, not direct Cargo imports
L4  Edge: crates/api, future CLI  (transport, auth, DTO mapping)
     ↓
L3  Orchestration: engine         (commands, sessions, jobs, policy)
     ↓
L2  Adapters: project-io,        (filesystem, kas/BitBake, processes,
     yocto-adapter, build-runner   serialization; controlled side effects)
     ↓
L1  Domain: crates/core          (project model, validation, IDs, errors)
```

`format` is an I/O adapter; `testkit` is test-only. Python's `adapters/yocto-python` and the actual BitBake process are **out-of-process dependencies**, not Rust foundation modules. All runtime layers may use external crates as appropriate, but respect the domain invariants below.

**Rules to automate as the repository grows:**

1. `core` may not depend on `api`, frontend code, Tokio/Axum, Git subprocesses, filesystem execution, BitBake Python APIs, or cloud SDKs.
2. `engine` may depend on domain abstractions/ports, but not on Axum request types or React state.
3. Adapters implement ports defined in the domain/application boundary; their types must not leak into the stable command contracts.
4. `api` maps DTOs to engine commands and presents engine output; it does not directly edit `local.conf` or invoke shell commands.
5. `apps/web` cannot become the only place where configuration validation or file mutation logic lives.
6. Every command has at least one headless test; new external adapters have fakes for unit tests and integration tests against real tools.
7. Cyclic workspace dependencies and undocumented cross-layer dependencies are disallowed.

Implement a machine-enforced checker later via `cargo metadata`, e.g. `cargo xtask layers`, and run it in CI. **The command is a target, not currently available merely because it is documented here.**

## 6. Domain model: data before UI

The domain model describes what the project **declares**, what tooling **resolved**, and what the GUI **displays**. These are different concepts.

Core entities (illustrative, not yet final Rust structs):

| Entity | Meaning |
| --- | --- |
| `ProjectId` / `ProjectSession` | An opened local project and current inspection state |
| `SourceRepository` | URL/path, requested ref, checked-out commit, provenance |
| `LayerRef` | Layer path, collection name, compatibility and dependency declarations when available |
| `BuildConfiguration` | Machine, distro, target, selected configuration files, toolchain version |
| `SettingValue` | Name, resolved value **if available**, origin/provenance, confidence/state |
| `ConfigChange` | A typed, supported edit requested by the user |
| `EditPreview` | Exact proposed file changes and validation diagnostics |
| `BuildSpec` | Target, environment policy, workspace identity, output location |
| `BuildJob` | ID, lifecycle state, timestamps, log/artifact references |
| `Diagnostic` | Stable code, severity, message, machine-readable details, safe remediation |

Never store a resolved value as though it were literally declared in `local.conf`. Distinguish:

- `Declared(value, source)` — a direct value from a known input.
- `Resolved(value, provenance)` — returned by the selected BitBake/Yocto environment.
- `Unknown(reason)` — the value is not yet resolvable, or the operation is unsupported.

The initial API may expose only a subset of these types, but must not conflate these states.

## 7. Everything is a command

Follow PhotoCraft's **one user-visible action → one stable command** principle.

Proposed command IDs (design targets):

| Command ID | Side effect | Earliest milestone |
| --- | --- | --- |
| `project.open` | Reads local project files | M1 |
| `project.inspect` | Reads declared/resolved metadata | M1–M2 |
| `config.preview_change` | Read-only; produces proposed diff | M3 |
| `config.apply_change` | Writes after explicit review/confirmation | M3 |
| `build.start` | Executes configured BitBake/kas build | M4 |
| `build.cancel` | Requests controlled cancellation | M4 |
| `build.status` | Reads job state | M4 |
| `build.logs` | Reads authorized build logs | M4 |
| `project.export` | Writes portable standard project files | M5 |
| `project.snapshot_export` | Writes proposed `.kcanvas` archive | Post-MVP |

Every registered command has:

- A stable ID, description, versioned input/output schema, and explicit capabilities/side-effect classification.
- Typed parameters; validation occurs before dispatch.
- A permission/approval check for filesystem, network, build, and destructive actions.
- A deterministic domain response or asynchronous `JobId` and structured events.
- Structured errors and telemetry redaction rules.
- Tests for invalid input, interrupted work, and allowed state transitions.

Sample (illustrative wire contract, **not** a working endpoint):

```json
{
  "command": "config.preview_change",
  "project_id": "project_123",
  "params": {
    "setting": "MACHINE",
    "value": "qemuarm64"
  }
}
```

Response data should include validation diagnostics, exact proposed changes, and a token/hash binding any later `apply_change` call to the reviewed file state. Do **not** expose arbitrary command execution as a generic `run_shell` command.

### Command execution model

```text
UI / HTTP / future CLI / future MCP
               │
               ▼
       typed command registry
               │
       validate + authorize
               │
        session / engine
               │
        injected adapters
               │
       result + event stream
```

Builds are long-running **jobs**, not blocking HTTP requests. The same command can be exercised by an in-process Rust test, a headless CLI, or a browser.

## 8. Yocto/BitBake integration boundary

**Never reimplement full BitBake variable expansion, override semantics, recipe evaluation, or layer resolution in Rust or JavaScript.** Those are complex and version-sensitive.

Use two separate capabilities:

### A. Manifest/declared-project inspection (no execution)

- Parse a **documented supported subset** of `kas` YAML to identify repositories, refs, layer declarations, and requested build target.
- Parse files defensively with size/depth limits. Mark unknown keys/constructs as unsupported where their meaning matters.
- Display declared data as declared, not as the effective BitBake environment.
- Inspecting a manifest does not automatically clone repos, source setup scripts, or run builds.

### B. Resolved Yocto metadata (explicit environment access)

- Use the selected Yocto/BitBake installation in a **separate, version-aware Python adapter**, favoring supported upstream tools/interfaces such as Tinfoil or documented BitBake commands.
- The Rust adapter invokes an explicit command with an argument vector (`exec`, **not** shell-string interpolation), sets controlled environment/cwd, captures structured output, and reports process failures.
- The Python bridge returns a versioned JSON envelope, e.g. `{ "schema_version": 1, "data": ..., "diagnostics": ... }`.
- Treat Python/BitBake implementation details as replaceable adapter internals. Capability-detect and test against selected supported releases rather than promising universal compatibility.
- Use metadata provenance where supported; do not invent a variable's origin when upstream data is insufficient.

**Reference material:** https://wiki.yoctoproject.org/wiki/TipsAndTricks/Tinfoil and https://kas.readthedocs.io/en/latest/userguide/project-configuration.html

### Boundary invariants

1. All potentially executing operations require explicit user action and a trusted workspace selection.
2. Workspace paths are canonicalized and checked for containment; symlinks, `..`, and time-of-check/time-of-use changes receive careful handling.
3. Allowed tool binaries and working directories are explicit. No user-supplied raw shell arguments in the browser API.
4. Credentials inherited by child processes are restricted; logs/diagnostics redact tokens and private URLs.
5. Unsupported Yocto constructs remain visible as unsupported rather than being silently discarded.
6. A failed or interrupted command must not leave the project marked as successfully validated.

## 9. Configuration edits: inspect → preview → apply → verify

The editing pipeline is deliberately conservative:

```text
Read original files
       ↓
Select a supported, typed setting
       ↓
Generate candidate edit in staging
       ↓
Show exact unified diff + impacted files
       ↓
Check file fingerprints / concurrent edits
       ↓
User explicitly confirms
       ↓
Atomic write + backup/recovery strategy
       ↓
Re-inspect with Yocto-aware tooling when appropriate
```

**MVP editing scope:** a small allowlist, initially configuration files such as known assignments in `local.conf` or a dedicated KernelCanvas-managed include file. The exact supported syntax and conflict behavior must be specified and tested before implementation.

Rules:

- Preserve unrelated comments, ordering, and unrecognized statements. Never rewrite a whole BitBake file with a lossy serializer.
- Do not claim a text edit succeeded semantically until the required metadata validation passes.
- Prefer an explicitly managed, source-controlled include where appropriate; verify its inclusion semantics before changing project behavior.
- `apply_change` must fail on stale fingerprints rather than overwriting another user's/agent's work.
- Write through same-filesystem temporary files and atomic rename where supported; preserve permissions; maintain a recovery path.
- Display a real diff before user confirmation. In future automation, approval must be an explicit capability rather than silently bypassing the GUI.
- If an edit cannot be represented safely, return `UnsupportedEdit` and offer read-only inspection or manual editing.

**Critical invariant:** import → open → export with no intentional edits must not drop unknown Yocto metadata, comments, or files. A lossy import/export is a bug.

## 10. Local build execution and jobs

The build subsystem owns **job state**, not Yocto's build semantics.

Lifecycle:

```text
Queued → Preparing → Running → {Succeeded | Failed | Cancelled}
                     ↘ Failed
```

All terminal states are final. No job can be `Succeeded` without an observed zero exit status and corresponding validation of expected artifacts where that command requires them.

Build worker responsibilities:

- Launch known tools, such as `kas build <manifest>` or the user's configured BitBake workflow, from an approved workspace.
- Record command arguments (redacted), tool versions, exact source revisions when available, start/end times, status, and exit code.
- Stream logs incrementally with bounded buffers and optional spool-to-disk, not unbounded in-memory accumulation.
- Cancel the build by signaling/terminating the **owned process group** and report whether it actually stopped.
- Expose log and artifact paths **scoped to that job**; never let API clients fetch arbitrary files.
- Allow at most one conflicting build per workspace unless safe isolation is established; multiple projects may use separate work dirs/caches if provisioned.
- Enforce explicit cache, output, and temporary-directory ownership; build outputs and credentials never enter Git by default.

A local build is **not a security sandbox**. Yocto recipes can execute code on the host. Imported untrusted projects must be treated as executable code; recommend disposable VMs/containers with appropriate isolation. For future multi-tenant hosted builds, use dedicated per-job isolation with separate trust controls, not merely local subprocesses.

## 11. UI architecture and typed contracts

React is a presentation shell, not an alternative project engine.

Initial feature boundaries:

```text
apps/web/src/
├── app/                 # routing, application composition, session connection
├── features/
│   ├── projects/        # import and overview
│   ├── layers/          # layer list/graph (graph later)
│   ├── config/          # setting inspector, staged diff, confirmation
│   └── builds/          # jobs, progress, log viewer
├── components/          # reusable accessible controls
├── api/                 # generated or centrally maintained typed client
└── styles/              # theme tokens
```

- Prefer versioned OpenAPI/JSON Schema contracts generated from the Rust API or another **single chosen source of truth**. Do not manually maintain diverging Rust and TypeScript models.
- UI navigation state lives in React; authoritative project and build state lives in the engine.
- Frontend displays loading, error, unsupported, dirty, and stale-data states explicitly.
- Use polling initially if reliable; add Server-Sent Events for progress before WebSocket complexity is justified.
- The UI must be testable with fake command responses and must be accessible with keyboard navigation.
- Treat filenames, logs, YAML values, and recipe descriptions as untrusted text. Never inject them as HTML.
- Visual edits should display their effects as real file diffs, never as optimistic uncommitted state alone.

A desktop wrapper must only provide local integration/packaging. Do not allow the wrapper to grow separate project logic.

## 12. Native snapshots and templates (post-MVP)

The default editable project is a **normal Git-friendly directory** using standard Yocto/`kas` files plus optional KernelCanvas metadata. The proposed `.kcanvas` snapshot is a convenience archive, **not** the project's canonical source of truth.

Provisional snapshot contents:

```text
example.kcanvas  (versioned archive)
├── manifest.json            # schema, export tool, content hashes
├── project.kas.yml         # or references to existing kas input files
├── config/                 # intentionally included project config
├── metadata/workspace.json # GUI-specific optional state
├── lock.json               # pinned repo revisions and tool versions
└── LICENSES/               # only if redistributable assets are bundled
```

Design rules:

1. Version every manifest. Reject unsupported major versions safely; define migration rules before publishing schema v1.
2. Never include secrets, workspace absolute paths, full source checkouts, build cache, or generated images by default.
3. On import, prevent archive path traversal, symlink escape, duplicate entries, zip bombs, and oversize extraction.
4. Check hashes, pin external revisions, and distinguish requested refs from verified checked-out SHAs.
5. An archive is **not** a trusted build recipe. Inspect and preview external fetch/build actions before execution.
6. A plain Yocto/`kas` export must remain possible without `.kcanvas`.
7. Test snapshot round-trips and preservation of unknown optional fields according to versioning policy.

Templates should initially be ordinary repos/files with metadata about supported Yocto releases, machines, license restrictions, pinning, and validation evidence. A future Template Hub adds publishing/review/signatures and team permissions without forcing a proprietary build configuration format.

## 13. Security, reliability, and diagnostics

### Error model

Every boundary returns typed/structured errors. Suggested codes:

`InvalidProject`, `UnsupportedConstruct`, `UnsupportedEdit`, `StalePreview`, `ToolNotFound`, `ToolVersionUnsupported`, `BuildFailed`, `BuildCancelled`, `UnauthorizedPath`, `PermissionDenied`, `InternalError`.

Errors include a safe user-facing explanation, optional remediation, and an internal correlation ID. Avoid leaking secrets, full private Git URLs, and environment dumps.

### Rust conventions (to be enforced in AGENTS.md)

- Avoid `unwrap`, `expect`, `panic!`, `todo!`, and `unimplemented!` in production request, parsing, or build paths. Return `Result` and actionable diagnostics.
- Forbid `unsafe` in foundational crates by default; any exception requires a documented architecture decision and focused tests.
- Bound input length, recursion, allocation, log buffers, archive extraction, and subprocess lifetime where feasible.
- Use explicit `Path`/`PathBuf`, checked arithmetic, and safe state transitions.
- Do not assume successful HTTP response implies successful build, write, or post-validation.
- Treat APIs/metadata/filenames/logs as untrusted input, including output originating from external tools.

### Trust boundaries

| Boundary | Risk | Required control |
| --- | --- | --- |
| Browser → localhost API | Cross-origin or local malware abuse | Session authorization, origin/host checks, no permissive CORS |
| API → filesystem | Arbitrary file read/write | Workspace-scoped path policy, reviewed edits, least privilege |
| API → tool process | Command injection and code execution | Argument vectors, binary allowlist, explicit confirmation, isolation guidance |
| Tool output → UI | Secrets and injected content | Redaction, output size limits, text escaping |
| Archive/template → project | Malicious paths or downloaded code | Strict unpacking, provenance, user approval |
| Future cloud build tenants | Cross-tenant compromise | Separate workers, identity, storage, network, and quotas |

## 14. Architecture verification and CI strategy

We follow PhotoCraft's principle: **architectural rules and quality claims should become executable checks**.

### Fast checks (every PR; once implemented)

- `cargo fmt --all -- --check`
- `cargo check --workspace`
- `cargo clippy --workspace --all-targets -- -D warnings`
- `cargo test --workspace`
- `npm run build --prefix apps/web`
- Frontend lint/type checks once those scripts exist.
- Dependency-layer gate (`cargo xtask layers`) **after** its implementation.
- Unit tests for every new command and an error-path test for hostile or malformed inputs.

### Contract and integration tests

- Golden JSON/HTTP command contracts and generated TypeScript API compatibility.
- Known `kas` YAML fixtures including unknown fields and invalid input.
- Safe edits tested against preserved comments and unrelated settings.
- Preview/apply stale-file race tests; atomic write failure/recovery tests.
- Fake Yocto adapter tests in normal CI; real Tinfoil/BitBake integration only in provisioned runner jobs.
- Workspace path traversal, dangerous command input, log redaction, and archive import adversarial tests.

### Expensive reference tests

- A **pinned** supported Yocto release, QEMU machine, and reference image are defined in `docs/DECISIONS.md` and test fixtures.
- Full image build, relevant artifact checks, and optional QEMU boot smoke test run on a suitable dedicated Linux runner, schedule, or release gate.
- Distinguish metadata parse pass, build pass, QEMU boot pass, and hardware validation; never combine these into one vague "verified" badge.

### Scorecard (future `docs/SCORECARD.md`)

Measure: supported Yocto release matrix, documented `kas` subset, metadata inspector correctness on fixtures, edit round-trip outcomes, local build success rate on pinned references, cancellations, crash/regression count, and performance (import/inspect/log latency). Counts must come from automated reports and dated evidence, not estimates or UI wiring.

## 15. Implementation milestones and agent work boundaries

The repository should grow in small verified slices, not all at once.

| Phase | Deliverable | Primary ownership | Gate |
| --- | --- | --- | --- |
| M0 — Foundation | Rust workspace, React shell, docs, minimal local API | Core/API/UI | Both builds + smoke test |
| M1 — Import | Open a supported local `kas` manifest; declared repo/layer overview | Project I/O + UI | Fixtures and no-execution import test |
| M2 — Inspect | Query selected effective metadata via installed BitBake | Yocto adapter + engine | Real supported toolchain test |
| M3 — Edit | Preview and apply one or two safe config settings | Project I/O + engine + UI | Diff/round-trip/stale-file tests |
| M4 — Build | Start/cancel local build; logs and job state | Build runner + API/UI | Pinned QEMU reference build |
| M5 — Export | Standard files portable outside KernelCanvas | Project I/O + QA | No-loss and external-tool verification |
| M6 — Extensions | Layer graph, snapshots, curated templates | Split feature teams | New contracts and independent tests |

### Agent ownership model

- **Core agent:** domain structs, validation, diagnostics, compatibility contracts; no UI or tool execution.
- **Yocto agent:** Python bridge and version capability matrix; no UI changes or opaque hacks around BitBake errors.
- **Project I/O agent:** safe `kas`/file import/export and diff/apply mechanics; preservation tests.
- **Build agent:** controlled local tool execution, job state, cancellation, logs; never raw user shell.
- **Frontend agent:** React features and user feedback; only typed API calls.
- **QA/integration agent:** regression fixtures, command-contract checks, CI, integration evidence; owns no feature implementation by default.

Agents use separate worktrees/branches and record evidence for changes. A task that requires touching another team's public interface needs an agreed contract first. Detailed claim/lease, handover, merge, escalation, and autonomy rules belong in `AGENTS.md` and `docs/TASK_PROTOCOL.md` (not duplicated here).

**Merge policy:** green relevant CI, review of shared interfaces and any command that writes or executes, reproducible test evidence, no silent changes to security or toolchain policy. The integrator may not treat an agent's self-reported "done" as proof.

## 16. Architecture decisions still open

Record decisions, rationale, alternatives, and migration strategy in `docs/DECISIONS.md` before agents build on them:

1. Exact first supported Yocto/Poky release, `kas` version, machine, and image target.
2. How the first local API launches and authenticates a browser session.
3. API schema source of truth / code generation tooling.
4. Whether M0 ships as local web UI only or is packaged in a Tauri shell later.
5. Versioning/capability contract for the Python/BitBake bridge.
6. Exact safe-edit semantics and whether to prefer a managed `.inc`/`.conf` file.
7. Snapshot `.kcanvas` schema and extension (provisional, post-MVP).
8. Repository license and business/open-core model (owner decision, not agent default).
9. Whether local build isolation is supported or only documented for the first release.

Until a decision is recorded, agent instructions must say **proposed**, not silently present a choice as an established requirement.

## 17. Definition of architectural success

This foundation is doing its job when a developer can:

1. Run the Rust engine's import/inspect commands without starting a browser.
2. Replace the GUI without rewriting Yocto integration or project edits.
3. Swap the fake Yocto adapter for the real Python bridge without changing command schemas.
4. Open and re-export supported projects without discarding unknown, untouched files.
5. Prove that a change survived focused tests, CI, and real BitBake validation as applicable.
6. Assign independent features to separate agents with few shared-file edits and no hidden dependencies.
7. Keep a standard Yocto project buildable with upstream tools even if KernelCanvas is uninstalled.

**Design rule:** If a feature makes the UI richer while compromising the correctness, portability, or auditability of the underlying project, the feature is not ready to ship.
