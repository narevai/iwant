"""Minimal terminal spinner, shown while waiting on a blocking SDK call."""

from __future__ import annotations

import itertools
import sys
import threading
import time
from types import TracebackType
from typing import Optional, TextIO

_FRAMES = "|/-\\"
_INTERVAL = 0.1


class Spinner:
    def __init__(self, message: str) -> None:
        self.message: str = message
        self._stop: threading.Event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # Keep the real stdout: callers may redirect sys.stdout to hide SDK
        # output (see infra.py), and the spinner should still show.
        self._out: TextIO = sys.stdout

    def _spin(self) -> None:
        for frame in itertools.cycle(_FRAMES):
            if self._stop.is_set():
                break
            _ = self._out.write(f"\r{frame} {self.message}")
            self._out.flush()
            time.sleep(_INTERVAL)
        _ = self._out.write("\r" + " " * (len(self.message) + 2) + "\r")
        self._out.flush()

    def __enter__(self) -> "Spinner":
        if self._out.isatty():
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        else:
            # Not a terminal (piped, CI): print once instead of animating.
            print(self.message, file=self._out)
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
