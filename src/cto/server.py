from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


class ADBSimulatorServer:
    def __init__(self, host: str, port: int, logs_dir: Path) -> None:
        self._host = host
        self._port = port
        self._logs_dir = logs_dir
        self._server: Optional[asyncio.AbstractServer] = None

    async def start(self) -> None:
        self._logs_dir.mkdir(parents=True, exist_ok=True)
        loop = asyncio.get_running_loop()
        self._server = await asyncio.start_server(self._handle, host=self._host, port=self._port)
        sockets = ", ".join(
            f"{sock.getsockname()[0]}:{sock.getsockname()[1]}" for sock in self._server.sockets or []
        )
        log.info("ADB simulator listening on %s", sockets)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        log.debug("Client connected: %s", peer)
        from .transport import StreamTransport
        from .adb_session import ADBSession

        transport = StreamTransport(reader, writer)
        session = ADBSession(transport=transport)
        try:
            await session.run()
        except Exception:
            log.exception("Client handler error")
        finally:
            await transport.close()
            log.debug("Client disconnected: %s", peer)

    async def run_forever(self) -> None:
        if self._server is None:
            await self.start()
        assert self._server is not None
        try:
            await self._server.serve_forever()
        except asyncio.CancelledError:  # pragma: no cover - shutdown path
            pass

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        log.info("ADB simulator stopped")


async def run_server(host: str, port: int, logs_dir: Path) -> None:
    server = ADBSimulatorServer(host=host, port=port, logs_dir=logs_dir)
    await server.start()
    try:
        await server.run_forever()
    finally:
        await server.stop()
