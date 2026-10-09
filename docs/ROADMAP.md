# KernelCanvas — Roadmap and Milestone Gates

> **Status:** Planned foundation roadmap v0.1. This is a sequence of **goals**, not a claim that implementation or tests already exist.
> **Source:** `docs/PRODUCT.md` §6 defines product requirements `KC-001` through `KC-007`. These are **requirement identifiers**; GitHub tasks may have separately assigned IDs under `docs/TASK_PROTOCOL.md`.
> **Process:** Every completed outcome requires a linked PR/commit, test evidence, and a recorded reviewer decision.

## 1. Product north star

Import a pinned, supported Yocto/`kas` project; inspect its real configuration; safely change a supported setting with a preview; run a local BitBake image build; inspect logs and export a configuration that works outside KernelCanvas.

**Order matters.** First prove a simple local tool is correct. Templates, `.kcanvas`, multi-user SaaS, cloud builds, marketplace, billing, 3D tooling and custom BitBake emulation come later.

## 2. Milestone definitions

| Milestone | Outcome | Key gate | Status |
| --- | --- | --- | --- |
| **M0 — Foundation** | Buildable Rust workspace, React shell, tiny localhost API, docs, CI | Clean build, API smoke test, frontend build | **NOT VERIFIED** |
| **M1 — Import** | Read-only import of a supported local `kas` configuration and project overview | Known fixtures, unknown-input handling, **no execution** | NOT STARTED |
| **M2 — Inspect** | Resolve selected real metadata via local installed Yocto/BitBake | Pinned supported toolchain, provenance evidence | NOT STARTED |
| **M3 — Safe edit** | Preview and apply a deliberately limited config edit | Exact diffs, no-loss tests, stale-preview protection | NOT STARTED |
| **M4 — Local build** | Start/status/log/cancel a local BitBake job | Pinned QEMU reference image successfully built | NOT STARTED |
| **M5 — Portable export** | Export standard, reproducible project files | External Yocto/`kas` workflow can consume export | NOT STARTED |
| **M6 — Studio extensions** | Layer graph, versioned templates, proposed `.kcanvas` snapshots | Feature-specific acceptance + round trips | NOT STARTED |
| **M7 — Team/cloud (future)** | Organization collaboration and isolated remote build service | Threat model, tenant isolation, billing/cost controls | NOT STARTED |

**Status discipline:** Change `NOT VERIFIED` or `NOT STARTED` only when there is traceable evidence. A scaffolded directory, mock API, or screenshot is not proof of a working Yocto feature.

## 3. M0 — Foundation (first priority)

M0 can proceed on a Fedora Linux developer machine with no Yocto installation. **Do not require downloading or executing third-party recipes merely to finish M0.**

Suggested task queue (assign unique task IDs through the coordinator; titles below do not themselves claim reservations):

| Order | Area | Narrow task and measurable acceptance |
| --- | --- | --- |
| 1 | Repository | Confirm `Cargo.toml` workspace, `crates/core`, `crates/api`, `apps/web`, `.gitignore`; both Rust and web builds execute |
| 2 | Docs/decisions | Review `PRODUCT`, `ARCHITECTURE`, `AGENTS`, `TASK_PROTOCOL`, `TESTING`, `INTEGRATION`; record architecture decisions still open |
| 3 | Core | Add a typed `Diagnostic` and test safe serialization/validation; no Axum/React/BitBake dependencies |
| 4 | API | Localhost health/readiness endpoint; negative security assumptions explicitly documented; deterministic smoke test |
| 5 | Frontend | Visual empty-project welcome flow that builds and clearly distinguishes demo data from real projects |
| 6 | CI | Configure format, Clippy, Rust tests, frontend build (when corresponding files/scripts exist) |
| 7 | Coordinator | Run two non-overlapping agent tasks + independent PR reviews; capture handovers, failure/merge metrics |

**Exit gate:** On a clean checkout and documented toolchain, Rust build/check/tests and frontend build pass, the local API smoke test runs, and the first PR follows the task/merge protocol. Local API authentication/origin protection must be designed before exposing filesystem/process commands; no claim of a secure production endpoint from a health check alone.

## 4. M1 — Project import and declared model (PRODUCT KC-001, KC-002 subset)

- Import a **supported** local `kas` YAML manifest without fetching Git repositories or executing scripts.
- Represent declared repository locations, requested refs, layer paths and selected machine/image settings with source locations when possible.
- Warn about unknown constructs instead of silently flattening advanced YAML or pretending all BitBake settings are resolved.
- Return structured errors for missing files, invalid syntax, symlink/path escapes and unsupported fields.
- Render a read-only project summary through the same typed application command/HTTP contract.

