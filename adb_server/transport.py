"""Binary ADB transport protocol implementation."""

from __future__ import annotations

import logging
import socket
from typing import Dict, Optional

from .mock_device import MockDevice
from .protocol import COMMANDS, ADBPacket, HEADER_SIZE, REVERSE_COMMANDS
from .shell import ShellEnvironment
from .streams import LogcatStream, ShellStream, SyncStream

LOGGER = logging.getLogger(__name__)


class ADBTransportSession:
    """Manage a binary transport session with an adb client."""

    def __init__(self, conn: socket.socket, device: MockDevice) -> None:
        self.conn = conn
        self.device = device
        self.max_payload = 4096
        self.streams_by_local: Dict[int, object] = {}
        self.streams_by_remote: Dict[int, object] = {}
        self.next_remote_id = 1
        self.active = True

    # ------------------------------------------------------------------
    def run(self) -> None:
        while self.active:
            packet = self._read_packet()
            if packet is None:
                break
            command_name = REVERSE_COMMANDS.get(packet.command, hex(packet.command))
            LOGGER.debug("Transport packet: %s", command_name)
            if packet.command == COMMANDS["CNXN"]:
                self._handle_cnxn(packet)
            elif packet.command == COMMANDS["OPEN"]:
                self._handle_open(packet)
            elif packet.command == COMMANDS["WRTE"]:
                self._handle_write(packet)
            elif packet.command == COMMANDS["CLSE"]:
                self._handle_close(packet)
            elif packet.command == COMMANDS["OKAY"]:
                self._handle_okay(packet)
            elif packet.command == COMMANDS["AUTH"]:
                self._handle_auth(packet)
            else:
                LOGGER.warning("Unsupported transport command: %s", command_name)

    # ------------------------------------------------------------------
    def _read_packet(self) -> Optional[ADBPacket]:
        header = self._read_exact(HEADER_SIZE)
        if not header:
            return None
        length = int.from_bytes(header[12:16], "little")
        payload = self._read_exact(length)
        if payload is None:
            return None
        return ADBPacket.unpack(header + payload)

    def _read_exact(self, size: int) -> Optional[bytes]:
        data = bytearray()
        while len(data) < size:
            chunk = self.conn.recv(size - len(data))
            if not chunk:
                return None
            data.extend(chunk)
        return bytes(data)

    # ------------------------------------------------------------------
    def _handle_cnxn(self, packet: ADBPacket) -> None:
        self.max_payload = min(packet.arg1, 256 * 1024)
        features = ""
        banner = f"{self.device.get_device_banner()};features={features}\0"
        response = ADBPacket(
            command=COMMANDS["CNXN"],
            arg0=packet.arg0,
            arg1=self.max_payload,
            payload=banner.encode("utf-8"),
        )
        self._send_packet(response)

    def _handle_auth(self, packet: ADBPacket) -> None:
        # For simplicity, bypass authentication by acknowledging with CNXN.
        LOGGER.debug("AUTH packet received; responding with CNXN bypass")
        features = ""
        banner = f"{self.device.get_device_banner()};features={features}\0"
        response = ADBPacket(
            command=COMMANDS["CNXN"],
            arg0=packet.arg0,
            arg1=self.max_payload,
            payload=banner.encode("utf-8"),
        )
        self._send_packet(response)

    def _handle_open(self, packet: ADBPacket) -> None:
        service = packet.payload.rstrip(b"\x00").decode("utf-8")
        local_id = packet.arg0
        remote_id = self._allocate_remote_id()
        stream = self._create_stream(service, local_id, remote_id)
        if stream is None:
            LOGGER.warning("Unsupported service requested: %s", service)
            self._send_packet(ADBPacket(COMMANDS["CLSE"], remote_id, local_id, b""))
            return
        self.streams_by_local[local_id] = stream
        self.streams_by_remote[remote_id] = stream
        self._send_packet(ADBPacket(COMMANDS["OKAY"], remote_id, local_id, b""))
        stream.start()

    def _handle_write(self, packet: ADBPacket) -> None:
        stream = self.streams_by_local.get(packet.arg0)
        if not stream:
            LOGGER.warning("WRTE for unknown local id %s", packet.arg0)
            return
        # Acknowledge receipt before processing to mimic adb behaviour.
        self._send_packet(ADBPacket(COMMANDS["OKAY"], stream.remote_id, stream.local_id, b""))
        stream.handle_client_data(packet.payload)

    def _handle_close(self, packet: ADBPacket) -> None:
        stream = self.streams_by_local.pop(packet.arg0, None)
        if not stream:
            return
        self.streams_by_remote.pop(stream.remote_id, None)
        stream.handle_close()
        self._send_packet(ADBPacket(COMMANDS["CLSE"], stream.remote_id, stream.local_id, b""))

    def _handle_okay(self, packet: ADBPacket) -> None:
        # OKAY acknowledgements from the client are currently ignored.
        return

    def _create_stream(self, service: str, local_id: int, remote_id: int):
        if service.startswith("shell:"):
            command = service[len("shell:"):]
            if command:
                shell = ShellEnvironment(self.device)
                return ShellStream(self, local_id, remote_id, shell, command, interactive=False)
            shell = ShellEnvironment(self.device)
            return ShellStream(self, local_id, remote_id, shell, interactive=True)
        if service.startswith("exec:"):
            command = service[len("exec:"):]
            shell = ShellEnvironment(self.device)
            return ShellStream(self, local_id, remote_id, shell, command, interactive=False)
        if service.startswith("sync:"):
            return SyncStream(self, local_id, remote_id, self.device)
        if service.startswith("logcat"):
            return LogcatStream(self, local_id, remote_id, self.device)
        return None

    def _allocate_remote_id(self) -> int:
        remote_id = self.next_remote_id
        self.next_remote_id += 1
        return remote_id

    # ------------------------------------------------------------------
    def send_stream_data(self, stream, data: bytes) -> None:
        if stream.remote_id not in self.streams_by_remote:
            return
        packets = [data[i: i + self.max_payload] for i in range(0, len(data), self.max_payload)]
        for chunk in packets:
            packet = ADBPacket(COMMANDS["WRTE"], stream.remote_id, stream.local_id, chunk)
            self._send_packet(packet)

    def close_stream(self, stream) -> None:
        if stream.remote_id in self.streams_by_remote:
            self.streams_by_remote.pop(stream.remote_id, None)
        self.streams_by_local.pop(stream.local_id, None)
        packet = ADBPacket(COMMANDS["CLSE"], stream.remote_id, stream.local_id, b"")
        self._send_packet(packet)

    def _send_packet(self, packet: ADBPacket) -> None:
        try:
            self.conn.sendall(packet.pack())
        except BrokenPipeError:
            self.active = False
