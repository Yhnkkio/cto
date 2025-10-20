from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import typer

from . import __version__
from .config import Config, load_config
from .logging_setup import setup_logging
from .server import serve_forever

app = typer.Typer(add_completion=False, help="ADB overlay mock server")


def version_callback(value: bool):
    if value:
        typer.echo(f"adb-overlay-server {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
):
    pass


@app.command(help="Run the ADB overlay mock server with the given configuration.")
def run(
    config_dir: Path = typer.Option(
        None,
        "--config",
        exists=True,
        file_okay=False,
        dir_okay=True,
        writable=False,
        readable=True,
        resolve_path=True,
        help=(
            "Path to configuration directory containing prop.json and commands.json. "
            "Defaults to built-in sample data."
        ),
    ),
    overlay_dir: Optional[Path] = typer.Option(
        None,
        "--overlay",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Path to overlay directory overriding the one in the config directory.",
    ),
    port: int = typer.Option(5037, "--port", help="TCP port to listen on (placeholder)."),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        help="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).",
    ),
    advertise: bool = typer.Option(
        True,
        "--zeroconf/--no-zeroconf",
        help="Register a Zeroconf/mDNS service for discovery (placeholder).",
    ),
):
    setup_logging(log_level)
    logger = logging.getLogger(__name__)

    cfg: Config = load_config(config_dir=config_dir, overlay_dir=overlay_dir)
    logger.debug("Loaded configuration: %s", cfg)
    logger.info("Starting server on port %s (zeroconf=%s)", port, advertise)

    try:
        asyncio.run(serve_forever(port=port, config=cfg, advertise=advertise))
    except KeyboardInterrupt:
        logger.info("Interrupted by user, shutting down.")


# Expose app as console script entrypoint
if __name__ == "__main__":
    app()
