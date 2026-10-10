"""Strict Git worktree verification and bounded review-input collection."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

from .models import WorktreeError

MAX_REVIEW_BYTES = 1024 * 1024
MAX_NEW_FILE_BYTES = 256 * 1024


@dataclass(frozen=True)
class VerifiedWorktree:
    path: Path
    branch: str
    repository_root: Path
    allowed_paths: tuple[str, ...]


def parse_allowed_paths(task_file: Path) -> tuple[str, ...]:
    """Read the bullet list beneath the task card's Allowed paths heading."""

    try:
        lines = task_file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise WorktreeError(f"cannot read task file: {task_file}") from error
    in_section = False
    paths: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.lower() in {"## allowed paths", "## allowed edits"}:
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if in_section and stripped.startswith("- "):
            value = stripped[2:].strip().strip("`")
            _validate_allowed_pattern(value)
            paths.append(value)
    if not paths:
        raise WorktreeError("task file has no parseable Allowed paths section")
    return tuple(paths)


def verify_worktree(
    worktree: Path,
    *,
    workspace_root: Path,
    expected_branch: str,
    allowed_paths: Iterable[str],
    base_ref: str = "main",
) -> VerifiedWorktree:
    root = workspace_root.resolve()
    path = worktree.resolve()
    if not root.is_dir() or not path.is_dir() or not path.is_relative_to(root):
        raise WorktreeError("assigned worktree escapes the approved workspace root")
    if path == root:
        raise WorktreeError("assigned worktree must not be the workspace/main checkout")
    patterns = tuple(allowed_paths)
    if not patterns:
        raise WorktreeError("at least one allowed path is required")
    for pattern in patterns:
        _validate_allowed_pattern(pattern)

    top = Path(_git(path, "rev-parse", "--show-toplevel").strip()).resolve()
    if top != path:
        raise WorktreeError(f"assigned path is not an exact Git worktree root: {path}")
    branch = _git(path, "branch", "--show-current").strip()
    if not branch or branch in {"main", "master"}:
        raise WorktreeError("detached or main checkout cannot be used for agent execution")
    if branch != expected_branch:
        raise WorktreeError(
            f"wrong branch: expected {expected_branch}, found {branch}"
        )
    _git(path, "rev-parse", "--verify", f"refs/heads/{base_ref}")

    changed = changed_paths(path, base_ref=base_ref)
    violations = sorted(item for item in changed if not path_allowed(item, patterns))
    if violations:
        raise WorktreeError(
            "changes outside permitted task scope: " + ", ".join(violations)
        )
    for relative in changed:
        candidate = path / relative
        if candidate.is_symlink():
            raise WorktreeError(f"changed symlink is not accepted: {relative}")
        if candidate.exists() and not candidate.resolve().is_relative_to(path):
            raise WorktreeError(f"changed path escapes worktree: {relative}")
    return VerifiedWorktree(path, branch, root, patterns)


def changed_paths(worktree: Path, *, base_ref: str = "main") -> set[str]:
    values: set[str] = set()
    for arguments in (
        ("diff", "--name-only", "-z", f"{base_ref}...HEAD", "--"),
        ("diff", "--cached", "--name-only", "-z", "HEAD", "--"),
        ("diff", "--name-only", "-z", "--"),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    ):
        output = _git_bytes(worktree, *arguments)
        for raw in output.split(b"\0"):
            if raw:
                values.add(_safe_git_path(raw))
    return values


