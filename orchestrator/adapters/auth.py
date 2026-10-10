"""Validation for explicitly selected, dedicated model CLI auth profiles."""

from __future__ import annotations

import os
import pwd
import stat
from pathlib import Path

from .results import InvocationError

_AUTH_DIRECTORY_PARTS = (".local", "share", "kernelcanvas", "auth")
_PROVIDERS = frozenset({"claude", "codex"})


def dedicated_auth_root() -> Path:
    """Return the only host directory from which auth profiles may be selected."""

    return _host_home().joinpath(*_AUTH_DIRECTORY_PARTS)


def _host_home() -> Path:
    """Resolve the account home without trusting an inherited HOME variable."""

    try:
        return Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
    except (KeyError, OSError) as error:
        raise InvocationError("could not determine the current user's home") from error


def resolve_auth_profile(profile: Path, *, provider: str) -> Path:
    """Resolve and validate one private, direct child profile for a provider.

    Profiles are deliberately not discovered. The maintainer must pass an absolute
    path below ``~/.local/share/kernelcanvas/auth/<provider>/``. The selected
    directory is later mounted writable so the CLI can refresh its own tokens.
    """

    if provider not in _PROVIDERS:
        raise InvocationError(f"unsupported authentication profile provider: {provider}")
    selected = Path(profile)
    if "\x00" in os.fspath(selected):
        raise InvocationError("authentication profile path must not contain NUL")
    if not selected.is_absolute():
        raise InvocationError("authentication profile path must be absolute")
    if ".." in selected.parts:
        raise InvocationError("authentication profile path must not contain traversal")

    try:
        auth_root = dedicated_auth_root().resolve(strict=True)
        provider_root = (auth_root / provider).resolve(strict=True)
        resolved = selected.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise InvocationError(
            "authentication profile and its dedicated KernelCanvas directory must exist"
        ) from error

    if not auth_root.is_dir() or not provider_root.is_dir() or not resolved.is_dir():
        raise InvocationError("authentication profile path must select a directory")
    home = _host_home()
    broad_roots = {
        Path("/"),
        home.parent,
        home,
        Path("/tmp").resolve(),
        Path("/var").resolve(),
    }
    try:
        sensitive_roots = tuple(
            (home / name).resolve()
            for name in (
                ".aws",
                ".claude",
                ".codex",
                ".config",
                ".gnupg",
                ".kube",
                ".ssh",
            )
        )
    except (OSError, RuntimeError) as error:
        raise InvocationError("could not validate sensitive host paths") from error
    if auth_root in broad_roots or any(
        auth_root == sensitive or auth_root.is_relative_to(sensitive)
        for sensitive in sensitive_roots
    ):
        raise InvocationError("refusing broad or sensitive authentication root")
    if provider_root.parent != auth_root or resolved.parent != provider_root:
        raise InvocationError(
            "authentication profile must be one direct child of the dedicated "
            f"KernelCanvas {provider} auth directory"
        )
    if resolved in {Path("/"), home, auth_root, provider_root}:
        raise InvocationError("refusing broad authentication profile mount")
    if any(
        os.path.ismount(directory)
        for directory in (auth_root, provider_root, resolved)
    ):
        raise InvocationError(
            "authentication directories must not be filesystem mount points"
        )

    for directory in (auth_root, provider_root, resolved):
        _verify_private_directory(directory)
    return resolved


def _verify_private_directory(directory: Path) -> None:
    try:
        metadata = directory.stat()
    except OSError as error:
        raise InvocationError(
            "could not inspect authentication profile directory"
        ) from error
    if metadata.st_uid != os.getuid():
        raise InvocationError(
            "authentication profile directories must be owned by the current user"
        )
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise InvocationError(
            "authentication profile directories must not grant group or other permissions"
        )
