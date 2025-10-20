# cto – ADB simulator scaffold and developer CLI

This repository contains a minimal, typed Python 3.11+ project scaffold with a Typer-based CLI, configuration loading (TOML/YAML), and developer tooling for linting, formatting, and type checking. It includes stub functionality for an asyncio-based ADB simulator server and overlay data management.

## Requirements

- Python 3.11+
- Recommended: `pipx` for global developer tools, or a virtual environment
- Runtime dependencies are installed automatically by the tooling:
  - [`typer`](https://typer.tiangolo.com)
  - [`PyYAML`](https://pyyaml.org)
- Optional/related tools and libraries:
  - `adb` (Android Debug Bridge) – if interacting with an actual ADB setup
  - `zeroconf` – for network service discovery (advertise/discovery), not required for the stub server
  - asyncio (standard library)

## Getting started

Clone the repo and create a virtual environment (examples using `venv` or `uv`):

```bash
python3.11 -m venv .venv
source .venv/bin/activate
# or with uv
# pip install uv  # if not already installed
# uv venv -p 3.11
# source .venv/bin/activate
```

Install developer tooling and run checks using nox:

```bash
pip install nox
nox -s lint
nox -s typecheck
```

You can also install the package in editable mode for local development:

```bash
pip install -e .
```

### Using pip-tools (optional)

This project includes `pip-tools` inputs to enable reproducible lockfiles if desired.

```bash
pip install pip-tools
pip-compile requirements.in --output-file requirements.txt
pip-compile requirements-dev.in --output-file requirements-dev.txt
pip-sync requirements-dev.txt
```

### Using uv (optional)

If you prefer `uv`, it works with the provided `pyproject.toml`:

```bash
# Install project and deps
uv pip install -e .

# Run the CLI
python -m cto --help
```

## CLI usage

Run with Python module form (recommended during development):

```bash
python -m cto --help
python -m cto run --help
python -m cto start
python -m cto version
python -m cto overlay --help
python -m cto overlay init
python -m cto config show
```

If installed, the console script `cto` will also be available:

```bash
cto --help
```

### Example

```bash
python -m cto run --host 127.0.0.1 --port 5555
# Press Ctrl+C to exit
```

## Configuration

Configuration can be provided in TOML or YAML. The loader searches in this order:

1. Explicit `--config` path
2. `CTO_CONFIG` environment variable
3. Current working directory: `cto.toml`, `config.toml`, `cto.yaml`, `cto.yml`, `config.yaml`, `config.yml`
4. User config dir: `~/.config/cto/{cto.toml, config.toml, cto.yaml, ...}`

When not provided, defaults are resolved relative to the current working directory:

- overlay/: `./overlay`
- props: `./overlay/props`
- commands: `./overlay/commands`
- logs: `./logs`
- server host: `127.0.0.1`
- server port: `5555`

You can inspect the resolved values with:

```bash
python -m cto config show
```

### Example configuration (TOML)

```toml
# cto.toml
env = "dev"
debug = true

[paths]
overlay = "./overlay"
props = "./overlay/props"
commands = "./overlay/commands"
logs = "./logs"

[server]
host = "0.0.0.0"
port = 5555
advertise = false
```

### Example configuration (YAML)

```yaml
# cto.yaml
env: dev
debug: true
paths:
  overlay: ./overlay
  props: ./overlay/props
  commands: ./overlay/commands
  logs: ./logs
server:
  host: 0.0.0.0
  port: 5555
  advertise: false
```

## Repository structure

```
.
├── pyproject.toml           # Project metadata, build backend (hatchling), and tooling config
├── noxfile.py               # Lint/format/type-check sessions
├── requirements*.in         # Optional pip-tools inputs
├── src/
│   └── cto/
│       ├── __init__.py      # Package version
│       ├── __main__.py      # Enables `python -m cto`
│       ├── cli.py           # Typer CLI app
│       ├── config.py        # Config loader (TOML/YAML) with defaults
│       ├── overlay.py       # Overlay management helpers
│       └── server.py        # Asyncio ADB simulator stub server
└── README.md
```

## Development notes

- Run linting and type checks:
  - `nox -s lint`
  - `nox -s typecheck`
- Format code: `nox -s format`
- The ADB server included here is a stub echo server to validate asyncio wiring. Replace with actual ADB simulator logic as needed.
- Zeroconf advertising is not implemented yet; the config option is reserved for future use.
