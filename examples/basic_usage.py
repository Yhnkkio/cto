"""Minimal example showcasing the Python ADB protocol server."""

from __future__ import annotations

import base64
import logging
import socket
from pprint import pprint

from adb_server import ADBServer
from adb_server.protocol import receive_message, send_message


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")

    server = ADBServer(port=0)
    server.start()

    print(f"ADB server running on {server.host}:{server.port}")

    try:
        with socket.create_connection((server.host, server.port)) as client_sock:
            send_message(
                client_sock,
                {
                    "type": "HELLO",
                    "serial": "demo-client",
                    "features": ["shell", "push", "pull", "forward"],
                },
            )
            print("Handshake reply:")
            pprint(receive_message(client_sock))

            send_message(
                client_sock,
                {
                    "type": "COMMAND",
                    "command": "shell",
                    "arguments": {"command": "echo 'Hello from the server!'"},
                },
            )
            print("Shell command response:")
            pprint(receive_message(client_sock))

            payload = base64.b64encode(b"Demo file contents").decode("ascii")
            send_message(
                client_sock,
                {
                    "type": "COMMAND",
                    "command": "push",
                    "arguments": {
                        "path": "demo/file.txt",
                        "data": payload,
                    },
                },
            )
            print("Push response:")
            pprint(receive_message(client_sock))

            send_message(
                client_sock,
                {
                    "type": "COMMAND",
                    "command": "pull",
                    "arguments": {"path": "demo/file.txt"},
                },
            )
            pull_response = receive_message(client_sock)
            print("Pull response:")
            pprint(pull_response)

            pulled_payload = pull_response["payload"]["data"]
            print("Decoded file contents:", base64.b64decode(pulled_payload.encode("ascii")).decode())
    finally:
        server.stop()
        print("ADB server stopped")


if __name__ == "__main__":
    main()
