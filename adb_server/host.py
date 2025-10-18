"""Implementation of the host <-> adb client text protocol."""

from __future__ import annotations

import logging
import socket
from typing import Optional

from .mock_device import MockDevice
from .transport import ADBTransportSession

LOGGER = logging.getLogger(__name__)


class HostProtocolError(RuntimeError):
    """Raised when an invalid host request is received."""


class ADBHostSession:
    """Handle the text-based host protocol prior to entering transport mode."""

    def __init__(self, conn: socket.socket, device: MockDevice) -> None:
        self.conn = conn
        self.device = device
        self.transport_started = False
        self.alive = True

    # ------------------------------------------------------------------
    def run(self) -> None:
        while self.alive and not self.transport_started:
            request = self._read_request()
            if request is None:
                return
            LOGGER.debug("Host request: %s", request)
            try:
                self._handle_request(request)
            except HostProtocolError as exc:
                LOGGER.error("Host command failed: %s", exc)
                self._send_fail(str(exc))
        if self.transport_started and self.alive:
            LOGGER.debug("Switching to transport mode")
            transport = ADBTransportSession(self.conn, self.device)
            transport.run()

    # ------------------------------------------------------------------
    def _read_request(self) -> Optional[str]:
        length_bytes = self._read_exact(4)
        if not length_bytes:
            return None
        try:
            length = int(length_bytes.decode("ascii"), 16)
        except ValueError:
            raise HostProtocolError("Invalid request length header")
        payload = self._read_exact(length)
        if payload is None:
            return None
        return payload.decode("utf-8")

    def _read_exact(self, size: int) -> Optional[bytes]:
        data = bytearray()
        while len(data) < size:
            chunk = self.conn.recv(size - len(data))
            if not chunk:
                return None
            data.extend(chunk)
        return bytes(data)

    # ------------------------------------------------------------------
    def _handle_request(self, request: str) -> None:
        if request.startswith("host-serial:"):
            serial_part, _, rest = request.partition(":")
            _, _, serial = serial_part.partition(":")
            if serial != self.device.get_serial():
                raise HostProtocolError(f"Unknown serial {serial}")
            self._handle_host_command(rest)
            return
        if request.startswith("host:"):
            command = request[5:]
            self._handle_host_command(command)
            return
        raise HostProtocolError(f"Unsupported request: {request}")

    def _handle_host_command(self, command: str) -> None:
        if command == "version":
            self._send_okay("001f")
            return
        if command in {"transport-any", "transport", "transport-usb", "transport-local"}:
            self._send_okay()
            self.transport_started = True
            return
        if command.startswith("get-state"):
            state = self.device.get_state()
            self._send_okay(state)
            return
        if command.startswith("get-serialno"):
            serial = self.device.get_serial()
            self._send_okay(serial)
            return
        if command.startswith("devices-l"):
            info = self.device.metadata
            line = f"{info.serial}\tdevice product:{info.model} model:{info.model} device:{info.model.lower()}"
            self._send_okay(line + "\n")
            return
        if command.startswith("devices"):
            self._send_okay(f"{self.device.get_serial()}\tdevice\n")
            return
        if command.startswith("forward:"):
            subcommand = command[len("forward:"):]
            if subcommand == "list-forward":
                rules = self.device.list_forward_rules()
                payload = "\n".join(f"{k} {v}" for k, v in rules.items()) + ("\n" if rules else "")
                self._send_okay(payload)
            else:
                self._handle_forward(subcommand)
            return
        if command.startswith("forward-remove:"):
            target = command[len("forward-remove:"):]
            removed = self.device.remove_forward_rule(target)
            if not removed:
                self._send_fail("forward-remove: not found")
                return
            self._send_okay()
            return
        if command == "list-forward":
            rules = self.device.list_forward_rules()
            payload = "\n".join(f"{k} {v}" for k, v in rules.items()) + ("\n" if rules else "")
            self._send_okay(payload)
            return
        if command.startswith("reboot"):
            self._send_okay()
            self.device.reboot()
            return
        if command == "features":
            self._send_okay("")
            return
        if command == "kill":
            self._send_okay()
            self.alive = False
            return
        raise HostProtocolError(f"Unsupported host command: {command}")

    def _handle_forward(self, spec: str) -> None:
        if spec.startswith("norebind:"):
            spec = spec[len("norebind:") :]
        if ";" not in spec:
            raise HostProtocolError("Malformed forward spec")
        local, remote = spec.split(";", 1)
        self.device.add_forward_rule(local, remote)
        self._send_okay()

    # ------------------------------------------------------------------
    def _send_okay(self, payload: str | bytes = b"") -> None:
        if isinstance(payload, str):
            payload_bytes = payload.encode("utf-8")
        else:
            payload_bytes = payload
        length = f"{len(payload_bytes):04x}".encode("ascii")
        self.conn.sendall(b"OKAY" + length + payload_bytes)

    def _send_fail(self, message: str) -> None:
        payload = message.encode("utf-8")
        length = f"{len(payload):04x}".encode("ascii")
        self.conn.sendall(b"FAIL" + length + payload)
