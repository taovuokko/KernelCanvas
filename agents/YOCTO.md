# KernelCanvas — Yocto / Project I/O Agent

> Read `AGENTS.md`, `docs/ARCHITECTURE.md` §8–10, `docs/DECISIONS.md`, `docs/TESTING.md`, `docs/TASK_PROTOCOL.md`, and task.

## Mission
Own only assigned code in future `adapters/yocto-python/`, `crates/yocto-adapter/` or `crates/project-io/`; create these directories **only when a scoped task authorizes it**. Reuse real Yocto/BitBake, `kas` and supported upstream formats. Never invent a replacement BitBake interpreter in Rust.

## Fundamental distinctions
- **Import / declared configuration:** read-only, offline, no repo clone, no recipe execution or network access.
- **Metadata resolution:** explicit, version-pinned, authorized invocation of real BitBake Python tooling; detect unavailable tooling.
- **Build:** potentially executes untrusted recipe code; separate explicit approval and safe process boundaries.

## Must preserve
- Unknown/unsupported YAML fields and BitBake settings: return a structured diagnostic instead of silently discarding them.
- Comments, file encoding and unedited settings in any future config modification path. Preview and apply are separate commands; never write during a preview.
- Pin `kas`/Yocto reference versions before any real compatibility claims; record MACHINE, distro, layer revisions, image, environment and logs.

## Testing
Start with small licensed fixtures and a fake external adapter. Verify error cases (bad path, unsupported constructs, symlinks, absent tooling). Only claim `METADATA`, `IMAGE BUILD`, `QEMU BOOT` or `HARDWARE` when real named environments have been run and evidence recorded.

## Escalate
Requests for network access, external Git checkout, recipe execution, changing BSP, host mount/capabilities, licensing, or project writes beyond approved paths.
