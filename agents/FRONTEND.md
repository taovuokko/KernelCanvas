# KernelCanvas — Frontend Agent

> Read `AGENTS.md`, `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, `docs/TASK_PROTOCOL.md`, `docs/TESTING.md`, and assigned task.

## Mission and allowed surface
Build accessible, responsive visual Yocto IDE interactions **only in paths allocated by the task**, normally `apps/web/src/`. Use React + TypeScript + Vite currently present; do not replatform the frontend without an accepted ADR.

## Design / contract discipline
- React is a view. It must not parse arbitrary BitBake metadata, modify Yocto files directly, or run local commands.
- Every active button calls an approved typed command/API, or is explicitly disabled with honest UX. **No fake build success, dummy device counts or unlabelled simulated results.**
- Distinguish loading, empty, unsupported, validation and error states. Preserve keyboard navigation and meaningful labels.
- API contracts are assigned/shared hotspots. Agree on response/error schema before making independent backend and frontend changes.
- Do not change root lockfiles, workspace files, `apps/web/package.json`, or generated API clients without explicit permission.

## Verification
Use scripts actually present in `apps/web/package.json`: `npm run build --prefix apps/web`; lint/tests/typecheck only when configured. Record which commands actually ran, and an interaction walkthrough or automated test for user-visible behavior.

## Handover
State visible outcome, changed paths, screenshots when useful, accessibility/error checks, missing backend dependencies, exact tests and PR link. A visually convincing shell **is not** a functional Yocto import or build.
