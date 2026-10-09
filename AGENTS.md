# KernelCanvas — Agent & Contributor Instructions

> Version: 0.1 (foundation)  
> Status: Active guidance for the current repository; planned tooling is explicitly marked **PLANNED**.  
> Applies to: The repository root and all subdirectories, unless a narrower `AGENTS.md` explicitly refines these rules without weakening safety requirements.

KernelCanvas Studio is a **local-first visual development environment for Yocto Project-based embedded Linux systems**. We are building an engineering tool, not rewriting Yocto or BitBake. The GUI should make real Yocto projects easier to inspect, configure, build, and share while keeping them usable through standard command-line tools.

The development model takes inspiration from PhotoCraft and WordCraft: clear module boundaries, command-driven functionality, evidence-based quality gates, small independently reviewable changes, and safe parallel agent work. **Do not copy their platform assumptions.** KernelCanvas intentionally uses Rust + React/TypeScript + a separate Python/BitBake bridge.

## 1. Start every session here

Read in this order; if a planned file does not exist, note its absence and continue rather than inventing its contents:

1. `docs/PRODUCT.md` — product requirements, supported scope, MVP definition.
2. `docs/ARCHITECTURE.md` — layers, trust boundaries, commands, integration contracts.
3. `docs/DECISIONS.md` — **when present**, accepted architectural decisions. Absence means choices listed as open in the architecture remain open.
4. `docs/ROADMAP.md` — **when present**, milestones, priorities, measurable acceptance criteria.
5. `docs/TASK_PROTOCOL.md` — **when present**, agent task reservations, handovers, and retries.
6. `docs/TESTING.md` and `docs/INTEGRATION.md` — **when present**, detailed test/merge procedure.
7. The assigned task/issue, relevant code and tests, existing contracts, and any previous task handover.

Before editing, run `git status --short --branch`, inspect the target modules and existing commands, and determine whether another worker owns the relevant files. **Do not overwrite unknown local changes.**

### Source-of-truth order

- An explicit instruction from the repository owner for the current task takes priority over normal task selection, but not over security constraints.
- Approved product/architecture decisions and stable interfaces take priority over an agent's implementation preference.
- An agreed task contract and its acceptance tests govern task completion.
- If instructions disagree, preserve existing data, identify the conflict in the handover, and ask for a maintainer decision when behavior or public interfaces could change.

## 2. Product rules — non-negotiable

1. **Yocto-native.** Use real Yocto/BitBake semantics through supported tooling; do not build a competing BitBake parser or executor.
2. **No lock-in.** Ordinary Yocto/`kas` files remain accessible and usable without KernelCanvas; `.kcanvas` is a proposed optional snapshot, not the canonical build source.
3. **Local-first MVP.** Prioritize a working local GUI, local API, imports, selected configuration inspections/edits, and real local builds before hosted infrastructure.
4. **Show provenance.** Distinguish declared configuration, effective values resolved by BitBake, and values that are not known.
5. **No silent changes.** Configuration editing uses inspect → preview exact diff → approve → apply → verify. Protect against stale-file writes.
6. **Imported content is untrusted.** Merely inspecting a project or template must not execute recipes, clone arbitrary repos, or run setup scripts without explicit authorization.
7. **Evidence over features.** A button, mocked return value, or successful TypeScript compilation does not prove the Yocto operation works.
8. **No unsupported promises.** Document specific supported Yocto releases, machines, adapters, and tests. Never assert universal BSP compatibility.

## 3. Repository map and ownership

Existing foundation is intentionally small. Additional modules are introduced **only when implemented**, not because a diagram mentions them.

| Location | Responsibility | Primary worker role |
| --- | --- | --- |
| `apps/web/` | React + TypeScript GUI and typed client | Frontend |
| `crates/core/` | Domain models, validation, diagnostics, stable types | Core |
| `crates/api/` | Local HTTP/API adapter, session authentication, DTO translation | API |
| `crates/engine/` (**PLANNED**) | Command dispatch, state, jobs, permissions | Engine |
| `crates/project-io/` (**PLANNED**) | Safe `kas`/file import/export and previewed edits | Project I/O |
| `crates/yocto-adapter/` (**PLANNED**) | Rust subprocess/JSON boundary to Yocto tools | Yocto |
| `adapters/yocto-python/` (**PLANNED**) | Version-aware BitBake/Tinfoil integration | Yocto |
| `crates/build-runner/` (**PLANNED**) | Owned processes, cancellation, logs and artifacts | Build |
| `crates/format/` (**PLANNED**) | Optional portable `.kcanvas` snapshots | Format |
| `crates/testkit/`, `fixtures/` (**PLANNED**) | Fake adapters, fixtures, reference tests | QA |
| `docs/`, root `AGENTS.md` | Product, contracts, roadmap, decisions, policy | Maintainer/assigned docs worker |
| `.github/workflows/`, `scripts/`, `xtask/` | CI and automated quality checks | QA/Infrastructure |

