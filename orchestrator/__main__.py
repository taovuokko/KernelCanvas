"""Module entry point for ``python -m orchestrator``."""

import sys

from .cli import main


if __name__ == "__main__":
    sys.exit(main())

