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

    profile_directory = None
    profile_read = None
    profile_refresh_succeeded = None
    profile_environment = request.get("profile_environment")
    if profile_environment:
        profile_directory = os.environ.get(profile_environment)
        profile_refresh_succeeded = False
        if profile_directory:
            profile = Path(profile_directory)
            try:
                profile_read = (profile / "profile-marker.txt").read_text(
                    encoding="utf-8"
                )
                (profile / "refresh-marker.txt").write_text(
                    "refreshed", encoding="utf-8"
                )
                profile_refresh_succeeded = True
            except OSError:
                pass

    crypto_policy_path = request.get("crypto_policy_path")
    crypto_policy_readable = None
    crypto_policy_is_symlink = None
    crypto_policy_target = None
    if crypto_policy_path:
        crypto_policy = Path(crypto_policy_path)
        crypto_policy_is_symlink = crypto_policy.is_symlink()
        try:
            crypto_policy_target = str(crypto_policy.resolve(strict=True))
            crypto_policy_readable = crypto_policy.is_file()
        except OSError:
            crypto_policy_readable = False

    print(
        json.dumps(
            {
                "cwd": os.getcwd(),
                "crypto_policy_is_symlink": crypto_policy_is_symlink,
                "crypto_policy_readable": crypto_policy_readable,
                "crypto_policy_target": crypto_policy_target,
                "outside_inaccessible": outside_inaccessible,
                "profile_directory": profile_directory,
                "profile_read": profile_read,
                "profile_refresh_succeeded": profile_refresh_succeeded,
                "visible": visible,
                "write_denied": not write_succeeded,
                "write_succeeded": write_succeeded,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
