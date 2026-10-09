# KernelCanvas — Product Definition

> Status: Draft v0.1  
> Product: KernelCanvas Studio  
> Category: Visual development environment for Yocto Project-based embedded Linux systems  
> Scope: Product goals and requirements; implementation details belong in `docs/ARCHITECTURE.md`.

## 1. Vision

KernelCanvas makes embedded Linux development more accessible, understandable, and repeatable without hiding or replacing the underlying Yocto Project toolchain.

Our long-term vision is a visual workspace where engineers can inspect, configure, build, validate, version, and share embedded Linux projects. The same projects must remain usable with standard Yocto/BitBake tooling outside KernelCanvas.

**Positioning:** A visual IDE for Yocto-based embedded Linux projects, with optional team and cloud services. KernelCanvas is an independent project and must not imply official Yocto Project endorsement.

## 2. Target Users

**Primary:** Embedded Linux developers and small-to-medium OEM engineering teams already using Yocto/BitBake.

**Secondary:** Firmware engineers transitioning to embedded Linux, consultants maintaining multiple board support packages (BSPs), and teams onboarding new engineers.

**Not an initial target:** Beginners expecting arbitrary hardware to work with zero BSP knowledge; large enterprises requiring fully managed production fleets on day one.

## 3. Problems to Solve

1. Yocto projects are difficult to understand because configuration is spread across repositories, layers, recipes, and variable overrides.
2. Developers need better visibility into which layers, machines, images, and packages are active and why.
3. Manually editing build configurations can introduce subtle errors and makes onboarding slow.
4. Reproducing or sharing a working build setup across machines and teams requires careful coordination of versions and dependencies.
5. Build logs, failures, and generated artifacts are often difficult to navigate.

## 4. Product Principles

1. **Yocto-native, not a replacement.** BitBake and existing Yocto metadata remain the source of truth.
2. **No lock-in.** Users can always inspect and export standard configuration and project files.
3. **Local-first.** The initial product must work with a user's own Linux development environment; cloud builds are optional and later.
4. **Transparent edits.** Show file diffs and require confirmation before writing modified configurations. Preserve unrelated comments and settings whenever possible.
5. **Reproducibility.** Prefer pinned source revisions and record the toolchain, layer revisions, machine, and configuration used for each build.
6. **Safety.** Never execute imported project code implicitly. Treat recipes, scripts, and repositories as untrusted inputs.
7. **Automation-ready.** Important operations should eventually be accessible through a documented API/CLI, not only GUI clicks.
8. **Evidence over claims.** Functionality is complete only when it is demonstrated with real tests and supported example projects.

## 5. Core Product Experience

A user should be able to:

1. Open an existing Yocto workspace or import a project described by a `kas` configuration.
2. See a visual overview of the machine, distribution, image target, enabled layers, repositories, and pinned revisions.
3. Inspect configuration values and their provenance where the underlying tooling provides it.
4. Make supported configuration changes through forms, with a readable preview of the resulting file diffs.
5. Validate the configuration using supported Yocto/BitBake tooling.
6. Start a build in a configured local Linux build environment, track progress, and inspect logs and artifacts.
7. Export or share a reproducible project definition without needing a KernelCanvas account.

Advanced features, such as visual Device Tree editing, template marketplaces, and remote build fleets, extend this workflow rather than replacing it.

## 6. First Release: MVP

**MVP goal:** Successfully import, inspect, safely modify a small supported subset of configuration, and build a reference Yocto project locally through the GUI.

### Must have (P0)

- [ ] **KC-001 — Project import:** Open a supported `kas` project definition or an existing Yocto build workspace, with clear diagnostics for unsupported inputs.
- [ ] **KC-002 — Project overview:** Show source repositories, pinned revisions where available, layers, `MACHINE`, `DISTRO`, and selected image target.
- [ ] **KC-003 — Configuration inspector:** Read selected configuration values using Yocto-aware tooling; do not pretend that regex parsing of BitBake files is authoritative.
- [ ] **KC-004 — Safe editing:** Edit a deliberately limited set of supported settings, preview changes, and write them only after user confirmation.
- [ ] **KC-005 — Local build:** Launch and observe a build using a properly configured local Yocto/BitBake environment; support cancellation and log inspection.
- [ ] **KC-006 — Project portability:** Preserve or export standard Yocto/`kas` files; no mandatory proprietary format or cloud account.
- [ ] **KC-007 — Verification:** Run an end-to-end test using at least one documented, pinned QEMU-based reference project and confirm produced artifacts.

