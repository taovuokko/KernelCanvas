#!/usr/bin/env python3
"""Argument-recording Bubblewrap stand-in used only by unit tests."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    record_path = os.environ.get("KC_FAKE_BWRAP_RECORD")
    if record_path:
        Path(record_path).write_text(json.dumps(sys.argv[1:]), encoding="utf-8")
    try:
        separator = sys.argv.index("--")
    except ValueError:
        print("missing --", file=sys.stderr)
        return 2
    command = sys.argv[separator + 1 :]
    if not command:
        print("missing command", file=sys.stderr)
        return 2
    sandbox_arguments = sys.argv[1:separator]
    for index, argument in enumerate(sandbox_arguments):
        if argument != "--ro-bind" or index + 2 >= len(sandbox_arguments):
            continue
        source = Path(sandbox_arguments[index + 1])
        destination = Path(sandbox_arguments[index + 2])
        command_path = Path(command[0])
        try:
            relative = command_path.relative_to(destination)
        except ValueError:
            continue
        command[0] = str(source / relative)
        break
    os.execve(command[0], command, os.environ)
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
