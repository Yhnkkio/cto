from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Tuple

from .protocol import ADBPacket


class Transport(ABC):
    @abstractmethod
    async def read_packet(self) -> ADBPacket:  # pragma: no cover - interface
        raise NotImplementedError

    @abstractmethod
    async def write_packet(self, pkt: ADBPacket) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class StreamTransport(Transport):
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._reader = reader
        self._writer = writer

    async def read_packet(self) -> ADBPacket:
        return await ADBPacket.read_from_stream(self._reader)

    async def write_packet(self, pkt: ADBPacket) -> None:
        self._writer.write(pkt.to_bytes())
        await self._writer.drain()

    async def close(self) -> None:
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except Exception:  # pragma: no cover - best effort
            pass
