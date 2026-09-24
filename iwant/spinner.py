"""Minimal, dependency-free terminal spinner - so `iwant status`/`down`/
`stop`/etc don't just sit there silently while waiting on a blocking SDK
call with no idea whether anything is happening."""

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
        # Captured once, up front, instead of looking up sys.stdout fresh on
        # every frame: some SkyPilot SDK calls (e.g. sky.check.check(), see
        # infra.py) print their own noisy raw output straight to stdout, and
        # callers may want to swallow that by temporarily reassigning
        # sys.stdout for the duration of the call. Writing to this captured
        # reference means the spinner itself keeps showing on the real
        # terminal either way, instead of also getting silenced.
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
            # Non-interactive (piped/redirected/CI) - an animated spinner
            # would just spam the log with \r characters, print once instead.
            print(self.message, file=self._out)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
