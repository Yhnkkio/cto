# Python ADB Protocol Server

A lightweight, pure-Python implementation of an ADB (Android Debug Bridge) style
server. The project demonstrates how to build a multi-client TCP server that
speaks a simplified ADB-inspired protocol featuring handshakes, shell command
execution, file transfer, and TCP port forwarding.

> ⚠️ This implementation is intentionally simplified for educational and testing
> purposes. It does not aim to be a drop-in replacement for the Android Debug
> Bridge provided by the Android SDK.

## Features

- **Connection management & handshake** – clients announce themselves with a
  `HELLO` packet and receive capabilities in response.
- **Command routing** – commands are encoded as JSON messages prefixed with a
  4-byte little-endian size header.
- **Shell command execution** – run arbitrary shell commands on the host and
  capture stdout/stderr as the response payload.
- **File transfers** – push files to the server and pull them back via base64
  encoded payloads confined to a safe storage directory.
- **Port forwarding** – spawn TCP forwarders that bridge connections from the
  host machine to arbitrary remote hosts/ports.
- **Multi-client support** – every connected client is handled by a dedicated
  thread.
- **Logging & error handling** – consistent logging for all subsystems and
  structured error responses returned to clients.

## Requirements

- Python 3.8+
- Standard library only (`socket`, `struct`, `threading`, `subprocess`, etc.)

## Installation

Clone or copy the repository, then ensure the project directory is on your
`PYTHONPATH` (or install it in editable mode).

```
python -m pip install -e .  # optional; not required for running the examples
```

## Getting Started

```python
from adb_server import ADBServer

server = ADBServer(host="127.0.0.1", port=5037)
server.start()

# Run until interrupted
try:
    server.serve_forever()
finally:
    server.stop()
```

Alternatively, run the included example which starts the server, connects a
client, and demonstrates shell execution plus file transfer:

```
python examples/basic_usage.py
```

## Protocol Overview

All messages follow the format:

```
+----------------------------+
| 4 byte size (little-endian)|
+----------------------------+
| JSON payload (UTF-8 bytes) |
+----------------------------+
```

Each payload must be a JSON object containing, at minimum, a `type` field.

### Handshake

1. Client connects and sends:
   ```json
   {
     "type": "HELLO",
     "serial": "demo-client",
     "features": ["shell", "push", "pull", "forward"]
   }
   ```
2. Server replies with:
   ```json
   {
     "type": "OKAY",
     "serial": "demo-client",
     "features": ["shell", "push", "pull", "forward"],
     "message": "Handshake successful"
   }
   ```

### Command Messages

After a successful handshake clients can send command packets:

```json
{
  "type": "COMMAND",
  "command": "shell",
  "arguments": {"command": "echo hello"}
}
```

Supported commands:

| Command  | Description | Arguments |
|----------|-------------|-----------|
| `shell`  | Execute a shell command on the host machine. | `command` (str), optional `timeout` (float seconds)
| `push`   | Upload a file to the server's storage area. | `path` (str), `data` (base64 str), optional `encoding` (`base64`)
| `pull`   | Download a file previously pushed to the server. | `path` (str)
| `forward` | Manage TCP port forwarding rules. | Detailed below |

### Port Forwarding

Forwarding commands use the `forward` command with one of three actions:

```json
{
  "type": "COMMAND",
  "command": "forward",
  "arguments": {
    "action": "add",
    "local_host": "127.0.0.1",
    "local_port": 9000,
    "remote_host": "example.com",
    "remote_port": 80
  }
}
```

- `add` – start forwarding a local port to a remote host/port.
- `remove` – stop forwarding: requires `local_port` (and optional `local_host`).
- `list` – list active forwardings; response payload contains a `forwards`
  array.

### Responses and Errors

Successful commands receive a `RESPONSE` packet:

```json
{
  "type": "RESPONSE",
  "command": "shell",
  "status": "success",
  "payload": {
    "stdout": "hello\n",
    "stderr": "",
    "return_code": 0
  }
}
```

Failures return an `ERROR` packet with `status="failure"` and a readable
`message` field explaining the cause.

## Storage Safety

Files transferred via `push` and `pull` are restricted to a dedicated
`adb_storage` directory (configurable via the `storage_dir` parameter when
creating the server). Path traversal attempts are blocked to prevent escaping
this sandbox.

## Logging

The server uses the standard `logging` module. Configure logging as needed in
your application to gain insight into connection and command handling:

```python
import logging

logging.basicConfig(level=logging.INFO)
```

## Limitations & Notes

- Authentication and device enumeration are intentionally omitted.
- Shell commands run on the host machine – handle with care.
- Port forwarding is implemented using simple TCP proxy threads and is intended
  for lightweight development scenarios.
- The message format is intentionally JSON-based for developer ergonomics; the
  real ADB protocol uses binary packets and a different framing strategy.

## License

This project is provided under the MIT license. See `LICENSE` for details (not
included by default).
