"""Implementation of a simplified, multi-client ADB protocol server."""

from __future__ import annotations

import base64
import logging
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple, Union

from .exceptions import (
    ConnectionClosed,
    FileTransferError,
    ForwardingError,
    HandshakeError,
    ProtocolError,
    ShellCommandError,
)
from .protocol import receive_message, send_message

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5037


class PortForwarder:
    """Simple TCP port forwarder used by :class:`ADBServer`."""

    def __init__(
        self,
        local_host: str,
        local_port: int,
        remote_host: str,
        remote_port: int,
        logger: logging.Logger,
    ) -> None:
        self.local_host = local_host
        self.local_port = local_port
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.logger = logger.getChild(
            f"forward[{local_host}:{local_port}->{remote_host}:{remote_port}]"
        )

        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._serve,
            name=f"ADBForward-{local_host}:{local_port}",
            daemon=True,
        )
        self._listener: Optional[socket.socket] = None

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass
        self._thread.join(timeout=2.0)

    def _serve(self) -> None:
        try:
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((self.local_host, self.local_port))
            listener.listen()
            listener.settimeout(1.0)
            self._listener = listener
            self.logger.info(
                "Forwarder listening on %s:%d", self.local_host, self.local_port
            )

            while not self._stop_event.is_set():
                try:
                    client_sock, client_addr = listener.accept()
                except socket.timeout:
                    continue
                except OSError as exc:
                    if self._stop_event.is_set():
                        break
                    self.logger.error("Forwarder accept failed: %s", exc)
                    continue

                handler = threading.Thread(
                    target=self._handle_connection,
                    args=(client_sock, client_addr),
                    name=f"ADBForwardPipe-{client_addr[0]}:{client_addr[1]}",
                    daemon=True,
                )
                handler.start()
        except OSError as exc:
            self.logger.error("Forwarder encountered fatal error: %s", exc)
        finally:
            if self._listener is not None:
                try:
                    self._listener.close()
                except OSError:
                    pass
                self._listener = None
            self.logger.info(
                "Forwarder on %s:%d stopped", self.local_host, self.local_port
            )

    def _handle_connection(
        self, client_sock: socket.socket, client_addr: Tuple[str, int]
    ) -> None:
        try:
            remote_sock = socket.create_connection(
                (self.remote_host, self.remote_port), timeout=5
            )
        except OSError as exc:
            self.logger.error(
                "Unable to connect to remote %s:%d for client %s:%d: %s",
                self.remote_host,
                self.remote_port,
                client_addr[0],
                client_addr[1],
                exc,
            )
            client_sock.close()
            return

        client_sock.settimeout(1.0)
        remote_sock.settimeout(1.0)

        self.logger.debug(
            "Forwarding connection %s:%d <-> %s:%d",
            client_addr[0],
            client_addr[1],
            self.remote_host,
            self.remote_port,
        )

        threads = [
            threading.Thread(
                target=self._pipe,
                args=(client_sock, remote_sock),
                daemon=True,
            ),
            threading.Thread(
                target=self._pipe,
                args=(remote_sock, client_sock),
                daemon=True,
            ),
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        for sock in (client_sock, remote_sock):
            try:
                sock.close()
            except OSError:
                pass

        self.logger.debug(
            "Connection %s:%d closed", client_addr[0], client_addr[1]
        )

    def _pipe(self, source: socket.socket, destination: socket.socket) -> None:
        while not self._stop_event.is_set():
            try:
                data = source.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break

            if not data:
                break

            try:
                destination.sendall(data)
            except OSError:
                break


class ADBServer:
    """Simplified ADB server implementation supporting multiple clients."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        storage_dir: Optional[Union[Path, str]] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.logger = logger or logging.getLogger("adb_server")
        self.storage_dir = self._normalise_storage_dir(storage_dir)

        self._server_socket: Optional[socket.socket] = None
        self._accept_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._clients: set["ADBClientSession"] = set()
        self._clients_lock = threading.Lock()

        self._forwardings: Dict[Tuple[str, int], PortForwarder] = {}
        self._forward_lock = threading.Lock()

        self.logger.debug(
            "ADBServer initialised (host=%s, port=%s, storage_dir=%s)",
            host,
            port,
            self.storage_dir,
        )

    # ------------------------------------------------------------------
    # Lifecycle management
    # ------------------------------------------------------------------
    @property
    def is_running(self) -> bool:
        return self._accept_thread is not None and self._accept_thread.is_alive()

    def start(self, backlog: int = 16) -> None:
        if self.is_running:
            raise RuntimeError("ADBServer is already running")

        self.storage_dir.mkdir(parents=True, exist_ok=True)

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((self.host, self.port))
        actual_host, actual_port = server_socket.getsockname()
        if self.host in ("0.0.0.0", "::", "0", ""):
            self.host = actual_host
        self.port = actual_port
        server_socket.listen(backlog)
        server_socket.settimeout(1.0)

        self._server_socket = server_socket
        self._stop_event.clear()

        self._accept_thread = threading.Thread(
            target=self._accept_loop,
            name="ADBServer.accept",
            daemon=True,
        )
        self._accept_thread.start()

        self.logger.info("ADB server listening on %s:%d", self.host, self.port)

    def serve_forever(self) -> None:
        self.start()
        try:
            while self.is_running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            self.logger.info("Interrupted by user, stopping ADB server")
        finally:
            self.stop()

    def stop(self) -> None:
        self._stop_event.set()

        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except OSError:
                pass
            self._server_socket = None

        if self._accept_thread is not None:
            self._accept_thread.join(timeout=2.0)
            self._accept_thread = None

        with self._clients_lock:
            clients = list(self._clients)
        for client in clients:
            client.stop()
        for client in clients:
            client.join(timeout=2.0)

        with self._forward_lock:
            forwarders = list(self._forwardings.values())
            self._forwardings.clear()
        for forwarder in forwarders:
            forwarder.stop()

        self.logger.info("ADB server stopped")

    # ------------------------------------------------------------------
    # Client management helpers
    # ------------------------------------------------------------------
    def _accept_loop(self) -> None:
        assert self._server_socket is not None

        while not self._stop_event.is_set():
            try:
                client_socket, client_addr = self._server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                if self._stop_event.is_set():
                    break
                raise

            session = ADBClientSession(self, client_socket, client_addr)

            with self._clients_lock:
                self._clients.add(session)

            session.start()

        # Ensure server socket closed when loop exits
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except OSError:
                pass
            self._server_socket = None

    def _unregister_client(self, session: "ADBClientSession") -> None:
        with self._clients_lock:
            self._clients.discard(session)

    # ------------------------------------------------------------------
    # Port forwarding management
    # ------------------------------------------------------------------
    def add_forward(
        self,
        *,
        local_host: str,
        local_port: int,
        remote_host: str,
        remote_port: int,
    ) -> None:
        key = (local_host, local_port)
        with self._forward_lock:
            if key in self._forwardings:
                raise ForwardingError(
                    f"Port {local_host}:{local_port} is already forwarded"
                )

            forwarder = PortForwarder(
                local_host=local_host,
                local_port=local_port,
                remote_host=remote_host,
                remote_port=remote_port,
                logger=self.logger,
            )
            try:
                forwarder.start()
            except OSError as exc:
                raise ForwardingError(
                    f"Unable to start port forwarder for {local_host}:{local_port}: {exc}"
                ) from exc

            self._forwardings[key] = forwarder
            self.logger.info(
                "Forwarding %s:%d -> %s:%d established",
                local_host,
                local_port,
                remote_host,
                remote_port,
            )

    def remove_forward(self, *, local_host: str, local_port: int) -> None:
        key = (local_host, local_port)
        with self._forward_lock:
            forwarder = self._forwardings.pop(key, None)

        if forwarder is None:
            raise ForwardingError(
                f"No active forwarding for {local_host}:{local_port}"
            )

        forwarder.stop()
        self.logger.info(
            "Forwarding %s:%d removed",
            local_host,
            local_port,
        )

    def list_forwards(self) -> Iterable[Dict[str, Union[str, int]]]:
        with self._forward_lock:
            items = list(self._forwardings.items())

        for (local_host, local_port), forwarder in items:
            yield {
                "local_host": local_host,
                "local_port": local_port,
                "remote_host": forwarder.remote_host,
                "remote_port": forwarder.remote_port,
            }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def supported_features(self) -> Tuple[str, ...]:
        return ("shell", "push", "pull", "forward")

    def _normalise_storage_dir(
        self, storage_dir: Optional[Union[Path, str]]
    ) -> Path:
        if storage_dir is None:
            storage = Path.cwd() / "adb_storage"
        else:
            storage = Path(storage_dir)

        return storage.expanduser().resolve()

    def resolve_storage_path(self, remote_path: str, create_parent: bool) -> Path:
        if not remote_path:
            raise FileTransferError("Remote path must not be empty")

        candidate = Path(remote_path)
        safe_parts = [part for part in candidate.parts if part not in ("", ".", "..")]
        safe_path = Path(*safe_parts)
        full_path = (self.storage_dir / safe_path).resolve()

        try:
            full_path.relative_to(self.storage_dir)
        except ValueError as exc:
            raise FileTransferError(
                "Remote path escapes the configured storage directory"
            ) from exc

        if create_parent:
            full_path.parent.mkdir(parents=True, exist_ok=True)

        return full_path


class ADBClientSession(threading.Thread):
    """Handles communication with a single client connection."""

    def __init__(
        self,
        server: ADBServer,
        connection: socket.socket,
        address: Tuple[str, int],
    ) -> None:
        super().__init__(
            name=f"ADBClient-{address[0]}:{address[1]}", daemon=True
        )
        self.server = server
        self._conn = connection
        self._conn.settimeout(1.0)
        self.address = address
        self.serial: Optional[str] = None
        self._stop_event = threading.Event()
        self.logger = server.logger.getChild(
            f"client[{address[0]}:{address[1]}]"
        )

    def stop(self) -> None:
        self._stop_event.set()
        try:
            self._conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self._conn.close()
        except OSError:
            pass

    def run(self) -> None:
        try:
            self.logger.info("Connection established")
            self._perform_handshake()
            self.logger.info("Handshake complete for %s", self.serial)

            while not self._stop_event.is_set() and not self.server._stop_event.is_set():
                try:
                    message = receive_message(self._conn)
                except ConnectionClosed:
                    self.logger.info("Client disconnected")
                    break
                except ProtocolError as exc:
                    self.logger.warning("Protocol error: %s", exc)
                    self._send_error(command="protocol", message=str(exc))
                    break
                except OSError as exc:
                    if self._stop_event.is_set():
                        break
                    self.logger.error("Socket error: %s", exc)
                    break

                try:
                    self._handle_message(message)
                except (ShellCommandError, FileTransferError, ForwardingError) as exc:
                    self.logger.warning("Command failed: %s", exc)
                    self._send_error(
                        command=message.get("command", "unknown"),
                        message=str(exc),
                    )
                except ProtocolError as exc:
                    self.logger.warning("Invalid command payload: %s", exc)
                    self._send_error(
                        command=message.get("command", "unknown"),
                        message=str(exc),
                    )
                except Exception as exc:  # pragma: no cover - safety net
                    self.logger.exception("Unexpected error while handling message")
                    self._send_error(
                        command=message.get("command", "unknown"),
                        message=str(exc),
                    )

        finally:
            self.server._unregister_client(self)
            try:
                self._conn.close()
            except OSError:
                pass
            self.logger.info("Connection closed")

    # ------------------------------------------------------------------
    # Handshake and messaging
    # ------------------------------------------------------------------
    def _perform_handshake(self) -> None:
        try:
            message = receive_message(self._conn)
        except ConnectionClosed as exc:
            raise HandshakeError("Client disconnected before handshake") from exc
        except ProtocolError as exc:
            raise HandshakeError(f"Invalid handshake payload: {exc}") from exc

        if message.get("type") != "HELLO":
            raise HandshakeError("Expected HELLO message as the first packet")

        serial = message.get("serial")
        if not serial:
            serial = f"{self.address[0]}:{self.address[1]}"
        self.serial = str(serial)
        self.logger = self.server.logger.getChild(f"client[{self.serial}]")

        requested_features = message.get("features") or []
        if not isinstance(requested_features, list):
            raise HandshakeError("Expected list of features in handshake")

        self.logger.info("Requested features: %s", ", ".join(map(str, requested_features)))

        send_message(
            self._conn,
            {
                "type": "OKAY",
                "serial": self.serial,
                "features": list(self.server.supported_features),
                "message": "Handshake successful",
            },
        )

    def _handle_message(self, message: Dict[str, object]) -> None:
        message_type = message.get("type")

        if message_type == "PING":
            send_message(
                self._conn,
                {
                    "type": "PONG",
                    "serial": self.serial,
                    "timestamp": time.time(),
                },
            )
            return

        if message_type != "COMMAND":
            raise ProtocolError(f"Unsupported message type: {message_type}")

        command = message.get("command")
        if not isinstance(command, str):
            raise ProtocolError("Command message requires a 'command' string")

        arguments = message.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise ProtocolError("Command arguments must be a JSON object")

        if command == "shell":
            self._handle_shell(arguments)
        elif command == "push":
            self._handle_push(arguments)
        elif command == "pull":
            self._handle_pull(arguments)
        elif command == "forward":
            self._handle_forward(arguments)
        else:
            raise ProtocolError(f"Unknown command: {command}")

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------
    def _handle_shell(self, arguments: Dict[str, object]) -> None:
        raw_command = arguments.get("command")
        if not isinstance(raw_command, str) or not raw_command.strip():
            raise ShellCommandError("Shell command payload must include a non-empty 'command' string")

        timeout_value = arguments.get("timeout")
        timeout = None
        if timeout_value is not None:
            try:
                timeout = float(timeout_value)
            except (TypeError, ValueError) as exc:
                raise ShellCommandError("Timeout must be numeric") from exc

        try:
            completed = subprocess.run(
                raw_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ShellCommandError(
                f"Shell command timed out after {exc.timeout} seconds"
            ) from exc
        except OSError as exc:
            raise ShellCommandError(f"Unable to execute shell command: {exc}") from exc

        send_message(
            self._conn,
            {
                "type": "RESPONSE",
                "command": "shell",
                "status": "success",
                "payload": {
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                    "return_code": completed.returncode,
                },
            },
        )

    def _handle_push(self, arguments: Dict[str, object]) -> None:
        remote_path = arguments.get("path")
        if not isinstance(remote_path, str):
            raise FileTransferError("Push command requires a 'path' field")

        encoding = arguments.get("encoding", "base64")
        if encoding != "base64":
            raise FileTransferError("Only base64 encoding is supported for push data")

        data = arguments.get("data")
        if not isinstance(data, str):
            raise FileTransferError("Push command requires base64 encoded 'data'")

        try:
            decoded = base64.b64decode(data.encode("ascii"))
        except (ValueError, UnicodeError) as exc:
            raise FileTransferError("Invalid base64 data supplied for push") from exc

        destination = self.server.resolve_storage_path(remote_path, create_parent=True)

        try:
            destination.write_bytes(decoded)
        except OSError as exc:
            raise FileTransferError(f"Unable to write file: {exc}") from exc

        send_message(
            self._conn,
            {
                "type": "RESPONSE",
                "command": "push",
                "status": "success",
                "payload": {
                    "path": remote_path,
                    "size": len(decoded),
                },
            },
        )

    def _handle_pull(self, arguments: Dict[str, object]) -> None:
        remote_path = arguments.get("path")
        if not isinstance(remote_path, str):
            raise FileTransferError("Pull command requires a 'path' field")

        source = self.server.resolve_storage_path(remote_path, create_parent=False)

        if not source.exists() or not source.is_file():
            raise FileTransferError(f"File '{remote_path}' not found on device")

        try:
            content = source.read_bytes()
        except OSError as exc:
            raise FileTransferError(f"Unable to read file: {exc}") from exc

        encoded = base64.b64encode(content).decode("ascii")

        send_message(
            self._conn,
            {
                "type": "RESPONSE",
                "command": "pull",
                "status": "success",
                "payload": {
                    "path": remote_path,
                    "encoding": "base64",
                    "data": encoded,
                    "size": len(content),
                },
            },
        )

    def _handle_forward(self, arguments: Dict[str, object]) -> None:
        action = arguments.get("action", "add")

        if action == "add":
            local_host = arguments.get("local_host", "127.0.0.1")
            local_port = arguments.get("local_port")
            remote_host = arguments.get("remote_host")
            remote_port = arguments.get("remote_port")

            if not isinstance(local_host, str):
                raise ForwardingError("local_host must be a string")
            if not isinstance(local_port, int):
                raise ForwardingError("local_port must be an integer")
            if not isinstance(remote_host, str):
                raise ForwardingError("remote_host must be a string")
            if not isinstance(remote_port, int):
                raise ForwardingError("remote_port must be an integer")

            self.server.add_forward(
                local_host=local_host,
                local_port=local_port,
                remote_host=remote_host,
                remote_port=remote_port,
            )

            payload = {
                "local_host": local_host,
                "local_port": local_port,
                "remote_host": remote_host,
                "remote_port": remote_port,
            }
        elif action == "remove":
            local_host = arguments.get("local_host", "127.0.0.1")
            local_port = arguments.get("local_port")
            if not isinstance(local_port, int):
                raise ForwardingError("local_port must be an integer when removing a forward")

            if not isinstance(local_host, str):
                raise ForwardingError("local_host must be a string when removing a forward")

            self.server.remove_forward(local_host=local_host, local_port=local_port)
            payload = {
                "local_host": local_host,
                "local_port": local_port,
            }
        elif action == "list":
            forwards = list(self.server.list_forwards())
            payload = {"forwards": forwards}
        else:
            raise ForwardingError(f"Unknown forwarding action: {action}")

        send_message(
            self._conn,
            {
                "type": "RESPONSE",
                "command": "forward",
                "status": "success",
                "payload": payload,
            },
        )

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------
    def _send_error(self, *, command: str, message: str) -> None:
        try:
            send_message(
                self._conn,
                {
                    "type": "ERROR",
                    "command": command,
                    "status": "failure",
                    "message": message,
                },
            )
        except OSError:
            pass


__all__ = ["ADBServer", "PortForwarder"]
