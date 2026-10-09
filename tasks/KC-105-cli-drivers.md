# KC-105 — Claude Code CLI + Codex CLI Adapters

> FUTURE TASK; do not start before KC-104 is merged and reviewed. Needs a new GitHub Issue, named owner/reviewer and allowed-path review.

## Outcome

Implement testable, opt-in Python subprocess adapters for locally installed `claude` (read-only planner/reviewer) and `codex` (scoped implementer). A dry-run mode validates arguments and paths without launching model sessions. KC-106 will add the repair loop; KC-107 will add concurrent scheduling.

## CLI principles

- Prefer the installed `claude` and `codex` binaries; validate presence with `shutil.which`. No bundled CLI, no API keys in repo.
- Use `subprocess.Popen` / explicit argv, cwd, timeouts and process-group cancellation; no `shell=True` and no interpolation of task content into shell scripts.
- `claude -p --output-format json` is appropriate for a single planning/review response. Restrict reviewer built-in tools to `Read` and deny MCP (`--disallowedTools 'mcp__*'`). Ensure hooks/settings cannot unexpectedly launch workers; test a safe configuration. If the installed CLI supports `--bare`, note that it can require API-key authentication rather than subscription OAuth; do not assume it is interchangeable.
- `codex exec --sandbox workspace-write --json -` consumes the explicit assignment prompt via stdin. Deny network to workers unless a per-task authorization grants it.
- Capture event stdout/stderr to restricted-size files under ignored `.agent-work/` or the user's state dir. Redact credentials/private URLs. Treat parsed responses as untrusted data.
- Do not permit Claude to call Codex through MCP in orchestrated sessions: Python explicitly owns every worker process. The user may continue using the existing Codex MCP interactively outside this pipeline.
- Do not treat model text as verification. Process exit status, test runner, independent reviewer and GitHub CI are separate gates.
- No automatic push, PR, merge or deploy; explicit owner approval required for external actions.

## Acceptance criteria

- Fake executable tests verify argv, cwd, stdin, timeout, cancellations, nonzero exits, JSON/JSONL parsing and redacted logs.
- A `--dry-run` mode has zero side effects and never consumes API credits.
- Optional real CLI smoke tests run only with maintainer approval and report actual identity/version, exit code, bounded logs and costs when available.
- Errors are structured; no silent fallback to success. Resume/retry semantics are documented.
- Independent reviewer validates sandbox/tool restrictions and that GitHub credentials never reach workers by default.

## Not in this task

No full autonomous loop, multi-worker orchestration, YOCTO build execution, or auto merge. Those belong to later tasks.