**Gate:** Real small fixture(s), invalid fixtures and an explicit no-execution/no-network test; record exact supported `kas` subset.

## 5. M2 — Resolved metadata (PRODUCT KC-003)

- Implement a narrow out-of-process Python bridge against a selected real BitBake/Tinfoil environment; negotiate tool/version support.
- Distinguish *declared* values from *resolved* values and `Unknown(reason)`.
- Keep arbitrary BitBake evaluation outside the Rust core and browser; capture sanitized diagnostics.
- Define behavior when a user has no compatible local toolchain.

**Gate:** Unit tests using a fake adapter **plus** a real environment test on the pinned Yocto release. A fake adapter pass is not a real BitBake pass.

## 6. M3 — Safe configuration edits (PRODUCT KC-004)

- Support **one** well-defined setting initially; determine exact file ownership and how complex overrides are handled.
- Use `inspect → preview exact diff → user approval → apply → verify`.
- Detect stale file changes using version/hash, preserve unrelated text/comments, refuse unsupported rewrites.
- Cover read-only/damaged files, concurrent edits, symlinks, and partial-write recovery.

**Gate:** Byte-preservation/round-trip tests for untouched files and exact-diff tests; manual real-tool verification when available.

## 7. M4 — Build jobs (PRODUCT KC-005, KC-007)

- Local job start/status/logs/cancel through stable command IDs.
- Explicitly authorize executable, working directory, environment and user confirmation; no arbitrary shell command endpoint.
- Stream bounded, redacted logs; handle exit code, cancellation, cleanup and process ownership.
- Use a pinned supported **QEMU reference machine** and image once chosen in `docs/DECISIONS.md`.

**Gate:** Fake-runner lifecycle tests **and** at least one documented successful real Yocto image build. QEMU boot evidence is distinct from image build evidence.

## 8. M5 — Portability (PRODUCT KC-006)

- Export standard project/configuration files and pinned Git references without cloud account.
- Re-import exported project and compare supported semantics.
- Verify use via standard `kas`/Yocto workflow on the supported reference environment.

**Gate:** Import → inspect → supported edit → export → external tool verification, with artifacts logged and no confidential paths/tokens in exports.

## 9. M6+ — Differentiating features (do not block MVP)

In proposed priority order:

1. Layer dependency/compatibility visualization grounded in real metadata.
2. Searchable recipes/packages and build history with reproducible settings.
3. Versioned curated templates stored as ordinary Git-friendly files; explicit provenance and license metadata.
4. Optional `.kcanvas` snapshot import/export with documented schema and hostile-archive protections.
5. Organization template sharing, review and future verified-build badges backed by real runs.
6. SBOM, license inventory, vulnerability visibility and Device Tree views.
7. Isolated build workers and billing **only** after threat modeling, worker cost limits and owner approval.

## 10. Prioritization rules for the planner

When deciding between tasks, prioritize:

1. Security/data loss or reproducible regression.
2. A missing end-to-end MVP capability or test needed to prove one.
3. Architecture/typed contract that unblocks independent agents.
4. User-facing polish grounded in functioning behavior.
5. Post-MVP exploration after the relevant milestone passes.

Do not choose tasks merely because they yield more commits, branches or impressive UI. Record rejected large-scope ideas as backlog rather than silently expanding the MVP.

## 11. Milestone report template

```md
### M<N> — <name>
Status: NOT STARTED | IN PROGRESS | BLOCKED | VERIFIED
Owner/reviewer: ...
Requirements covered: KC-...
Merged PRs: ...
Tests: <exact commands, environment, results>
Real Yocto level: none | metadata | image-build | QEMU-boot | hardware
Known exclusions: ...
Decision records: ...
Date validated: YYYY-MM-DD
```

**Update rule:** A milestone is `VERIFIED` only after its exit gate is independently checked. If regression breaks the gate, mark it `BLOCKED` or `IN PROGRESS` again; do not preserve a stale green claim.

## 12. Near-term unanswered choices

Before M1–M4 work depends on them, create/approve entries in `docs/DECISIONS.md` for the selected Yocto release, QEMU machine, `kas` version, API/session security, contract schema source, supported settings-editing strategy and local tool execution policy.

**Related docs:** `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/TASK_PROTOCOL.md`, `docs/TESTING.md`.
