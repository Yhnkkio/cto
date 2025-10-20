from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import ClassVar, Optional

# ADB protocol constants (commands encoded as little-endian 32-bit ASCII)


def _cmd(code: str) -> int:
    if len(code) != 4:
        raise ValueError("command must be 4 chars")
    # Interpret as 4 ASCII bytes in little-endian uint32
    b = code.encode("ascii")
    return struct.unpack("<I", b)[0]


A_SYNC = _cmd("SYNC")
A_CNXN = _cmd("CNXN")
A_OPEN = _cmd("OPEN")
A_OKAY = _cmd("OKAY")
A_CLSE = _cmd("CLSE")
A_WRTE = _cmd("WRTE")
A_AUTH = _cmd("AUTH")

# AUTH constants (arg0)
A_AUTH_TOKEN = 1
A_AUTH_SIGNATURE = 2
A_AUTH_RSAPUBLICKEY = 3

# Protocol version we speak
ADB_PROTOCOL_VERSION = 0x01000001
# Default max payload we advertise
ADB_MAX_PAYLOAD = 4096


class ADBProtocolError(Exception):
    pass


class ADBChecksumError(ADBProtocolError):
    pass


class ADBMagicError(ADBProtocolError):
    pass


class ADBTruncatedError(ADBProtocolError):
    pass


@dataclass(slots=True)
class ADBPacket:
    command: int
    arg0: int
    arg1: int
    payload: bytes = b""

    # Header is 6 little-endian uint32 fields
    _HEADER_STRUCT: ClassVar[struct.Struct] = struct.Struct("<IIIIII")

    @staticmethod
    def checksum(data: bytes) -> int:
        return sum(data) & 0xFFFFFFFF

    @property
    def magic(self) -> int:
        return self.command ^ 0xFFFFFFFF

    def to_bytes(self) -> bytes:
        data_length = len(self.payload)
        data_checksum = self.checksum(self.payload)
        header = self._HEADER_STRUCT.pack(
            self.command,
            self.arg0,
            self.arg1,
            data_length,
            data_checksum,
            self.magic,
        )
        return header + self.payload

    @classmethod
    def from_bytes(cls, raw: bytes) -> "ADBPacket":
        if len(raw) < cls._HEADER_STRUCT.size:
            raise ADBTruncatedError("incomplete header")
        (
            command,
            arg0,
            arg1,
            data_length,
            data_checksum,
            magic,
        ) = cls._HEADER_STRUCT.unpack_from(raw, 0)
        if magic != (command ^ 0xFFFFFFFF):
            raise ADBMagicError("invalid magic")
        if len(raw) != cls._HEADER_STRUCT.size + data_length:
            raise ADBTruncatedError("payload length mismatch")
        payload = raw[cls._HEADER_STRUCT.size : cls._HEADER_STRUCT.size + data_length]
        if cls.checksum(payload) != data_checksum:
            raise ADBChecksumError("checksum mismatch")
        return cls(command=command, arg0=arg0, arg1=arg1, payload=bytes(payload))

    @classmethod
    async def read_from_stream(cls, reader) -> "ADBPacket":
        # reader: asyncio.StreamReader-like with readexactly
        header = await reader.readexactly(cls._HEADER_STRUCT.size)
        (
            command,
            arg0,
            arg1,
            data_length,
            data_checksum,
            magic,
        ) = cls._HEADER_STRUCT.unpack(header)
        if magic != (command ^ 0xFFFFFFFF):
            raise ADBMagicError("invalid magic")
        payload = b""
        if data_length:
            payload = await reader.readexactly(data_length)
        if cls.checksum(payload) != data_checksum:
            raise ADBChecksumError("checksum mismatch")
        return cls(command=command, arg0=arg0, arg1=arg1, payload=payload)

    def is_command(self, name: str) -> bool:
        try:
            return self.command == _cmd(name)
        except Exception:
            return False


def parse_cnxn_payload(data: bytes) -> str:
    # CNXN payload is a null-terminated string
    # e.g., b"host::features=\x00..." but null-terminator may be omitted by some clients
    s = data.rstrip(b"\x00").decode("utf-8", errors="replace")
    return s


def build_cnxn_payload(kind: str, banner: str, features: list[str]) -> bytes:
    # kind is typically "device"; banner contains properties like ro.serialno
    # Payload format: f"{kind}::{banner}\x00" where banner includes keys and features=
    feat = ",".join(sorted(set(features))) if features else ""
    parts = [banner]
    if feat:
        parts.append(f"features={feat}")
    payload = f"{kind}::" + ";".join(parts)
    return payload.encode("utf-8")


def features_from_payload(payload: str) -> set[str]:
    # payload like "host::features=cmd,shell_v2,ls_v2"
    if "features=" not in payload:
        return set()
    after = payload.split("features=", 1)[1]
    # Can be followed by other props delimited by ';'
    for sep in [";", "\x00"]:
        if sep in after:
            after = after.split(sep, 1)[0]
            break
    return set(x for x in after.split(",") if x)
