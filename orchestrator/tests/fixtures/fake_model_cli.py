#!/usr/bin/env python3
"""Deterministic fake for Claude/Codex adapter tests; never contacts a service."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    stdin_text = sys.stdin.read()
    record_path = os.environ.get("KC_FAKE_RECORD")
    if record_path:
        Path(record_path).write_text(
            json.dumps(
                {
                    "argv": sys.argv[1:],
                    "cwd": os.getcwd(),
                    "stdin": stdin_text,
                    "environment": dict(os.environ),
                    "environment_keys": sorted(os.environ),
                }
            ),
            encoding="utf-8",
        )

    mode = os.environ.get("KC_FAKE_MODE", "success")
    if mode == "nonzero":
        print('{"error":"failed"}')
        print("simulated failure", file=sys.stderr)
        return 17
    if mode == "malformed":
        print("not-json")
        return 0
    if mode == "large":
        sys.stdout.write("x" * 200_000)
        sys.stderr.write("y" * 200_000)
        return 0
    if mode == "secret":
        print('{"token":"token=very-secret-value"}')
        print("https://person:private-password@example.invalid/repo", file=sys.stderr)
        return 0
    if mode == "timeout-child":
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)",
            ],
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        pid_path = os.environ.get("KC_FAKE_CHILD_PID")
        if pid_path:
            Path(pid_path).write_text(str(child.pid), encoding="ascii")
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(60)
        return 0

    executable = Path(sys.argv[0]).name
    if "codex" in executable:
        print(json.dumps({"type": "started"}))
        print(json.dumps({"type": "completed", "input": stdin_text}))
    else:
        print(json.dumps({"result": "ok", "input": stdin_text}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
