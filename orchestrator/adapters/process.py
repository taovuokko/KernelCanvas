"""Safe, bounded process execution shared by local CLI adapters."""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .results import ExecutableNotFoundError, InvocationError, InvocationPreview

DEFAULT_MAX_OUTPUT_BYTES = 1024 * 1024
DEFAULT_MAX_STDIN_BYTES = 4 * 1024 * 1024
TRUNCATION_MARKER = b"\n[output truncated]\n"

_INHERITED_ENVIRONMENT = frozenset(
    {
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LOGNAME",
        "PATH",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "TERM",
        "TMPDIR",
        "USER",
    }
)
_FORBIDDEN_ENVIRONMENT_FRAGMENTS = (
    "API_KEY",
    "AUTHORIZATION",
    "CREDENTIAL",
    "PASSWORD",
    "SECRET",
    "TOKEN",
)
_FORBIDDEN_ENVIRONMENT_PREFIXES = (
    "AWS_",
    "AZURE_",
    "GH_",
    "GITHUB_",
    "GOOGLE_",
)
_FORBIDDEN_ENVIRONMENT_NAMES = frozenset(
    {"GIT_ASKPASS", "SSH_ASKPASS", "SSH_AUTH_SOCK"}
)

_JSON_FIELD_REDACTION = re.compile(
    r'(?i)("[^"\\]*(?:token|secret|password|api[_-]?key)[^"\\]*"\s*:\s*)'
    r'"(?:\\.|[^"\\])*"'
)
_REDACTIONS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+"),
    re.compile(r"(?i)((?:api[_-]?key|password|secret|token)\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(https?://)([^/@\s:]+):([^/@\s]+)@"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
)


@dataclass(frozen=True)
class ProcessOutput:
    argv: tuple[str, ...]
    cwd: Path
    exit_code: int
    timed_out: bool
    stdout: str
    stderr: str
    stdout_path: Path
    stderr_path: Path
    stdout_truncated: bool
    stderr_truncated: bool
    duration_seconds: float


class _BoundedCapture:
    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._data = bytearray()
        self.truncated = False

    def consume(self, chunk: bytes) -> None:
        remaining = self._limit - len(self._data)
        if remaining > 0:
            self._data.extend(chunk[:remaining])
        if len(chunk) > remaining:
            self.truncated = True

    def value(self) -> bytes:
        return bytes(self._data)


def _is_forbidden_environment_name(name: str) -> bool:
    upper = name.upper()
    return (
        upper in _FORBIDDEN_ENVIRONMENT_NAMES
        or upper.startswith(_FORBIDDEN_ENVIRONMENT_PREFIXES)
        or any(fragment in upper for fragment in _FORBIDDEN_ENVIRONMENT_FRAGMENTS)
    )


