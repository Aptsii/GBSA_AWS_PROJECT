"""Fail-closed worker entrypoint until Integration task T176 wires handlers."""

from __future__ import annotations

import sys


def main() -> int:
    sys.stderr.write("No worker handlers are registered; complete T176 before launch.\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
