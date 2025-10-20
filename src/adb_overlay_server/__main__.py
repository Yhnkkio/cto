from __future__ import annotations

from .main import app

if __name__ == "__main__":
    # Delegate to Typer app so `python -m adb_overlay_server` works
    app()