def collect_review_input(
    verified: VerifiedWorktree,
    *,
    base_ref: str = "main",
    max_bytes: int = MAX_REVIEW_BYTES,
) -> str:
    """Collect committed, staged/unstaged, and relevant untracked content."""

    if max_bytes < 1:
        raise WorktreeError("review input limit must be positive")
    # Re-verify immediately before collection to close scope drift between phases.
    verify_worktree(
        verified.path,
        workspace_root=verified.repository_root,
        expected_branch=verified.branch,
        allowed_paths=verified.allowed_paths,
        base_ref=base_ref,
    )
    sections = [
        b"=== COMMITTED BRANCH DIFF ===\n"
        + _git_bytes(
            verified.path,
            "diff",
            "--binary",
            "--no-ext-diff",
            "--full-index",
            f"{base_ref}...HEAD",
            "--",
        ),
        b"\n=== TRACKED STAGED DIFF ===\n"
        + _git_bytes(
            verified.path,
            "diff",
            "--cached",
            "--binary",
            "--no-ext-diff",
            "--full-index",
            "HEAD",
            "--",
        ),
        b"\n=== TRACKED UNSTAGED DIFF ===\n"
        + _git_bytes(
            verified.path,
            "diff",
            "--binary",
            "--no-ext-diff",
            "--full-index",
            "--",
        ),
    ]
    untracked = _git_bytes(
        verified.path, "ls-files", "--others", "--exclude-standard", "-z"
    )
    sections.append(b"\n=== RELEVANT NEW FILES ===\n")
    for raw in untracked.split(b"\0"):
        if not raw:
            continue
        relative = _safe_git_path(raw)
        if not path_allowed(relative, verified.allowed_paths):
            raise WorktreeError(f"untracked path is outside permitted scope: {relative}")
        candidate = verified.path / relative
        if candidate.is_symlink() or not candidate.is_file():
            raise WorktreeError(f"unsafe new-file type: {relative}")
        if not candidate.resolve().is_relative_to(verified.path):
            raise WorktreeError(f"new file escapes worktree: {relative}")
        try:
            payload = candidate.read_bytes()
        except OSError as error:
            raise WorktreeError(f"cannot read new file: {relative}") from error
        if len(payload) > MAX_NEW_FILE_BYTES:
            raise WorktreeError(f"new file exceeds review limit: {relative}")
        if b"\0" in payload:
            raise WorktreeError(f"binary new file is not accepted for review: {relative}")
        sections.append(f"--- /dev/null\n+++ b/{relative}\n".encode() + payload + b"\n")
    combined = b"".join(sections)
    if len(combined) > max_bytes:
        raise WorktreeError(
            f"review input exceeds bounded limit of {max_bytes} bytes"
        )
    try:
        return combined.decode("utf-8")
    except UnicodeDecodeError as error:
        raise WorktreeError("review input is not valid UTF-8") from error


def path_allowed(relative: str, patterns: Iterable[str]) -> bool:
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts:
        return False
    for pattern in patterns:
        if pattern.endswith("/**"):
            prefix = PurePosixPath(pattern[:-3])
            if path == prefix or prefix in path.parents:
                return True
        elif path == PurePosixPath(pattern):
            return True
    return False


def _validate_allowed_pattern(value: str) -> None:
    if not value or "\x00" in value:
        raise WorktreeError("allowed path must be non-empty and contain no NUL")
    plain = value[:-3] if value.endswith("/**") else value
    path = PurePosixPath(plain)
    if path.is_absolute() or not plain or ".." in path.parts or "." in path.parts:
        raise WorktreeError(f"unsafe allowed path: {value}")
    if "*" in plain or "?" in plain or "[" in plain:
        raise WorktreeError(f"unsupported allowed path pattern: {value}")


def _safe_git_path(raw: bytes) -> str:
    try:
        value = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise WorktreeError("Git returned a non-UTF-8 path") from error
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value.startswith(".git/"):
        raise WorktreeError(f"unsafe Git path: {value}")
    return path.as_posix()


def _git(worktree: Path, *arguments: str) -> str:
    try:
        return _git_bytes(worktree, *arguments).decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise WorktreeError("Git verification output is not valid UTF-8") from error


def _git_bytes(worktree: Path, *arguments: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", os.fspath(worktree), *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=15,
            env={
                "PATH": os.environ.get("PATH", os.defpath),
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
            },
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise WorktreeError(f"Git verification failed: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()[:500]
        raise WorktreeError(f"Git verification failed: {detail}")
    return result.stdout