def build_safe_environment(
    extra: Mapping[str, str] | None = None,
    *,
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build an explicit environment allow-list and reject credential variables."""

    inherited = os.environ if source is None else source
    environment = {
        key: inherited[key]
        for key in _INHERITED_ENVIRONMENT
        if key in inherited and not _is_forbidden_environment_name(key)
    }
    environment.setdefault("PATH", os.defpath)
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    for key, value in (extra or {}).items():
        if not key or "=" in key or "\x00" in key:
            raise InvocationError(f"invalid environment variable name: {key!r}")
        if _is_forbidden_environment_name(key):
            raise InvocationError(f"credential-bearing environment variable is forbidden: {key}")
        if "\x00" in value:
            raise InvocationError(f"environment variable contains NUL: {key}")
        environment[key] = value
    return environment


def resolve_executable(executable: str, environment: Mapping[str, str]) -> str:
    """Resolve an executable without invoking it."""

    if not executable or "\x00" in executable:
        raise InvocationError("executable must be a non-empty string without NUL")
    candidate = Path(executable)
    if candidate.parent != Path("."):
        resolved = candidate.expanduser().resolve()
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return str(resolved)
        raise ExecutableNotFoundError(f"executable not found or not executable: {executable}")
    resolved_name = shutil.which(executable, path=environment.get("PATH"))
    if resolved_name is None:
        raise ExecutableNotFoundError(f"executable not found: {executable}")
    return resolved_name


def redact_text(value: str) -> str:
    """Redact common credential forms before text reaches disk or previews."""

    redacted = _JSON_FIELD_REDACTION.sub(r'\1"[redacted]"', value)
    for pattern in _REDACTIONS:
        if pattern.groups >= 3:
            redacted = pattern.sub(r"\1[redacted]:[redacted]@", redacted)
        elif pattern.groups:
            redacted = pattern.sub(r"\1[redacted]", redacted)
        else:
            redacted = pattern.sub("[redacted]", redacted)
    return redacted


def preview_invocation(
    argv: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    stdin_text: str,
    timeout_seconds: float,
    preview_characters: int = 512,
) -> InvocationPreview:
    if not cwd.is_dir():
        raise InvocationError(f"working directory is not a directory: {cwd}")
    if timeout_seconds <= 0:
        raise InvocationError("timeout_seconds must be positive")
    if not isinstance(stdin_text, str):
        raise InvocationError("stdin_text must be a string")
    if preview_characters < 1:
        raise InvocationError("preview_characters must be positive")
    preview = redact_text(stdin_text[:preview_characters])
    if len(stdin_text) > preview_characters:
        preview += "\n[input preview truncated]"
    return InvocationPreview(
        argv=tuple(argv),
        cwd=cwd,
        environment_keys=tuple(sorted(environment)),
        stdin_preview=preview,
    )


class ProcessRunner:
    """Launch one owned process group and retain only bounded output."""

    def __init__(
        self,
        *,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
        max_stdin_bytes: int = DEFAULT_MAX_STDIN_BYTES,
        terminate_grace_seconds: float = 0.5,
    ) -> None:
        if max_output_bytes < 1:
            raise InvocationError("max_output_bytes must be positive")
        if max_stdin_bytes < 1:
            raise InvocationError("max_stdin_bytes must be positive")
        if terminate_grace_seconds < 0:
            raise InvocationError("terminate_grace_seconds must not be negative")
        self.max_output_bytes = max_output_bytes
        self.max_stdin_bytes = max_stdin_bytes
        self.terminate_grace_seconds = terminate_grace_seconds

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        environment: Mapping[str, str],
        stdin_text: str,
        timeout_seconds: float,
        log_dir: Path,
    ) -> ProcessOutput:
        arguments = tuple(argv)
        if not arguments or any("\x00" in argument for argument in arguments):
            raise InvocationError("argv must be non-empty and contain no NUL")
        resolved_cwd = cwd.resolve()
        if not resolved_cwd.is_dir():
            raise InvocationError(f"working directory is not a directory: {cwd}")
        if timeout_seconds <= 0:
            raise InvocationError("timeout_seconds must be positive")
        if not isinstance(stdin_text, str):
            raise InvocationError("stdin_text must be a string")
        stdin_bytes = stdin_text.encode("utf-8")
        if len(stdin_bytes) > self.max_stdin_bytes:
            raise InvocationError(
                f"stdin exceeds {self.max_stdin_bytes} byte invocation limit"
            )

        log_directory_fd = self._prepare_log_directory(log_dir)
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                list(arguments),
                cwd=resolved_cwd,
                env=dict(environment),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                start_new_session=True,
            )
        except FileNotFoundError as error:
            os.close(log_directory_fd)
            raise ExecutableNotFoundError(f"executable not found: {arguments[0]}") from error
        except OSError as error:
            os.close(log_directory_fd)
            raise InvocationError(f"failed to start executable: {error}") from error

        if process.stdin is None or process.stdout is None or process.stderr is None:
            self._terminate_process_group(process)
            os.close(log_directory_fd)
            raise InvocationError("subprocess pipes were not created")

        stdout_capture = _BoundedCapture(self.max_output_bytes)
        stderr_capture = _BoundedCapture(self.max_output_bytes)
        readers = (
            threading.Thread(
                target=self._drain,
                args=(process.stdout, stdout_capture),
                daemon=True,
            ),
            threading.Thread(
                target=self._drain,
                args=(process.stderr, stderr_capture),
                daemon=True,
            ),
        )
        writer = threading.Thread(
            target=self._write_stdin,
            args=(process.stdin, stdin_bytes),
            daemon=True,
        )
        for reader in readers:
            reader.start()
        writer.start()

        timed_out = False
        deadline = started + timeout_seconds
        try:
            process.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            timed_out = True
            self._terminate_process_group(process)

        for reader in readers:
            remaining = max(0.0, deadline - time.monotonic()) if not timed_out else 1.0
            reader.join(remaining)
        if any(reader.is_alive() for reader in readers):
            timed_out = True
            self._terminate_process_group(process)
            for reader in readers:
                reader.join(1.0)
        writer.join(1.0)
        if process.poll() is None:
            timed_out = True
            self._terminate_process_group(process)

        duration = time.monotonic() - started
        stdout_bytes = stdout_capture.value()
        stderr_bytes = stderr_capture.value()
        stdout_text = stdout_bytes.decode("utf-8", errors="replace")
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")
        stdout_path = log_dir / "stdout.log"
        stderr_path = log_dir / "stderr.log"
        try:
            self._write_log(
                log_directory_fd,
                stdout_path.name,
                stdout_text,
                stdout_capture.truncated,
            )
            self._write_log(
                log_directory_fd,
                stderr_path.name,
                stderr_text,
                stderr_capture.truncated,
            )
        finally:
            os.close(log_directory_fd)
        return ProcessOutput(
            argv=arguments,
            cwd=resolved_cwd,
            exit_code=process.returncode if process.returncode is not None else -signal.SIGKILL,
            timed_out=timed_out,
            stdout=stdout_text,
            stderr=stderr_text,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            stdout_truncated=stdout_capture.truncated,
            stderr_truncated=stderr_capture.truncated,
            duration_seconds=duration,
        )

    @staticmethod
    def _drain(stream, capture: _BoundedCapture) -> None:
        try:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    return
                capture.consume(chunk)
        finally:
            stream.close()

    @staticmethod
    def _write_stdin(stream, data: bytes) -> None:
        try:
            stream.write(data)
            stream.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                stream.close()
            except OSError:
                pass

    def _terminate_process_group(self, process: subprocess.Popen[bytes]) -> None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        grace_deadline = time.monotonic() + self.terminate_grace_seconds
        while time.monotonic() < grace_deadline and self._process_group_exists(process.pid):
            time.sleep(min(0.01, max(0.0, grace_deadline - time.monotonic())))
        try:
            if self._process_group_exists(process.pid):
                os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired as error:
            raise InvocationError("owned process group did not terminate") from error

    @staticmethod
    def _process_group_exists(process_group_id: int) -> bool:
        try:
            os.killpg(process_group_id, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    @staticmethod
    def _prepare_log_directory(log_dir: Path) -> int:
        """Create and open a log directory without following any symlink."""

        absolute = Path(os.path.abspath(log_dir))
        components = absolute.parts[1:]
        if not components:
            raise InvocationError("log directory must not be the filesystem root")

        directory_flags = os.O_RDONLY | os.O_DIRECTORY
        if hasattr(os, "O_CLOEXEC"):
            directory_flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            directory_flags |= os.O_NOFOLLOW

        current_fd = os.open(os.sep, directory_flags)
        try:
            for index, component in enumerate(components):
                try:
                    next_fd = os.open(component, directory_flags, dir_fd=current_fd)
                except FileNotFoundError:
                    os.mkdir(component, mode=0o700, dir_fd=current_fd)
                    next_fd = os.open(component, directory_flags, dir_fd=current_fd)
                except OSError as error:
                    raise InvocationError(
                        f"log directory contains an unsafe component: {absolute}"
                    ) from error
                os.close(current_fd)
                current_fd = next_fd
                if index == len(components) - 1:
                    os.fchmod(current_fd, 0o700)
            return current_fd
        except OSError as error:
            os.close(current_fd)
            raise InvocationError(f"could not prepare log directory: {error}") from error
        except Exception:
            os.close(current_fd)
            raise

    def _write_log(
        self,
        directory_fd: int,
        filename: str,
        value: str,
        truncated: bool,
    ) -> None:
        payload = redact_text(value).encode("utf-8")
        if len(payload) > self.max_output_bytes:
            payload = payload[: self.max_output_bytes].decode(
                "utf-8", errors="ignore"
            ).encode("utf-8")
            truncated = True
        if truncated:
            payload += TRUNCATION_MARKER
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(filename, flags, 0o600, dir_fd=directory_fd)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
        except OSError as error:
            raise InvocationError(
                f"could not write bounded log {filename}: {error}"
            ) from error
