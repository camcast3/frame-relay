"""Periodically sample the network link during a session (to catch Wi-Fi roams / dips)."""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Optional

from . import linkinfo


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LinkMonitor:
    """Samples ``linkinfo.detect()`` on a timer in a background thread."""

    def __init__(self, source: str = "client", machine: Optional[str] = None,
                 interval: float = 15.0):
        self.source = source
        self.machine = machine
        self.interval = interval
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _sample_once(self) -> dict[str, Any]:
        sample = linkinfo.detect()
        sample.update({"source": self.source, "machine": self.machine, "sampled_at": _now()})
        return sample

    def _loop(self) -> None:
        self.samples.append(self._sample_once())
        while not self._stop.wait(self.interval):
            self.samples.append(self._sample_once())

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> list[dict[str, Any]]:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval + 5)
        return self.samples
