"""Read-only Claude CLI planner and reviewer adapter.

KC-105 permits outbound connections needed for public documentation, public
GitHub reads, dependencies, and model APIs. Bubblewrap provides filesystem
isolation here, but this adapter does not implement kernel-enforced network
egress filtering. The worker receives no host credentials by default and no
automatic GitHub push, merge, or deployment authority. Future unattended runs
need separately approved authentication and execution authorization; stronger
egress controls may be added by a later task.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping

from . import auth
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
_SANDBOX_RUNTIME = Path("/run/kernelcanvas/claude-runtime")
_SANDBOX_AUTH_PROFILE = _SANDBOX_HOME / ".claude"
_OPENSSL_CRYPTO_POLICY_CONFIG = Path(
    "/etc/crypto-policies/back-ends/opensslcnf.config"
)
_CRYPTO_POLICY_TARGET_ROOT = Path("/usr/share/crypto-policies")
_REVIEW_JSON_SCHEMA = json.dumps(
    {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["APPROVE", "REQUEST_CHANGES"],
            },
            "summary": {"type": "string", "minLength": 1, "maxLength": 2000},
        },
        "required": ["verdict", "summary"],
        "additionalProperties": False,
    },
    separators=(",", ":"),
)
_SYSTEM_ROOTS = (
    Path("/usr/bin"),
    Path("/usr/lib"),
    Path("/usr/lib64"),
    Path("/usr/libexec"),
    Path("/usr/share"),
)
_SYSTEM_LINKS = (Path("/bin"), Path("/sbin"), Path("/lib"), Path("/lib64"))
_SYSTEM_FILES = (
    Path("/etc/ca-certificates.conf"),
    Path("/etc/gai.conf"),
    Path("/etc/hosts"),
    Path("/etc/ld.so.cache"),
    Path("/etc/ld.so.conf"),
    Path("/etc/localtime"),
    Path("/etc/nsswitch.conf"),
    Path("/etc/resolv.conf"),
)
_SYSTEM_DIRECTORIES = (
    Path("/etc/ca-certificates"),
    Path("/etc/ld.so.conf.d"),
    Path("/etc/pki"),
    Path("/etc/ssl/certs"),
)


class ClaudeCLI:
    """Invoke Claude in a read-only sandbox limited to one workspace root."""

    def __init__(
        self,
        workspace_root: Path,
        *,
        executable: str = "claude",
        sandbox_executable: str = "bwrap",
        runtime_root: Path | None = None,
        auth_profile: Path | None = None,
        runner: ProcessRunner | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        root = workspace_root.resolve()
        if not root.is_dir():
            raise InvocationError(f"workspace root is not a directory: {workspace_root}")
        self.workspace_root = root
        self.executable = executable
        self.sandbox_executable = sandbox_executable
        self.runtime_root = runtime_root
        self.auth_profile = (
            auth.resolve_auth_profile(auth_profile, provider="claude")
            if auth_profile is not None
            else None
        )
        self.runner = runner or ProcessRunner()
        self.environment = build_safe_environment(environment)

    def plan(
        self,
        prompt: str,
        *,
        cwd: Path,
        timeout_seconds: float,
        log_dir: Path,
        dry_run: bool = False,
    ) -> CLIResult | InvocationPreview:
        return self._invoke(
            prompt,
            json_schema=None,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            log_dir=log_dir,
            dry_run=dry_run,
        )

    def review(
        self,
        diff_context: str,
        *,
        cwd: Path,
        timeout_seconds: float,
        log_dir: Path,
        dry_run: bool = False,
    ) -> CLIResult | InvocationPreview:
        return self._invoke(
            diff_context,
            json_schema=_REVIEW_JSON_SCHEMA,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            log_dir=log_dir,
            dry_run=dry_run,
        )

    def _invoke(
        self,
        prompt: str,
        *,
        json_schema: str | None,
        cwd: Path,
        timeout_seconds: float,
        log_dir: Path,
        dry_run: bool,
    ) -> CLIResult | InvocationPreview:
        resolved_cwd = cwd.resolve()
        if not resolved_cwd.is_dir():
            raise InvocationError(f"working directory is not a directory: {cwd}")
        if not resolved_cwd.is_relative_to(self.workspace_root):
            raise InvocationError(
                f"working directory is outside configured workspace root: {resolved_cwd}"
            )
        auth_profile = (
            auth.resolve_auth_profile(self.auth_profile, provider="claude")
            if self.auth_profile is not None
            else None
        )

        claude = Path(resolve_executable(self.executable, self.environment))
        bubblewrap = resolve_executable(self.sandbox_executable, self.environment)
        runtime_arguments, sandbox_claude = _claude_runtime_mount(
            claude,
            assigned_worktree=resolved_cwd,
            approved_runtime_root=self.runtime_root,
        )
        claude_argv = (
            sandbox_claude,
            "-p",
            "--output-format",
            "json",
            "--permission-mode",
            "plan",
            "--tools",
            "Read",
            "--allowedTools",
            "Read",
            "--disallowedTools",
            "Bash,Edit,Write,NotebookEdit,WebFetch,WebSearch,Task,mcp__*",
            "--setting-sources",
            "",
            "--strict-mcp-config",
            *(("--json-schema", json_schema) if json_schema is not None else ()),
        )
        argv = (
            bubblewrap,
            "--die-with-parent",
            "--new-session",
            "--unshare-pid",
            *_system_mount_arguments(),
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--tmpfs",
            "/tmp",
            "--dir",
            "/home",
            "--dir",
            str(_SANDBOX_HOME),
            "--setenv",
            "HOME",
            str(_SANDBOX_HOME),
            "--setenv",
            "XDG_CONFIG_HOME",
            str(_SANDBOX_HOME / ".config"),
            "--setenv",
            "XDG_CACHE_HOME",
            "/tmp/cache",
            *_auth_profile_arguments(auth_profile),
            "--ro-bind",
            str(resolved_cwd),
            str(_SANDBOX_WORKTREE),
            *runtime_arguments,
            "--chdir",
            str(_SANDBOX_WORKTREE),
            "--",
            *claude_argv,
        )
        if dry_run:
            return preview_invocation(
                argv,
                cwd=resolved_cwd,
                environment=self.environment,
                stdin_text=prompt,
                timeout_seconds=timeout_seconds,
            )
        output = self.runner.run(
            argv,
            cwd=resolved_cwd,
            environment=self.environment,
            stdin_text=prompt,
            timeout_seconds=timeout_seconds,
            log_dir=log_dir,
        )
        return _json_result(output)


def _auth_profile_arguments(profile: Path | None) -> tuple[str, ...]:
    if profile is None:
        return ()
    return (
        "--bind",
        str(profile),
        str(_SANDBOX_AUTH_PROFILE),
        "--setenv",
        "CLAUDE_CONFIG_DIR",
        str(_SANDBOX_AUTH_PROFILE),
    )


def _system_mount_arguments() -> tuple[str, ...]:
    """Return narrow host runtime mounts needed by native and Node CLIs."""

    arguments: list[str] = []
    for path in _SYSTEM_ROOTS:
        if path.is_dir():
            arguments.extend(("--ro-bind", str(path), str(path)))
    for path in _SYSTEM_LINKS:
        if path.is_symlink():
            arguments.extend(("--symlink", os.readlink(path), str(path)))
        elif path.is_dir():
            arguments.extend(("--ro-bind", str(path), str(path)))
    arguments.extend(("--dir", "/etc"))
    for path in (*_SYSTEM_FILES, *_SYSTEM_DIRECTORIES):
        if path.exists():
            arguments.extend(("--ro-bind", str(path.resolve()), str(path)))
    arguments.extend(_crypto_policy_mount_arguments())
    return tuple(arguments)


def _crypto_policy_mount_arguments() -> tuple[str, ...]:
    """Expose Fedora's OpenSSL policy link without broadening the sandbox."""

    config = _OPENSSL_CRYPTO_POLICY_CONFIG
    if not config.is_symlink():
        raise InvocationError(
            f"required OpenSSL crypto-policy configuration is unavailable: {config}"
        )
    try:
        target = config.resolve(strict=True)
        link_target = os.readlink(config)
    except (OSError, RuntimeError) as error:
        raise InvocationError(
            f"required OpenSSL crypto-policy configuration is unavailable: {config}"
        ) from error
    if not target.is_file() or not target.is_relative_to(
        _CRYPTO_POLICY_TARGET_ROOT
    ):
        raise InvocationError(
            "required OpenSSL crypto-policy target is unavailable or outside "
            f"approved system roots: {target}"
        )
    return (
        "--dir",
        "/etc/crypto-policies",
        "--dir",
        "/etc/crypto-policies/back-ends",
        "--symlink",
        link_target,
        str(config),
    )


