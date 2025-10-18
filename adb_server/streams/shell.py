"""Shell service stream implementation."""

from __future__ import annotations

from typing import Optional

from ..shell import ShellEnvironment, ShellResponse
from .base import BaseStream


class ShellStream(BaseStream):
    """Implements the `shell:` and `exec:` services."""

    def __init__(
        self,
        transport,
        local_id: int,
        remote_id: int,
        shell: ShellEnvironment,
        initial_command: Optional[str] = None,
        interactive: bool = False,
    ) -> None:
        super().__init__(transport, local_id, remote_id)
        self.shell = shell
        self.initial_command = initial_command
        self.interactive = interactive
        self.input_buffer: str = ""
        self.awaiting_exit = False

    def start(self) -> None:
        if self.initial_command is not None:
            response = self.shell.execute(self.initial_command)
            self._send_response(response)
            self.close()
            return
        if self.interactive:
            self.send(self.shell.prompt.encode("utf-8"))

    def handle_client_data(self, data: bytes) -> None:
        if not self.interactive:
            # Non-interactive shells do not expect further data.
            return
        text = data.decode("utf-8", errors="ignore")
        for char in text:
            if char == "\x03":  # Ctrl+C
                self.input_buffer = ""
                self.send(b"^C\r\n")
                self.send(self.shell.prompt.encode("utf-8"))
                continue
            if char == "\x04":  # Ctrl+D
                self.awaiting_exit = True
                self.close()
                return
            if char in "\r\n":
                command = self.input_buffer.strip()
                self.input_buffer = ""
                if command:
                    if command == "exit":
                        self.send(b"exit\r\n")
                        self.close()
                        return
                    response = self.shell.execute(command)
                    self._send_response(response)
                self.send(self.shell.prompt.encode("utf-8"))
            else:
                self.input_buffer += char

    def handle_close(self) -> None:
        super().handle_close()

    def _send_response(self, response: ShellResponse) -> None:
        output = response.as_text()
        if output:
            normalized = output.replace("\n", "\r\n")
            self.send(normalized.encode("utf-8"))