### Should have after the MVP (P1)

- Layer dependency and compatibility visualization.
- Recipe and package discovery with searchable metadata.
- Build history, configuration diffing, and failure diagnostics.
- Reproducibility report: layer revisions, build settings, and tool versions.
- Import/export of a portable KernelCanvas project snapshot.
- Curated, versioned project templates.

### Later (P2)

- Team workspaces, private templates, sharing, and access controls.
- Template Hub with review, provenance, and verified-build badges.
- Optional remote build workers, shared caches, and artifact storage.
- SBOM, license inventory, and vulnerability reporting.
- Device Tree visualization/editing with platform-specific validation.
- Extension SDK and integrations with CI/CD and device management tools.

## 7. Project Files and Templates

**Default working format:** A normal, Git-friendly directory containing standard Yocto, `kas`, and KernelCanvas metadata files. The user owns these files.

**Portable snapshot (proposed):** `.kcanvas` — a versioned archive for sharing project definitions and GUI metadata. This extension and schema are provisional until separately specified. Store references and pinned revisions by default; do not silently embed entire external repositories or build output.

**Templates:** Versioned, reusable project definitions. Initially, users can import/export them as ordinary files or Git repositories. A hosted Template Hub may follow later.

**Rules:** A template must disclose external repositories, versions, licenses, expected hardware/BSP support, and whether a reference build has been verified. A template does not guarantee compatibility with arbitrary machines.

## 8. Commercial Direction

The core local development experience should remain usable without a subscription. Potential paid offerings include organization workspaces, private templates, shared build infrastructure, artifact retention, audit logs, and enterprise support.

The MVP does **not** require billing, a marketplace, or cloud infrastructure. Pricing and open-source licensing are business decisions to validate separately; this document does not commit the project to a specific license.

## 9. Explicit Non-Goals for MVP

- Rewriting BitBake, Yocto, the Linux kernel, or existing BSPs.
- Supporting every Yocto release, board, and vendor layer immediately.
- Guaranteeing that arbitrary imported configurations will build.
- Building a fully managed multi-tenant cloud builder before isolation and cost controls exist.
- Building a 3D CAD system or a general embedded device simulator.
- Replacing target-device package formats such as RPM, IPK, or DEB.
- Editing arbitrary BitBake syntax through a lossy, home-grown parser.
- Claiming official Yocto Project compatibility certification or endorsement without approval.

## 10. Security, Licensing, and Trust

- Imported recipes, repositories, and build scripts may execute arbitrary code; require explicit action and use appropriate isolation for any hosted execution.
- Never include credentials, SSH keys, tokens, or private repository contents in exported snapshots by default.
- Record component licenses and honor distribution obligations for redistributed tools, layers, and generated images.
- Keep the product's own licensing and any use of Yocto Project trademarks under explicit review.
- Label test results accurately: metadata validation, QEMU boot tests, and tests on physical hardware are different levels of evidence.

## 11. Definition of MVP Success

The MVP is ready for an initial external user test when all of the following are true:

1. A documented example project can be imported from clean, pinned source inputs.
2. The GUI accurately displays the project's key metadata.
3. A supported GUI edit produces a reviewable diff and remains compatible with command-line Yocto tools.
4. The application can start a local build, show its outcome, and expose the build logs and resulting image artifacts.
5. The imported/exported project can be used without a KernelCanvas cloud account.
6. Automated checks and an end-to-end reference-build procedure run reliably and are documented.

## 12. Decisions Still Open

- Which Yocto release(s) and `kas` version(s) are supported first?
- Which QEMU reference machine and image will be the canonical integration test?
- Will the first desktop shell be a local web UI or a Tauri application?
- What is the long-term license/open-core model?
- What exact schema and filename extension will portable snapshots use?

**Decision rule:** Record settled choices in `docs/DECISIONS.md` before agents implement features that depend on them. Unresolved choices must not be presented as final requirements.
