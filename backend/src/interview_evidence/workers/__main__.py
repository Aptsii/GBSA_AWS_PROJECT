"""Worker process entrypoint with fail-closed handler registration."""

from __future__ import annotations

import signal
import sys
from threading import Event

from interview_evidence.main import create_worker_registry


def main() -> int:
    registry = create_worker_registry()
    if not registry:
        sys.stderr.write("No worker handlers are registered.\n")
        return 2

    shutdown = Event()

    def stop(_signal_number: int, _frame: object) -> None:
        shutdown.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    shutdown.wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
