from __future__ import annotations

import os
import struct
from pathlib import Path
from typing import Iterable

from server.overlay_fs import OverlayFS


# SYNC IDs
ID_STAT = b"STAT"
ID_LIST = b"LIST"
ID_RECV = b"RECV"
ID_SEND = b"SEND"
ID_DENT = b"DENT"
ID_DONE = b"DONE"
ID_DATA = b"DATA"
ID_OKAY = b"OKAY"
ID_FAIL = b"FAIL"


class SyncProtocol:
    def __init__(self, fs: OverlayFS, cwd: Path):
        self.fs = fs
        self.cwd = cwd

    def _pack(self, ident: bytes, payload: bytes = b"") -> bytes:
        return ident + struct.pack("<I", len(payload)) + payload

    def _pack_stat(self, path: Path) -> bytes:
        try:
            st = self.fs.stat(path)
            mode = st.mode
            size = st.size
            mtime = st.mtime
        except Exception:
            mode = 0
            size = 0
            mtime = 0
        payload = struct.pack("<III", mode, size, mtime)
        return self._pack(ID_STAT, payload)

    def _iter_list(self, path: Path) -> Iterable[bytes]:
        try:
            for name, st in self.fs.list_entries(path):
                # mode, size, mtime, name
                payload = struct.pack("<III", st.mode, st.size, st.mtime) + name.encode("utf-8")
                yield self._pack(ID_DENT, payload)
        except FileNotFoundError:
            pass
        yield self._pack(ID_DONE)

    def handle(self, data: bytes) -> bytes:
        # Process a complete request message, return response bytes (may be multiple frames)
        # Some requests stream, so caller should keep state between calls if needed.
        if len(data) < 8:
            return self._pack(ID_FAIL, b"bad request")
        ident = data[:4]
        length = struct.unpack("<I", data[4:8])[0]
        payload = data[8:8 + length]
        if ident == ID_STAT:
            path = payload.decode("utf-8")
            p = self.fs.resolve(self.cwd, path)
            return self._pack_stat(p)
        elif ident == ID_LIST:
            path = payload.decode("utf-8")
            p = self.fs.resolve(self.cwd, path)
            out = bytearray()
            for chunk in self._iter_list(p):
                out += chunk
            return bytes(out)
        elif ident == ID_RECV:
            path = payload.decode("utf-8")
            p = self.fs.resolve(self.cwd, path)
            if not p.exists() or p.is_dir():
                return self._pack(ID_FAIL, b"No such file or directory")
            out = bytearray()
            with open(p, "rb") as f:
                while True:
                    b = f.read(64 * 1024)
                    if not b:
                        break
                    out += self._pack(ID_DATA, b)
            out += self._pack(ID_DONE)
            return bytes(out)
        elif ident == ID_SEND:
            # payload is path,0xXXXX mode
            try:
                path, mode_s = payload.decode("utf-8").rsplit(",", 1)
                mode = int(mode_s)
            except Exception:
                return self._pack(ID_FAIL, b"bad send header")
            self._send_path = self.fs.resolve(self.cwd, path)
            self._send_fp = open(self._send_path, "wb")
            self._send_mtime = None
            return b""
        elif ident == ID_DATA:
            # Append to last SEND
            if not hasattr(self, "_send_fp"):
                return self._pack(ID_FAIL, b"DATA without SEND")
            self._send_fp.write(payload)
            return b""
        elif ident == ID_DONE:
            # Finalize SEND
            if not hasattr(self, "_send_fp"):
                return self._pack(ID_FAIL, b"DONE without SEND")
            # payload is mtime
            if len(payload) >= 4:
                mtime = struct.unpack("<I", payload[:4])[0]
                try:
                    self._send_fp.flush()
                    self._send_fp.close()
                finally:
                    del self._send_fp
                self.fs.set_mtime(self._send_path, int(mtime))
            return self._pack(ID_OKAY)
        else:
            return self._pack(ID_FAIL, b"unknown request")
