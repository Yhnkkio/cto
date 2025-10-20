Python ADB Server (Device and Host stubs)

Overview
- A pure-Python (3.11+) ADB protocol server with a focus on a functional device-mode (port 5555) implementation that works with stock adb for common workflows: connect, shell, exec, and SYNC push/pull/stat/list. Authentication is disabled (simulating ro.adb.secure=0) so the device always appears as "device".
- A host-server (5037) entrypoint is included as a stub and will be expanded in future iterations.

Features implemented
- ADB transport (CNXN/OPEN/OKAY/WRTE/CLSE, no AUTH) using asyncio
- Channel multiplexing with simple flow control
- Device mode server on configurable TCP port (default 5555)
- Shell services:
  - Non-interactive: `adb shell <cmd>`
  - Interactive: simple REPL with cwd, history, prompt, Ctrl+C/Ctrl+D handling
  - exec:<cmd> mapped to shell execution path
- Overlay-only filesystem rooted at ./overlay
  - Strict path normalization, no path escapes
  - Built-ins: ls, cat, echo (with > and >>), mkdir -p, rm/rm -r, touch, pwd, cd, getprop, setprop
- SYNC service (push/pull/stat/list) for overlay
- Simulation layers
  - prop.json with Pixel-like defaults (serial emu-00000001)
  - command.json optional command overrides
- Logging: per-connection JSONL under logs/
- CLI: `python -m main` or `python main.py` with mode selection and ports

Quick start (device mode)
1) Create and populate the overlay filesystem directory if needed:
   mkdir -p overlay
2) Start the device server on port 5555:
   python3 -m main --mode device --device-port 5555 --serial emu-00000001
3) In another terminal, connect with adb:
   adb connect 127.0.0.1:5555
   adb devices
   adb shell
   adb push localfile /remote/file
   adb pull /remote/file ./localcopy

Configuration
- CLI flags control ports, serial, overlay path, and log directory.
- Environment variables are supported for the same keys; see main.py --help.
- command.json and prop.json in the repository root provide simulation layers.

Notes
- mDNS advertisement is intentionally optional; the server will run without zeroconf. If zeroconf is available, it will announce _adb._tcp with the configured serial as the service name.
- The host server (5037) is a placeholder and not required for direct `adb connect` to the device-mode server.

Limitations
- TLS, authentication (AUTH/PKI), shell_v2, stat_v2/ls_v2 are not implemented.
- The host mode (5037) is a stub and not yet routing device services.
