"""Minimal terminal spinner, shown while waiting on a blocking SDK call."""

import itertools
import sys
import threading
import time

_FRAMES = "|/-\\"
_INTERVAL = 0.1


class Spinner:
    def __init__(self, message: str):
        self.message = message
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # Keep the real stdout: callers may redirect sys.stdout to hide SDK
        # output (see infra.py), and the spinner should still show.
        self._out = sys.stdout

    def _spin(self) -> None:
        for frame in itertools.cycle(_FRAMES):
            if self._stop.is_set():
                break
            self._out.write(f"\r{frame} {self.message}")
            self._out.flush()
            time.sleep(_INTERVAL)
        self._out.write("\r" + " " * (len(self.message) + 2) + "\r")
        self._out.flush()

    def __enter__(self) -> "Spinner":
        if self._out.isatty():
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        else:
            # Not a terminal (piped, CI): print once instead of animating.
            print(self.message, file=self._out)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
