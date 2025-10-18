"""Implementation of the `sync:` service for push/pull operations."""

from __future__ import annotations

import struct
from typing import Optional

from ..filesystem import FilesystemError
from .base import BaseStream


SYNC_HEADER = struct.Struct("<4sI")
SYNC_STAT = struct.Struct("<III")
SYNC_DENT = struct.Struct("<IIII")
CHUNK_SIZE = 64 * 1024


class SyncStream(BaseStream):
    """Handle the sync service used by `adb push` and `adb pull`."""

    def __init__(self, transport, local_id: int, remote_id: int, device) -> None:
        super().__init__(transport, local_id, remote_id)
        self.device = device
        self._buffer = bytearray()
        self._current_path: Optional[str] = None
        self._current_mode: int = 0o664
        self._current_data = bytearray()

    # ------------------------------------------------------------------
    @staticmethod
    def _with_type_bits(entry) -> int:
        mode = entry.permissions
        if entry.node_type == "dir":
            return mode | 0o040000
        if entry.node_type == "symlink":
            return mode | 0o120000
        return mode | 0o100000

    # ------------------------------------------------------------------
    def handle_client_data(self, data: bytes) -> None:
        self._buffer.extend(data)
        while len(self._buffer) >= SYNC_HEADER.size:
            cmd_bytes, length = SYNC_HEADER.unpack(self._buffer[:SYNC_HEADER.size])
            total = SYNC_HEADER.size + length
            if len(self._buffer) < total:
                return
            payload = bytes(self._buffer[SYNC_HEADER.size:total])
            del self._buffer[:total]
            command = cmd_bytes.decode("ascii")
            self._dispatch(command, payload)

    # ------------------------------------------------------------------
    def _dispatch(self, command: str, payload: bytes) -> None:
        if command == "STAT":
            self._handle_stat(payload)
        elif command == "SEND":
            self._handle_send(payload)
        elif command == "DATA":
            self._handle_data(payload)
        elif command == "DONE":
            self._handle_done(payload)
        elif command == "RECV":
            self._handle_recv(payload)
        elif command == "LIST":
            self._handle_list(payload)
        elif command == "QUIT":
            self.close()
        else:  # pragma: no cover - defensive
            self._send_fail(f"Unsupported sync command {command}")

    # ------------------------------------------------------------------
    def _handle_stat(self, payload: bytes) -> None:
        path = payload.decode("utf-8")
        try:
            entry = self.device.filesystem.get_entry(path)
            mode = self._with_type_bits(entry)
            size = len(entry.content) if entry.node_type == "file" else 0
        except FilesystemError:
            mode = 0
            size = 0
        response = SYNC_STAT.pack(mode, size, 0)
        self._send_chunk("STAT", response)

    def _handle_send(self, payload: bytes) -> None:
        spec = payload.decode("utf-8")
        if "," not in spec:
            self._send_fail("Malformed SEND request")
            return
        path, mode_text = spec.rsplit(",", 1)
        try:
            self._current_mode = int(mode_text, 8)
        except ValueError:
            self._current_mode = 0o664
        self._current_path = path
        self._current_data = bytearray()

    def _handle_data(self, payload: bytes) -> None:
        if not self._current_path:
            self._send_fail("DATA without SEND")
            return
        self._current_data.extend(payload)

    def _handle_done(self, payload: bytes) -> None:
        if not self._current_path:
            self._send_fail("DONE without SEND")
            return
        try:
            self.device.filesystem.write_file(
                self._current_path,
                bytes(self._current_data),
                mode=self._current_mode,
            )
            self._send_chunk("OKAY", b"")
        except FilesystemError as exc:
            self._send_fail(str(exc))
        finally:
            self._current_path = None
            self._current_data = bytearray()
            self._current_mode = 0o664

    def _handle_recv(self, payload: bytes) -> None:
        path = payload.decode("utf-8")
        try:
            data = self.device.filesystem.read_file(path)
        except FilesystemError as exc:
            self._send_fail(str(exc))
            return
        offset = 0
        while offset < len(data):
            chunk = data[offset: offset + CHUNK_SIZE]
            offset += len(chunk)
            self._send_chunk("DATA", chunk)
        self._send_chunk("DONE", b"")

    def _handle_list(self, payload: bytes) -> None:
        path = payload.decode("utf-8") or "/"
        try:
            entries = self.device.filesystem.list_dir(path)
        except FilesystemError as exc:
            self._send_fail(str(exc))
            return
        for entry in entries:
            name = entry.path.name or "/"
            mode = self._with_type_bits(entry)
            size = len(entry.content) if entry.node_type == "file" else 0
            dent = SYNC_DENT.pack(mode, size, 0, len(name)) + name.encode("utf-8")
            self._send_chunk("DENT", dent)
        self._send_chunk("DONE", b"")

    # ------------------------------------------------------------------
    def _send_chunk(self, command: str, payload: bytes) -> None:
        self.send(SYNC_HEADER.pack(command.encode("ascii"), len(payload)) + payload)

    def _send_fail(self, message: str) -> None:
        payload = message.encode("utf-8")
        self.send(SYNC_HEADER.pack(b"FAIL", len(payload)) + payload)
