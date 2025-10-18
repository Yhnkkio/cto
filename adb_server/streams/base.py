"""Base classes shared by stream implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from ..transport import ADBTransportSession


class StreamClosed(Exception):
    """Raised when operations occur on a closed stream."""


class BaseStream:
    """Common functionality for all service streams."""

    def __init__(self, transport: "ADBTransportSession", local_id: int, remote_id: int) -> None:
        self.transport = transport
        self.local_id = local_id
        self.remote_id = remote_id
        self.closed = False

    def start(self) -> None:
        """Called once the stream has been registered."""

    def handle_client_data(self, data: bytes) -> None:
        """Process data coming from the adb client."""

    def handle_close(self) -> None:
        """Called when the client closes the stream."""
        self.closed = True

    def send(self, data: bytes) -> None:
        if self.closed:
            raise StreamClosed("Stream is closed")
        self.transport.send_stream_data(self, data)

    def close(self) -> None:
        if not self.closed:
            self.handle_close()
            self.transport.close_stream(self)
            self.closed = True
