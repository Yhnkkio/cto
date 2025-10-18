"""Utilities for encoding and decoding messages that conform to the simplified
ADB protocol used by :class:`adb_server.server.ADBServer`.

The protocol uses a 4-byte, little-endian length prefix followed by a UTF-8
encoded JSON payload. Each JSON payload must be an object (dictionary).
"""

from __future__ import annotations

import json
import socket
import struct
from typing import Any, Dict, Optional

from .exceptions import ConnectionClosed, ProtocolError

LENGTH_PREFIX_FORMAT = "<I"
LENGTH_PREFIX_SIZE = struct.calcsize(LENGTH_PREFIX_FORMAT)
# Prevent unbounded allocations – 16 MiB is more than sufficient for typical
# ADB payloads such as shell output or reasonably sized file chunks.
MAX_MESSAGE_SIZE = 16 * 1024 * 1024


def encode_message(payload: Dict[str, Any]) -> bytes:
    """Serialise *payload* into the wire format expected by the ADB server."""

    try:
        raw_payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive guard
        raise ProtocolError(f"Unable to serialise payload to JSON: {exc}") from exc

    length = len(raw_payload)
    if length > MAX_MESSAGE_SIZE:
        raise ProtocolError(
            f"Payload exceeds maximum allowed size of {MAX_MESSAGE_SIZE} bytes"
        )

    return struct.pack(LENGTH_PREFIX_FORMAT, length) + raw_payload


def send_message(sock: socket.socket, payload: Dict[str, Any]) -> None:
    """Send *payload* over *sock* using the protocol."""

    sock.sendall(encode_message(payload))


def receive_message(sock: socket.socket) -> Dict[str, Any]:
    """Read the next message from *sock*.

    Raises :class:`ConnectionClosed` when the peer closes the connection and
    :class:`ProtocolError` when the payload is invalid.
    """

    length_bytes = _read_exact(sock, LENGTH_PREFIX_SIZE)
    if length_bytes is None:
        raise ConnectionClosed("connection closed during length prefix read")

    (payload_length,) = struct.unpack(LENGTH_PREFIX_FORMAT, length_bytes)
    if payload_length > MAX_MESSAGE_SIZE:
        raise ProtocolError(
            f"Advertised payload size {payload_length} exceeds maximum of {MAX_MESSAGE_SIZE}"
        )

    raw_payload = _read_exact(sock, payload_length)
    if raw_payload is None:
        raise ConnectionClosed("connection closed while reading payload")

    try:
        message = json.loads(raw_payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"Received malformed JSON payload: {exc}") from exc

    if not isinstance(message, dict):
        raise ProtocolError("ADB messages must encode JSON objects")

    return message


def _read_exact(sock: socket.socket, size: int) -> Optional[bytes]:
    """Read exactly *size* bytes from *sock*.

    Returns ``None`` if the peer closes the connection before enough bytes were
    read. Any other socket errors are allowed to propagate so callers can
    differentiate between fatal and temporary conditions.
    """

    chunks = bytearray()
    remaining = size

    while remaining > 0:
        try:
            chunk = sock.recv(remaining)
        except socket.timeout:
            continue
        if not chunk:  # Connection closed by peer
            return None
        chunks.extend(chunk)
        remaining -= len(chunk)

    return bytes(chunks)


__all__ = [
    "encode_message",
    "receive_message",
    "send_message",
    "MAX_MESSAGE_SIZE",
]
