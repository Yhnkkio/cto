from __future__ import annotations

import asyncio
import traceback
from pathlib import Path
from typing import Dict

from server.adb_protocol import AdbConnection, Channel, Command
from server.command_sim import CommandSim
from server.config import Config
from server.log import ConnLogger
from server.overlay_fs import OverlayFS
from server.props import Props
from server.shell.commands import Shell
from server.sync_service import SyncProtocol


class AdbDeviceSession:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, cfg: Config):
        self.reader = reader
        self.writer = writer
        self.cfg = cfg
        self.fs = OverlayFS(cfg.overlay_path)
        self.props = Props.load(Path("prop.json"))
        # Keep serial consistent
        if cfg.serial:
            self.props.set("ro.serialno", cfg.serial)
        self.sim = CommandSim(Path("command.json"))
        self.shell = Shell(self.fs, self.props)
        self.cwd: Dict[int, Path] = {}
        self.conn = AdbConnection(reader, writer, self.props.to_banner().decode())
        self.conn.on_open = self.on_open
        self.log = ConnLogger(writer.get_extra_info("peername")[0].replace(":", "_"))

    async def start(self) -> None:
        try:
            await self.conn.handle()
        except Exception as e:
            self.log.log("error", error=str(e), tb=traceback.format_exc())
        finally:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
            self.log.close()

    async def _handle_shell(self, ch: Channel, initial: str | None, data: bytes):
        if ch.local_id not in self.cwd:
            self.cwd[ch.local_id] = self.fs.get_root()
        cwd = self.cwd[ch.local_id]

        if initial is None or initial == "":
            # interactive; data may contain a first line
            await self.conn.wrte(ch, b"$ ")
            if data:
                await self._process_shell_input(ch, data)
            return
        else:
            # Non-interactive: run once and close
            resp = self.sim.match(str(cwd), initial)
            if resp is not None:
                if resp.stdout:
                    await self.conn.wrte(ch, resp.stdout)
                if resp.stderr:
                    await self.conn.wrte(ch, resp.stderr)
                await self.conn.clse(ch)
                return
            cwd, result = self.shell.run(cwd, initial)
            self.cwd[ch.local_id] = cwd
            if result.stdout:
                await self.conn.wrte(ch, result.stdout)
            if result.stderr:
                await self.conn.wrte(ch, result.stderr)
            await self.conn.clse(ch)

    async def _process_shell_input(self, ch: Channel, data: bytes):
        # Called for interactive input stream; commands separated by newlines.
        if ch.local_id not in self.cwd:
            self.cwd[ch.local_id] = self.fs.get_root()
        cwd = self.cwd[ch.local_id]
        lines = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n")
        for i, raw in enumerate(lines):
            if raw == b"":
                # empty line
                await self.conn.wrte(ch, b"\r\n$ ")
                continue
            if raw == b"\x04":
                # Ctrl+D: close
                await self.conn.clse(ch)
                return
            if raw == b"\x03":
                # Ctrl+C: cancel line
                await self.conn.wrte(ch, b"^C\r\n$ ")
                continue
            cmdline = raw.decode("utf-8", errors="ignore")
            resp = self.sim.match(str(cwd), cmdline)
            if resp is not None:
                if resp.stdout:
                    await self.conn.wrte(ch, resp.stdout)
                if resp.stderr:
                    await self.conn.wrte(ch, resp.stderr)
                await self.conn.wrte(ch, b"\r\n$ ")
                continue
            cwd, result = self.shell.run(cwd, cmdline)
            self.cwd[ch.local_id] = cwd
            if result.stdout:
                await self.conn.wrte(ch, result.stdout)
            if result.stderr:
                await self.conn.wrte(ch, result.stderr)
            await self.conn.wrte(ch, b"\r\n$ ")

    async def _handle_sync(self, ch: Channel, data: bytes):
        # The sync protocol is message-based over the ADB stream.
        if not hasattr(ch, "_sync"):
            ch._sync = SyncProtocol(self.fs, self.fs.get_root())  # type: ignore[attr-defined]
        sync: SyncProtocol = ch._sync  # type: ignore[attr-defined]
        buf = bytearray()
        if data:
            buf += data
        # In this simple implementation, we assume each WRTE will contain a whole message,
        # but we still parse length fields to support multiple messages batched together.
        while buf:
            if len(buf) < 8:
                break
            length = int.from_bytes(buf[4:8], "little")
            need = 8 + length
            if len(buf) < need:
                break
            chunk = bytes(buf[:need])
            del buf[:need]
            out = sync.handle(chunk)
            if out:
                await self.conn.wrte(ch, out)

    # The connection object calls on_open both on OPEN and WRTE. We need to dispatch WRTE for interactive shell and sync.
    async def on_open(self, ch: Channel, data: bytes):  # type: ignore[override]
        service = ch.service
        if service.startswith("shell:"):
            cmd = service[len("shell:") :]
            if hasattr(ch, "_shell_started"):
                # interactive input
                await self._process_shell_input(ch, data)
            else:
                ch._shell_started = True  # type: ignore[attr-defined]
                await self._handle_shell(ch, initial=cmd, data=data)
        elif service.startswith("exec:"):
            await self._handle_shell(ch, initial=service[len("exec:") :], data=data)
        elif service.startswith("sync:"):
            await self._handle_sync(ch, data)
        elif service.startswith("reboot"):
            await self.conn.wrte(ch, b"rebooting...\n")
            await self.conn.clse(ch)
        else:
            await self.conn.wrte(ch, f"unknown service: {service}\n".encode())
            await self.conn.clse(ch)


class AdbDeviceTCPServer:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._server: asyncio.base_events.Server | None = None

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        session = AdbDeviceSession(reader, writer, self.cfg)
        await session.start()

    async def start(self):
        self._server = await asyncio.start_server(self._client, host="0.0.0.0", port=self.cfg.device_port)
        sockets = ", ".join(str(s.getsockname()) for s in self._server.sockets or [])
        print(f"ADB device server listening on {sockets} (serial {self.cfg.serial})")
        async with self._server:
            await self._server.serve_forever()
