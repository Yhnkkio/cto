# Mock ADB Python Server

This project provides a Python implementation of an Android Debug Bridge (ADB) server that mimics the behaviour of a real Android device. The server implements the low-level ADB protocol, offers a configurable mock Android environment, and supports the most common ADB commands including push/pull, install, shell (interactive and non-interactive) and logcat.

## Features

- **Protocol compatibility**
  - Listens on the standard ADB port (`5037`)
  - Handles the host text protocol (`host:*` requests)
  - Implements the binary transport protocol (`A_CNXN`, `A_OPEN`, `A_WRTE`, `A_OKAY`, `A_CLSE`)
  - Supports the sync service (`sync:`) used by `adb push` and `adb pull`
  - Provides shell services (`shell:`, `exec:`) with interactive session support
  - Simulates `logcat` streaming output

- **Mock Android device**
  - Configuration-driven filesystem, packages, running processes and system properties
  - In-memory filesystem with permission, ownership and symlink support
  - Simulated package manager (`pm`), activity manager (`am`), property service (`getprop` / `setprop`)
  - Simplified reboot and log buffering behaviour

- **Shell environment**
  - Stateful shell interpreter with persistent working directory and history
  - Supports common commands (`cd`, `ls`, `cat`, `echo`, `mkdir`, `rm`, `cp`, `mv`, `chmod`, `chown`, `ps`, `top`, `getprop`, `setprop`, `pm`, `am`, `history`, `exit`)
  - Interactive sessions handle prompts, command history and Ctrl+C / Ctrl+D control characters

## Installation

The server only relies on the Python standard library. Python 3.10 or newer is recommended.

```bash
python -m adb_server --help
```

## Running the server

```bash
python -m adb_server --config mock_device_config.json --host 127.0.0.1 --port 5037 --verbose
```

Once running, you can use the regular Android SDK `adb` client:

```bash
adb kill-server           # ensure the official server is not running
adb connect 127.0.0.1:5037
adb devices
adb shell
adb push local.txt /sdcard/Download/local.txt
adb pull /system/build.prop ./build.prop
adb logcat
```

> **Note**: Because the mock server binds to the standard ADB port, make sure the official `adb` server is not running. Use `adb kill-server` before starting this mock server.

## Configuration file

The server loads configuration data from a JSON or YAML file. See [`mock_device_config.json`](mock_device_config.json) for a comprehensive example. The configuration supports the following sections:

| Section       | Description |
|---------------|-------------|
| `device`      | Basic device metadata such as serial, model, manufacturer, Android version and state |
| `properties`  | Key/value map of Android system properties exposed via `getprop` |
| `filesystem`  | List of file entries describing directories, files and symlinks, including content, permissions and ownership |
| `packages`    | Installed package list. Either simple package strings or objects with `package` and `path` |
| `processes`   | Running process table used for `ps` / `top`. Each entry supports `pid`, `user`, `name`, `cpu`, `mem` |
| `logs`        | Initial log buffer used by the `logcat` service |

### Filesystem entries

Each filesystem entry has the following fields:

- `path` – absolute POSIX path
- `type` – `file`, `dir` or `symlink`
- `permissions` – POSIX mode as octal string (e.g., `"0755"`)
- `owner` / `group` – owner metadata
- `content` – optional string or binary data for files
- `target` – required for symlinks, specifies the target path

The filesystem is stored in-memory. File modifications performed through the shell or sync service update the in-memory state for the duration of the server process.

## Supported ADB commands

- `adb devices`
- `adb version`
- `adb get-state`
- `adb get-serialno`
- `adb forward`, `adb forward --list`, `adb forward --remove`
- `adb push`
- `adb pull`
- `adb install` (recorded in package list)
- `adb shell` (`shell` and `exec` services, interactive and non-interactive)
- `adb exec-out`
- `adb logcat`
- `adb reboot` (simulated state change and log entry)

Additional shell commands are handled inside the shell interpreter, including package manager (`pm`) and activity manager (`am`) operations.

## Development notes

- Logging is configured via the `--verbose` flag or by setting the `ADB_SERVER_LOG_LEVEL` environment variable when embedding the server.
- The server is single-device: all clients interact with the same mock device state.
- The implementation focuses on correctness of protocol flow and realistic behaviour rather than absolute performance.

## Limitations

- Cryptographic authentication is bypassed; all clients are treated as authorised.
- The shell command support covers common workflows but is not exhaustive.
- Port forwarding entries are recorded but no actual sockets are opened.
- The mock filesystem is in-memory; changes are not persisted to disk.

## License

This project is provided as-is for development and testing purposes.