def _claude_runtime_mount(
    executable: Path,
    *,
    assigned_worktree: Path,
    approved_runtime_root: Path | None,
) -> tuple[tuple[str, ...], str]:
    """Map Claude only from a system, worktree, or explicitly approved root."""

    resolved = executable.resolve()
    if resolved.is_relative_to(assigned_worktree):
        sandbox_path = _SANDBOX_WORKTREE / resolved.relative_to(assigned_worktree)
        return (), str(sandbox_path)
    if any(resolved.is_relative_to(root) for root in _SYSTEM_ROOTS):
        return (), str(resolved)

    if approved_runtime_root is None:
        raise InvocationError(
            "Claude executable is outside approved system/worktree runtime paths; "
            "an explicit runtime_root is required"
        )

    runtime_root = approved_runtime_root.resolve()
    if not runtime_root.is_dir():
        raise InvocationError(
            f"approved Claude runtime root is not a directory: {approved_runtime_root}"
        )
    if not resolved.is_relative_to(runtime_root):
        raise InvocationError(
            f"Claude executable is outside approved runtime root: {resolved}"
        )

    home = Path.home().resolve()
    broad_roots = tuple(
        path.resolve()
        for path in (Path("/"), Path("/home"), Path("/tmp"), Path("/var"), home)
    )
    sensitive_roots = tuple(
        path.resolve()
        for path in (
            home / ".aws",
            home / ".claude",
            home / ".codex",
            home / ".config",
            home / ".gnupg",
            home / ".kube",
            home / ".ssh",
        )
    )
    if runtime_root in broad_roots or any(
        runtime_root.is_relative_to(sensitive) for sensitive in sensitive_roots
    ):
        raise InvocationError(
            f"refusing broad or sensitive Claude runtime mount: {runtime_root}"
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


def _json_result(output: ProcessOutput) -> CLIResult:
    parsed: JSONValue | None = None
    parse_error: str | None = None
    try:
        value = json.loads(output.stdout)
        if not isinstance(value, (dict, list)):
            raise ValueError("top-level response must be an object or array")
        parsed = value
    except (json.JSONDecodeError, ValueError) as error:
        parse_error = f"invalid Claude JSON response: {error}"
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