**File ownership is assigned per task, not granted forever by role.** A worker may touch files outside its default area only when the task explicitly permits it and the owner of the affected contract agrees.

### Layer boundaries

- Domain `core` does not depend on HTTP, UI, Tokio/Axum, Python/BitBake APIs, filesystem execution, or cloud SDKs.
- API handlers translate transport DTOs and invoke commands; do not put Yocto semantics or write `local.conf` directly in handlers.
- The browser never invokes BitBake or directly rewrites Yocto configuration files.
- Side effects happen behind testable adapter ports. `engine` cannot depend on React or Axum request objects.
- Python integration is a **separate out-of-process tool adapter**, not a source of truth for product policy.
- Prefer an isolated module and narrowly scoped registration edit for new commands. Avoid extending giant shared dispatch files.
- Dependency checks with `cargo xtask layers` are **PLANNED**, not yet available by virtue of being documented.

## 4. Autonomous work: permitted versus escalated

Within an explicitly assigned, bounded task, agents **should proceed independently**: inspect the code, implement, add focused tests, run relevant checks, produce evidence, and prepare a reviewable commit/PR. Do not interrupt for routine naming or implementation choices that are covered by existing contracts.

**Ask the maintainer or stop at a safe boundary before:**

- Choosing or changing the product's license, open-core model, pricing, trademarks, or release policy.
- Publishing externally, creating new Git remotes, pushing to a remote or deploying unless the current task specifically authorizes it.
- Accessing or distributing credentials, tokens, private datasets, proprietary BSPs, or customer code.
- Running imported/unreviewed build recipes or scripts, enabling network access, or installing privileged host tooling without task authorization.
- Deleting or rewriting unrelated user data, history, worktrees, caches owned by others, or production resources.
- Changing authentication, permissions, sandbox/isolation boundaries, public command schemas, database migrations, or established security policy without an approved design/contract.
- Introducing new licensing obligations, copying third-party code/assets, or redistributing vendor components without provenance and review.

If blocked, record the **smallest precise decision** needed and useful options. Continue only with independent tasks that do not depend on that decision.

## 5. Safety and reliability — outrank feature work

**Never silently corrupt a Yocto project.** Every crash or data-loss fix must include a regression test where practical.

### Rust

- Production parsing, request, edit, and build paths must not use `unwrap()`, `expect()`, `panic!`, `unreachable!`, `todo!`, or `unimplemented!` on fallible or externally influenced data. Use typed `Result`/errors and actionable diagnostics.
- Treat external indexes, strings, lengths, depth, numbers and file sizes as hostile. Use checked arithmetic, bounds checks, allocation/depth limits and UTF-8-safe slicing.
- `unsafe` is disallowed in foundational crates by default. Any exception requires a documented review decision, a narrow boundary and explicit safety rationale.
- Avoid leaking tokens, private repository URLs, environment variables or credential-bearing command lines to logs/errors.
- Propagate cancellation and failed writes honestly; never report an interrupted or unverified operation as successful.

### External tools and filesystem

- Invoke tools with explicit executable + argument vectors, **not shell-interpolated strings**.
- Restrict tool paths, working directories, environment inheritance and workspace file access. Validate path containment, including symlink and traversal behavior.
- Never assume a localhost API is safe by default: require session authorization, host/origin checks, and restrictive CORS.
- Treat any full Yocto build as code execution. A local build is **not a sandbox**; hosted builds require stronger tenant isolation and resource limits.
- Keep credentials and build artifacts outside Git; use minimal test data and pinned external references.
- Don't perform unsafe or lossy rewriting of `.bb`, `.bbappend`, `.conf`, Device Tree or `kas` YAML. Unknown content must remain untouched or be reported as unsupported.

### Templates / portable snapshots

- Untrusted archives require path-traversal, symlink, duplicate-path, size/ratio and extraction-limit defenses.
- Publishing a template is distinct from trusting it. Record provenance, licenses and pinned revisions. Never silently download or execute its code during preview.
- `.kcanvas` is **proposed and post-MVP**; don't create a proprietary-only workflow prematurely.

## 6. Everything important is a command

**Target architecture:** every user-visible operation has one typed command ID, an input/output schema, permission/side-effect classification, structured errors and focused tests. UI, local API, future CLI and future MCP must use the same operation rather than duplicating business logic.

