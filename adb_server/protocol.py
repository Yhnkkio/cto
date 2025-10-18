"""ADB protocol primitives used by the server implementation."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import ClassVar


# ADB command constants -------------------------------------------------------
COMMANDS = {
    "SYNC": 0x434e5953,
    "CNXN": 0x4e584e43,
    "AUTH": 0x48545541,
    "OPEN": 0x4e45504f,
    "OKAY": 0x59414b4f,
    "CLSE": 0x45534c43,
    "WRTE": 0x45545257,
}

REVERSE_COMMANDS = {value: key for key, value in COMMANDS.items()}

MAX_PAYLOAD = 1024 * 1024  # 1 MiB safety bound
HEADER_FORMAT = "<IIIIII"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


def checksum(data: bytes) -> int:
    """Return the classic adb checksum (sum of bytes mod 2^32)."""

    return sum(data) & 0xFFFFFFFF


@dataclass
class ADBPacket:
    command: int
    arg0: int
    arg1: int
    payload: bytes = b""

    HEADER_SIZE: ClassVar[int] = HEADER_SIZE

    @property
    def length(self) -> int:
        return len(self.payload)

    @property
    def magic(self) -> int:
        return self.command ^ 0xFFFFFFFF

    def pack(self) -> bytes:
        body = self.payload
        if len(body) > MAX_PAYLOAD:
            raise ValueError("Payload too large")
        header = struct.pack(
            HEADER_FORMAT,
            self.command,
            self.arg0,
            self.arg1,
            len(body),
            checksum(body),
            self.magic,
        )
        return header + body

    @classmethod
    def unpack(cls, data: bytes) -> "ADBPacket":
        if len(data) < HEADER_SIZE:
            raise ValueError("Not enough data for an ADB packet header")
        command, arg0, arg1, length, expected_checksum, magic = struct.unpack(
            HEADER_FORMAT, data[:HEADER_SIZE]
        )
        if command ^ 0xFFFFFFFF != magic:
            raise ValueError("Invalid ADB packet magic")
        payload = data[HEADER_SIZE:HEADER_SIZE + length]
        if len(payload) != length:
            raise ValueError("Payload length mismatch")
        if checksum(payload) != expected_checksum:
            raise ValueError("ADB payload checksum mismatch")
        return cls(command=command, arg0=arg0, arg1=arg1, payload=payload)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        cmd = REVERSE_COMMANDS.get(self.command, hex(self.command))
        return f"ADBPacket({cmd}, arg0={self.arg0}, arg1={self.arg1}, length={self.length})"
