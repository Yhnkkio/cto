Developer Guide

This repository contains a minimal scaffold for an ADB overlay mock server. The current implementation includes a Typer CLI, configuration loader, basic logging, and a placeholder async loop. Future work can replace the placeholder with a real ADB protocol implementation.

Repository Layout
- pyproject.toml: Project metadata, dependencies, tooling config
- src/adb_overlay_server/
  - __init__.py: Package version
  - __main__.py: Enables `python -m adb_overlay_server`
  - main.py: Typer CLI (`adb-mockd` console script)
  - config.py: Configuration loader for prop.json, commands.json, overlay/
  - logging_setup.py: Basic logging to stdout and logs/adb_overlay_server.log
  - server.py: Placeholder async loop and optional Zeroconf advertisement
  - data/: Built-in sample configuration
    - prop.json
    - commands.json
    - overlay/ (placeholder files)

Getting Started
1. Create a virtual environment:
   - python -m venv .venv
   - source .venv/bin/activate

2. Install dependencies for development:
   - pip install -e .[dev]

3. Run the CLI:
   - python -m adb_overlay_server --help
   - adb-mockd --help

4. Start the server with default sample config:
   - python -m adb_overlay_server run

5. Start the server with a custom config:
   - python -m adb_overlay_server run --config ./path/to/config
   Ensure the directory contains `prop.json`, `commands.json`, and `overlay/`.

Logging
- Logs are written to `./logs/adb_overlay_server.log` and also output to stdout.
- You can adjust level with `--log-level`, e.g. `--log-level DEBUG`.

Testing, Linting, Formatting
- pytest: `pytest`
- ruff: `ruff check .`
- black: `black .`

Releasing / Packaging
- The project uses setuptools with a `src/` layout.
- The `data/` directory is included as package data, so the built-in samples are available at runtime.

Notes
- The Zeroconf registration is a placeholder for discovery and may be replaced or expanded later.
- The server loop is a stub; replace it with actual protocol handling in future iterations.
