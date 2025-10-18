"""Custom exception types for the lightweight ADB protocol server implementation."""

from __future__ import annotations


class ADBServerError(Exception):
    """Base class for all server-related exceptions."""


class ProtocolError(ADBServerError):
    """Raised when an inbound message violates the protocol."""


class ConnectionClosed(ADBServerError):
    """Raised when the remote peer closes the connection unexpectedly."""


class HandshakeError(ADBServerError):
    """Raised when the initial client handshake cannot be completed."""


class ShellCommandError(ADBServerError):
    """Raised when a shell command cannot be executed successfully."""


class FileTransferError(ADBServerError):
    """Raised when push or pull file transfer operations fail."""


class ForwardingError(ADBServerError):
    """Raised when port forwarding cannot be established or maintained."""
