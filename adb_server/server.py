"""Entry point for the mock ADB server."""

from __future__ import annotations

import argparse
import logging
import socket
import threading
from pathlib import Path
from typing import Optional

from .config import ConfigurationError, load_config
from .host import ADBHostSession
from .mock_device import MockDevice

LOGGER = logging.getLogger(__name__)
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "mock_device_config.json"


class ADBServer:
    """Socket server compatible with regular adb clients."""

    def __init__(self, host: str = "127.0.0.1", port: int = 5037, config_path: Optional[Path] = None) -> None:
        self.host = host
        self.port = port
        self.config_path = config_path or DEFAULT_CONFIG
        self._sock: Optional[socket.socket] = None
        self._threads: list[threading.Thread] = []
        self._running = threading.Event()
        self.device = self._load_device()

    def _load_device(self) -> MockDevice:
        config_file = Path(self.config_path)
        if not config_file.exists():
            raise ConfigurationError(f"Mock configuration not found: {config_file}")
        config = load_config(config_file)
        return MockDevice.from_config(config)

    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._sock is not None:
            raise RuntimeError("Server already started")
        LOGGER.info("Starting mock ADB server on %s:%s", self.host, self.port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen(5)
        self._sock = sock
        self._running.set()
        threading.Thread(target=self._accept_loop, name="adb-accept", daemon=True).start()

    def _accept_loop(self) -> None:
        assert self._sock is not None
        while self._running.is_set():
            try:
                conn, addr = self._sock.accept()
            except OSError:
                break
            LOGGER.info("Client connected from %s:%s", *addr)
            thread = threading.Thread(target=self._handle_client, args=(conn,), daemon=True)
            thread.start()
            self._threads.append(thread)

    def _handle_client(self, conn: socket.socket) -> None:
        with conn:
            session = ADBHostSession(conn, self.device)
            session.run()

    def stop(self) -> None:
        self._running.clear()
        if self._sock:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._sock.close()
            self._sock = None
        for thread in self._threads:
            thread.join(timeout=0.5)
        LOGGER.info("ADB server stopped")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Mock ADB server")
    parser.add_argument("--host", default="127.0.0.1", help="Host address to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5037, help="Port to listen on (default: 5037)")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to mock device configuration JSON/YAML file",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="[%(levelname)s] %(message)s")

    server = ADBServer(args.host, args.port, args.config)
    try:
        server.start()
        LOGGER.info("Mock ADB server ready. Press Ctrl+C to stop.")
        while True:
            threading.Event().wait(1)
    except KeyboardInterrupt:
        LOGGER.info("Shutting down due to interrupt")
    finally:
        server.stop()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
