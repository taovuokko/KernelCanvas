"""Typed results and expected failures for CLI adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

JSONScalar: TypeAlias = None | bool | int | float | str
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


class AdapterError(Exception):
    """Base class for expected adapter failures."""


class ExecutableNotFoundError(AdapterError):
    """A required local executable was not found."""


class InvocationError(AdapterError):
    """An invocation was invalid or could not be started safely."""


@dataclass(frozen=True)
class InvocationPreview:
    """A side-effect-free description returned for a dry run."""

    argv: tuple[str, ...]
    cwd: Path
    environment_keys: tuple[str, ...]
    stdin_preview: str


@dataclass(frozen=True)
class CLIResult:
    """Bounded process evidence plus parsed CLI output."""

    argv: tuple[str, ...]
    cwd: Path
    exit_code: int
    timed_out: bool
    stdout_path: Path
    stderr_path: Path
    stdout_truncated: bool
    stderr_truncated: bool
    parsed: JSONValue | None
    parse_error: str | None
    duration_seconds: float

    @property
    def succeeded(self) -> bool:
        """Return true only for a complete, parseable, zero-exit response."""

        return (
            self.exit_code == 0
            and not self.timed_out
            and not self.stdout_truncated
            and self.parse_error is None
            and self.parsed is not None
        )
