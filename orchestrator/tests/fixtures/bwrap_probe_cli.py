#!/usr/bin/python3
"""Harmless CLI used to verify the real Bubblewrap filesystem boundary."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    request = json.loads(sys.stdin.read())
    visible = Path("visible.txt").read_text(encoding="utf-8")

    write_succeeded = False
    try:
        Path(request.get("write_name", "forbidden-write.txt")).write_text(
            "sandbox-write", encoding="utf-8"
        )
        write_succeeded = True
    except OSError:
        pass

    outside_inaccessible = False
    try:
        Path(request["outside_path"]).read_text(encoding="utf-8")
    except OSError:
        outside_inaccessible = True

    print(
        json.dumps(
            {
                "cwd": os.getcwd(),
                "outside_inaccessible": outside_inaccessible,
                "visible": visible,
                "write_denied": not write_succeeded,
                "write_succeeded": write_succeeded,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
