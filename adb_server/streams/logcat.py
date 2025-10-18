"""`logcat:` service implementation."""

from __future__ import annotations

import threading
import time
from typing import Optional

from .base import BaseStream


class LogcatStream(BaseStream):
    """Simulate adb logcat by streaming messages from the mock device."""

    def __init__(self, transport, local_id: int, remote_id: int, device, interval: float = 0.2) -> None:
        super().__init__(transport, local_id, remote_id)
        self.device = device
        self.interval = interval
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        def run() -> None:
            while not self._stop_event.is_set():
                lines = self.device.next_log_lines(5)
                if not lines:
                    time.sleep(self.interval)
                    continue
                payload = "\n".join(lines) + "\n"
                try:
                    self.send(payload.encode("utf-8"))
                except Exception:
                    break
                time.sleep(self.interval)

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def handle_client_data(self, data: bytes) -> None:
        # logcat does not process client data; allow Ctrl+C to stop
        if b"\x03" in data:
            self.close()

    def handle_close(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        super().handle_close()
