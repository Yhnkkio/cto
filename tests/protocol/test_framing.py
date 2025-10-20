from __future__ import annotations

import pytest

from cto.protocol import (
    ADBPacket,
    A_OPEN,
    ADBChecksumError,
    ADBMagicError,
    ADBTruncatedError,
)


def test_roundtrip_encoding_decoding() -> None:
    payload = b"hello, adb"
    pkt = ADBPacket(command=A_OPEN, arg0=1, arg1=2, payload=payload)
    raw = pkt.to_bytes()
    parsed = ADBPacket.from_bytes(raw)
    assert parsed.command == A_OPEN
    assert parsed.arg0 == 1
    assert parsed.arg1 == 2
    assert parsed.payload == payload


def test_checksum_mismatch_raises() -> None:
    payload = b"data123"
    pkt = ADBPacket(command=A_OPEN, arg0=0, arg1=0, payload=payload)
    raw = bytearray(pkt.to_bytes())
    # Flip one byte in the payload to break checksum
    raw[-1] ^= 0xFF
    with pytest.raises(ADBChecksumError):
        ADBPacket.from_bytes(bytes(raw))


def test_magic_mismatch_raises() -> None:
    pkt = ADBPacket(command=A_OPEN, arg0=0, arg1=0, payload=b"")
    raw = bytearray(pkt.to_bytes())
    # Magic is last 4 bytes of header (offset 20..23). Corrupt it.
    raw[20:24] = b"\x00\x00\x00\x00"
    with pytest.raises(ADBMagicError):
        ADBPacket.from_bytes(bytes(raw))


def test_truncated_header_raises() -> None:
    with pytest.raises(ADBTruncatedError):
        ADBPacket.from_bytes(b"\x00\x01\x02")
