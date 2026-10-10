"""Scoped Codex CLI implementation adapter.

KC-105 permits outbound connections needed for public documentation, public
GitHub reads, dependencies, and model APIs. Bubblewrap and Codex's sandbox
provide filesystem isolation, but KC-105 does not implement kernel-enforced
network egress filtering. The worker receives no host credentials by default
and no automatic GitHub push, merge, or deployment authority. Future
unattended runs need separately approved authentication and execution
authorization; stronger egress controls may be added by a later task.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping

from .claude_cli import _system_mount_arguments
from .process import (
    ProcessOutput,
    ProcessRunner,
    build_safe_environment,
    preview_invocation,
    resolve_executable,
)
from .results import CLIResult, InvocationError, InvocationPreview, JSONValue

_SANDBOX_WORKTREE = Path("/workspace")
_SANDBOX_HOME = Path("/home/kernelcanvas")
_SANDBOX_CACHE = Path("/tmp/cache")
_SANDBOX_RUNTIME = Path("/run/kernelcanvas/codex-runtime")
_SYSTEM_RUNTIME_ROOTS = (
    Path("/usr/bin"),
    Path("/usr/lib"),
    Path("/usr/lib64"),
    Path("/usr/libexec"),
    Path("/usr/share"),
)


class CodexCLI:
    """Invoke Codex in Bubblewrap plus Codex's workspace-write sandbox.

    The sandbox intentionally has an empty home and does not mount the host's
    Codex authentication files. A real CLI that cannot authenticate without
    those files must fail closed; callers must not retry it outside Bubblewrap.
    """

    def __init__(
        self,
        workspace_root: Path,
        *,
        executable: str = "codex",
        sandbox_executable: str = "bwrap",
        runtime_root: Path | None = None,
        runner: ProcessRunner | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        root = workspace_root.resolve()
        if not root.is_dir():
            raise InvocationError(
                f"workspace root is not a directory: {workspace_root}"
            )
        self.workspace_root = root
        self.executable = executable
        self.sandbox_executable = sandbox_executable
        self.runtime_root = runtime_root
        self.runner = runner or ProcessRunner()
        self.environment = build_safe_environment(environment)

    def implement(
        self,
        assignment_prompt: str,
        *,
        worktree: Path,
        timeout_seconds: float,
        log_dir: Path,
        dry_run: bool = False,
    ) -> CLIResult | InvocationPreview:
        resolved_worktree = worktree.resolve()
        if not resolved_worktree.is_dir():
            raise InvocationError(f"worktree is not a directory: {worktree}")
        if not resolved_worktree.is_relative_to(self.workspace_root):
            raise InvocationError(
                f"worktree is outside configured workspace root: {resolved_worktree}"
            )
        codex = Path(resolve_executable(self.executable, self.environment))
        bubblewrap = resolve_executable(self.sandbox_executable, self.environment)
        runtime_arguments, sandbox_codex = _codex_runtime_mount(
            codex,
            assigned_worktree=resolved_worktree,
            approved_runtime_root=self.runtime_root,
        )
        codex_argv = (
            sandbox_codex,
            "exec",
            "--sandbox",
            "workspace-write",
            "--json",
            "-c",
            "mcp_servers={}",
            "-",
        )
        argv = (
            bubblewrap,
            "--die-with-parent",
            "--new-session",
            "--unshare-pid",
            "--unshare-ipc",
            "--unshare-uts",
            *_system_mount_arguments(),
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--tmpfs",
            "/tmp",
            "--dir",
            str(_SANDBOX_CACHE),
            "--dir",
            "/home",
            "--dir",
            str(_SANDBOX_HOME),
            "--clearenv",
            "--setenv",
            "HOME",
            str(_SANDBOX_HOME),
            "--setenv",
            "XDG_CONFIG_HOME",
            str(_SANDBOX_HOME / ".config"),
            "--setenv",
            "XDG_CACHE_HOME",
            str(_SANDBOX_CACHE),
            "--setenv",
            "TMPDIR",
            "/tmp",
            "--setenv",
            "PATH",
            "/usr/bin:/bin",
            "--setenv",
            "LANG",
            "C.UTF-8",
            "--setenv",
            "LC_ALL",
            "C.UTF-8",
            "--setenv",
            "GIT_CONFIG_GLOBAL",
            os.devnull,
            "--setenv",
            "GIT_CONFIG_NOSYSTEM",
            "1",
            "--setenv",
            "GIT_TERMINAL_PROMPT",
            "0",
            "--bind",
            str(resolved_worktree),
            str(_SANDBOX_WORKTREE),
            *runtime_arguments,
            "--chdir",
            str(_SANDBOX_WORKTREE),
            "--",
            *codex_argv,
        )
        if dry_run:
            return preview_invocation(
                argv,
                cwd=resolved_worktree,
                environment=self.environment,
                stdin_text=assignment_prompt,
                timeout_seconds=timeout_seconds,
            )
        output = self.runner.run(
            argv,
            cwd=resolved_worktree,
            environment=self.environment,
            stdin_text=assignment_prompt,
            timeout_seconds=timeout_seconds,
            log_dir=log_dir,
        )
        return _jsonl_result(output)


def _codex_runtime_mount(
    executable: Path,
    *,
    assigned_worktree: Path,
    approved_runtime_root: Path | None,
) -> tuple[tuple[str, ...], str]:
    """Map the Codex executable without exposing an implicit host directory."""

    resolved = executable.resolve()
    if resolved.is_relative_to(assigned_worktree):
        sandbox_path = _SANDBOX_WORKTREE / resolved.relative_to(assigned_worktree)
        return (), str(sandbox_path)
    if any(resolved.is_relative_to(root) for root in _SYSTEM_RUNTIME_ROOTS):
        return (), str(resolved)
    if approved_runtime_root is None:
        raise InvocationError(
            "Codex executable is outside approved system/worktree runtime paths; "
            "an explicit runtime_root is required"
        )

    runtime_root = approved_runtime_root.resolve()
    if not runtime_root.is_dir():
        raise InvocationError(
            f"approved Codex runtime root is not a directory: {approved_runtime_root}"
        )
    if not resolved.is_relative_to(runtime_root):
        raise InvocationError(
            f"Codex executable is outside approved runtime root: {resolved}"
        )

    home = Path.home().resolve()
    forbidden_roots = (
        Path("/"),
        home,
        home / ".aws",
        home / ".codex",
        home / ".config",
        home / ".ssh",
    )
    if runtime_root in forbidden_roots or any(
        runtime_root.is_relative_to(sensitive) for sensitive in forbidden_roots[2:]
    ):
        raise InvocationError(
            f"refusing broad or sensitive Codex runtime mount: {runtime_root}"
        )

    return (
        (
            "--dir",
            "/run",
            "--dir",
            "/run/kernelcanvas",
            "--ro-bind",
            str(runtime_root),
            str(_SANDBOX_RUNTIME),
        ),
        str(_SANDBOX_RUNTIME / resolved.relative_to(runtime_root)),
    )


def _jsonl_result(output: ProcessOutput) -> CLIResult:
    parsed_lines: list[JSONValue] = []
    parse_error: str | None = None
    lines = [line for line in output.stdout.splitlines() if line.strip()]
    if not lines:
        parse_error = "invalid Codex JSONL response: response was empty"
    else:
        for line_number, line in enumerate(lines, start=1):
            try:
                value = json.loads(line)
                if not isinstance(value, (dict, list)):
                    raise ValueError("event must be an object or array")
                parsed_lines.append(value)
            except (json.JSONDecodeError, ValueError) as error:
                parse_error = (
                    f"invalid Codex JSONL response at line {line_number}: {error}"
                )
                parsed_lines = []
                break
    parsed: JSONValue | None = parsed_lines if parse_error is None else None
    return CLIResult(
        argv=output.argv,
        cwd=output.cwd,
        exit_code=output.exit_code,
        timed_out=output.timed_out,
        stdout_path=output.stdout_path,
        stderr_path=output.stderr_path,
        stdout_truncated=output.stdout_truncated,
        stderr_truncated=output.stderr_truncated,
        parsed=parsed,
        parse_error=parse_error,
        duration_seconds=output.duration_seconds,
    )
