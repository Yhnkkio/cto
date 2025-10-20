from __future__ import annotations

import asyncio
import enum
import io
import struct
import time
from dataclasses import dataclass
from typing import Optional

ADB_VERSION = 0x01000000
MAX_PAYLOAD = 4096


def _u32(x: int) -> int:
    return x & 0xFFFFFFFF


class Command(enum.IntEnum):
    CNXN = 0x4E584E43  # 'CNXN'
    OPEN = 0x4E45504F  # 'OPEN'
    OKAY = 0x59414B4F  # 'OKAY'
    CLSE = 0x45534C43  # 'CLSE'
    WRTE = 0x45545257  # 'WRTE'
    AUTH = 0x48545541  # 'AUTH'


@dataclass(slots=True)
class AdbPacket:
    cmd: int
    arg0: int
    arg1: int
    data: bytes

    def pack(self) -> bytes:
        data_len = len(self.data)
        checksum = _u32(sum(self.data))
        magic = _u32(self.cmd ^ 0xFFFFFFFF)
        header = struct.pack("<6I", self.cmd, self.arg0, self.arg1, data_len, checksum, magic)
        return header + self.data

    @staticmethod
    def unpack_from(buf: bytes) -> "AdbPacket":
        if len(buf) < 24:
            raise ValueError("buffer too small for adb header")
        cmd, arg0, arg1, data_len, checksum, magic = struct.unpack("<6I", buf[:24])
        if magic != _u32(cmd ^ 0xFFFFFFFF):
            raise ValueError("adb magic mismatch")
        data = buf[24:24 + data_len]
        if len(data) != data_len:
            raise ValueError("incomplete adb packet body")
        if _u32(sum(data)) != checksum:
            raise ValueError("adb checksum mismatch")
        return AdbPacket(cmd, arg0, arg1, data)


class AdbIO:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer

    async def read_packet(self) -> AdbPacket:
        header = await self.reader.readexactly(24)
        cmd, arg0, arg1, data_len, checksum, magic = struct.unpack("<6I", header)
        if magic != _u32(cmd ^ 0xFFFFFFFF):
            raise ValueError("adb magic mismatch")
        data = await self.reader.readexactly(data_len)
        if _u32(sum(data)) != checksum:
            raise ValueError("adb checksum mismatch")
        return AdbPacket(cmd, arg0, arg1, data)

    async def write_packet(self, pkt: AdbPacket) -> None:
        self.writer.write(pkt.pack())
        await self.writer.drain()


class Channel:
    def __init__(self, local_id: int, remote_id: int, service: str):
        self.local_id = local_id
        self.remote_id = remote_id
        self.service = service
        self.created_at = time.time()
        self.buffer = io.BytesIO()
        self.closed = False


class AdbConnection:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, banner: str):
        self.io = AdbIO(reader, writer)
        self.banner = banner.encode()
        self.max_payload = MAX_PAYLOAD
        self.channels: dict[int, Channel] = {}
        self._next_local_id = 1
        self.on_open = None  # set by consumer: callable(channel: Channel, initial_data: bytes) -> coroutine

    def allocate_local_id(self) -> int:
        lid = self._next_local_id
        self._next_local_id += 1
        return lid

    async def send(self, cmd: Command, arg0: int, arg1: int, data: bytes = b"") -> None:
        await self.io.write_packet(AdbPacket(int(cmd), arg0, arg1, data))

    async def handle(self):
        # Wait for host CNXN, then reply device CNXN
        first = await self.io.read_packet()
        if first.cmd == Command.AUTH:
            # ignore authentication; wait for CNXN
            first = await self.io.read_packet()
        if first.cmd != Command.CNXN:
            raise RuntimeError("expected CNXN from host")
        # Respond CNXN device banner
        await self.send(Command.CNXN, ADB_VERSION, self.max_payload, self.banner)

        # Main loop
        while True:
            pkt = await self.io.read_packet()
            cmd = Command(pkt.cmd)
            if cmd == Command.OPEN:
                service = pkt.data.rstrip(b"\x00").decode(errors="replace")
                remote_id = pkt.arg0
                local_id = self.allocate_local_id()
                ch = Channel(local_id, remote_id, service)
                self.channels[local_id] = ch
                # reply OKAY
                await self.send(Command.OKAY, local_id, remote_id)
                # service handler
                if self.on_open is not None:
                    asyncio.create_task(self.on_open(ch, b""))
            elif cmd == Command.OKAY:
                # ack for our WRTE; ignore for now
                pass
            elif cmd == Command.WRTE:
                # route to channel
                # ack immediately
                await self.send(Command.OKAY, pkt.arg1, pkt.arg0)
                # find channel
                ch = self.channels.get(pkt.arg1)
                if ch is not None and self.on_open is not None:
                    asyncio.create_task(self.on_open(ch, pkt.data))
            elif cmd == Command.CLSE:
                # close channel
                lid = pkt.arg1
                ch = self.channels.pop(lid, None)
                # ack close by mirroring CLSE
                await self.send(Command.CLSE, pkt.arg1, pkt.arg0)
                if ch:
                    ch.closed = True
            else:
                # ignore unknown
                pass

    async def wrte(self, ch: Channel, data: bytes) -> None:
        if ch.closed:
            return
        await self.send(Command.WRTE, ch.local_id, ch.remote_id, data)

    async def clse(self, ch: Channel) -> None:
        if ch.closed:
            return
        await self.send(Command.CLSE, ch.local_id, ch.remote_id)
        ch.closed = True
