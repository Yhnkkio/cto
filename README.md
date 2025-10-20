ADB Overlay Server (Scaffold)

A minimal, scaffolded Python project for an ADB overlay mock server. It includes a Typer-based CLI, sample configuration files, basic logging, and a placeholder async listener optionally advertised via Zeroconf.

Features
- Typer CLI with `adb-mockd` console script
- `python -m adb_overlay_server` support
- Sample configuration: `prop.json`, `commands.json`, and `overlay/`
- Basic logging to `logs/adb_overlay_server.log`
- Optional Zeroconf/mDNS advertisement (placeholder)

Quickstart
1. Create and activate a virtual environment (optional but recommended):
   - python -m venv .venv
   - source .venv/bin/activate

2. Install the project in editable/development mode with dev tools:
   - pip install -e .[dev]

3. Show help:
   - python -m adb_overlay_server --help
   - adb-mockd --help

4. Run the server with built-in sample data:
   - python -m adb_overlay_server run
   - or `adb-mockd run`

   The server currently runs a placeholder async loop and optionally advertises a Zeroconf service named "ADB Mock Server" on `_adb-mock._tcp.local.`. Stop it with Ctrl+C.

5. Run with a custom configuration directory:
   - python -m adb_overlay_server run --config /path/to/config/dir
   The directory should contain `prop.json`, `commands.json`, and an `overlay/` subdirectory.

Configuration
- By default, the server uses built-in sample configuration under `adb_overlay_server/data/`.
- You can provide a custom `--overlay` path to override the overlay directory path.
- Logging writes to `./logs/adb_overlay_server.log` in the current working directory.

Developer Notes
- Format: `black .`
- Lint: `ruff check .`
- Test: `pytest`

License
MIT