Examples from the architecture: `project.open`, `project.inspect`, `config.preview_change`, `config.apply_change`, `build.start`, `build.cancel`, `build.status`, `build.logs`, `project.export`.

Rules for a new command:

1. Define user outcome, typed inputs/outputs, required permissions and failure modes.
2. Implement domain logic outside the browser/HTTP transport.
3. Test normal paths, malformed input, missing tools, permissions and cancellation where applicable.
4. Confirm that preview commands are read-only and that write/build commands need explicit authorization.
5. Add versioned API/client contract tests if a public DTO changes.
6. Document the command's verified support level. Don't mark a stub as complete.

Those IDs are **design targets**, not proof that a command registry exists today.

## 7. Parallel agent protocol — initial manual mode

We want PhotoCraft-style narrow file ownership plus iw4L-style isolated work areas. Initially use **Git worktrees**, not several agents concurrently editing one checkout.

- One task → one named owner → one worktree → one branch → one reviewable PR.
- Branch names: `agent/<task-id>-<short-topic>` (example: `agent/KC-001-kas-import`).
- Start new branches from an up-to-date integration branch only when that base is clean. Avoid stacking unrelated features.
- The task must name allowed paths and agreed external contracts before the agent writes code.
- Never change another worker's uncommitted files or reuse their worktree or Cargo target directory.
- Keep shared edits (`Cargo.toml`, `Cargo.lock`, API schemas, CI, central registries, root docs) minimal and explicitly coordinated. Re-read just before patching; never overwrite a newer version.
- Do not run `git reset --hard`, `git clean -fdx`, force-push, mass-reformat, or history rewriting without explicit owner approval.
- A merge conflict is a signal to coordinate, not an invitation to discard another agent's changes.

**Example for a human coordinator** (run in the project root only after the base branch has been committed):

```bash
git worktree add ../kc-agent-KC-001 -b agent/KC-001-kas-import main
cd ../kc-agent-KC-001
export CARGO_TARGET_DIR="$PWD/target/agent-KC-001"
```

Use a private, ignored artifact directory in each worktree, e.g. `.agent-work/`, for run logs and intermediate data. The handover summary attached to the PR/task is the durable shared record; ignored local notes are not automatically visible to other clones or the CI system.

A centralized atomic task-claim/lease system is **PLANNED** for `docs/TASK_PROTOCOL.md`. Until implemented, a coordinator must explicitly assign tasks; agents must not invent distributed locks or simultaneously self-claim the same task based on a Markdown checklist.

### Integration policy

- Agents commit **only their own complete, reviewable units**; direct merges to `main` are not permitted by default.
- A PR needs passing relevant checks, a task ID, a summary, reproducible evidence, and clear notes on risks and remaining gaps.
- Integrator/reviewer checks changed files, public contracts, security-sensitive operations, dependency layering, and claimed test results independently.
- Changes to builds, configuration writes, auth, or archive/template import always get heightened review.
- CI failures cannot be renamed away, ignored, or bypassed. Fix the cause or document an owner-approved exception.
- After integration, update the task state/roadmap through the assigned process and remove an obsolete worktree only when it is safe.

## 8. Quality gates — only claim tests you actually ran

### Baseline checks (when the corresponding project exists)

```bash
# Rust workspace
cargo fmt --all -- --check
cargo check --workspace
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace

# Frontend, when apps/web/package.json exists and dependencies are installed
npm run build --prefix apps/web
```

Run the relevant subset before a task commit, and the full available baseline before proposing merge. If a command does not exist, prerequisites are unavailable, or a test cannot run, mark it **NOT RUN** with the reason; never claim `PASS` based on intent. Also run any configured frontend typecheck/lint scripts only if they exist.

**Future gates, not available yet:** `cargo xtask layers`, project/command contract checks, visual GUI snapshots, `kas` fixtures, and real BitBake/QEMU reference builds. Implement them as milestones; do not falsely require them in M0.

### Test requirements by change type

| Change | Minimum evidence |
| --- | --- |
| Pure domain/core code | Focused unit tests, error cases, relevant Rust checks |
| API or command | Contract and invalid-input tests, permission/failure tests |
| React GUI | Frontend build/type checks, screenshot or manual walkthrough when feasible |
| `kas` import | Known fixtures, unknown-key preservation, **no-execution** import test |
| Yocto adapter | Fake-adapter tests + real pinned toolchain verification when provisioned |
| Config write | Exact diff, unchanged-file round trip, stale-preview and write failure tests |
| Build runner | Start/status/log/cancel tests, exit-code reporting and owned-process cleanup |
| Snapshot/template | Round-trip and archive adversarial tests, provenance/license checks |

Distinguish **unit test passed**, **metadata resolved by BitBake**, **Yocto image built**, **QEMU booted**, and **real device tested**. None implies the others.

### Evidence and scorecards

- Every bug fix adds a reproducing regression test whenever possible.
- Performance claims need reproducible baselines, environment and before/after results.
- Once `docs/SCORECARD.md` exists, update it only with measured, dated evidence. A command's existence is not functional parity.
- Never delete a failing test, lower a metric floor, or weaken a checker merely to get green CI without a documented approval.

## 9. Task lifecycle and handover

Until `docs/TASK_PROTOCOL.md` exists, use the following lightweight states **in the task/PR description**, not as a pretend global scheduler:

- `READY` — scoped task assigned, dependencies satisfied, acceptance criteria clear.
- `IN_PROGRESS` — agent actively owns the task/worktree.
- `BLOCKED` — cannot proceed safely; exact blocker and requested decision recorded.
- `REVIEW` — implementation and evidence ready for independent review.
- `DONE` — reviewed and integrated; do not equate with an agent saying "done".

Within a task, use `PART` for an incomplete handover, `READY_FOR_REVIEW` for a tested candidate and `FINAL` only for the agent's completed scope. `FINAL` **does not imply merged**.

### Required handover block

```text
Task: KC-XXX / short title
Owner / branch / commit: ...
Status: PART | READY_FOR_REVIEW | BLOCKED | FINAL
Scope / changed paths: ...
Implemented: ...
Contracts changed: ...
Checks:
  PASS  <exact command, environment, outcome>
  FAIL  <exact command, relevant error>
  NOT RUN  <command, why>
Yocto verification: not attempted | metadata | build | QEMU | hardware
Security / data / license considerations: ...
Known issues and remaining work: ...
Suggested next task: ...
```

If work stops because of time or context limits, leave a useful `PART` handover and safe Git state. Never fabricate logs, benchmarks, tool results or commits.

## 10. Agent roles and coordination

- **Planner/Coordinator:** decomposes roadmap items, specifies ownership, dependencies, acceptance checks and review requirements. Does not silently re-prioritize product goals.
- **Core/Engine:** pure domain modeling, stable command semantics and recoverable error handling.
- **Yocto/Project I/O:** `kas` and BitBake interaction, read-only inspection first, preservation-aware edits, version capability checks.
- **Frontend:** visual project/navigation flows, typed client calls, accessibility and user-visible error states; no hidden build logic.
- **Build/Infrastructure:** safe local subprocess lifecycle, logs, jobs and CI with resource budgets.
- **QA/Integrator:** adversarial tests, architectural checks, review/merge gates and independent verification; not an automatic self-approver.

Use **small vertical slices** through the architecture where possible. Before parallelizing dependent work, agree on data contracts and fixtures; otherwise assign independent tasks. More concurrent agents do not compensate for ambiguous interfaces.

## 11. Documentation and decision discipline

- Add or change `docs/PRODUCT.md` only for real changes to product scope or goals.
- Update `docs/ARCHITECTURE.md` when a meaningful boundary, module responsibility or contract changes.
- Put major choices and alternatives in `docs/DECISIONS.md` (when created) before dependent implementation.
- Record new capability and verified tests in `docs/ROADMAP.md` and future scorecards only after validation.
- Avoid copying a private Craft team's unpublished rules or treating another repo's scripts as commands available here.
- Write docs and code comments in clear English for consistency; user-facing application language can be localized later.
- Prefer small documentation diffs coupled to the code they describe. No large speculative diagrams detached from working code.

## 12. Before declaring a task complete

Check all of the following:

- [ ] The change satisfies the assigned outcome and stays within approved file ownership.
- [ ] No confidential material, unintended generated artifacts, or third-party license violations were introduced.
- [ ] No unexpected runtime execution, file loss, silent config rewrite, or security policy regression.
- [ ] Relevant automated tests were run and their exact results recorded.
- [ ] New behavior is available through the appropriate typed command or a clearly scoped foundation component.
- [ ] User-visible Yocto claims match the actual test tier; errors remain actionable.
- [ ] Public interfaces and major decisions are documented; dependent workers know about changed contracts.
- [ ] The PR/commit is reviewable and the handover states what remains unfinished.

**Final rule:** Protect the user's Yocto work and the credibility of test results before optimizing the number of agent branches, commits, or shipped features.

---

Reference inspirations (not dependencies):
- PhotoCraft: https://github.com/storytold/photocraft/blob/main/AGENTS.md
- WordCraft: https://github.com/storytold/wordcraft/blob/main/AGENTS.md
- KernelCanvas design: `docs/PRODUCT.md` and `docs/ARCHITECTURE.md`
