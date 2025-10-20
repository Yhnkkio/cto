from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import typer

from . import __version__
from .config import AppConfig, ensure_directories, load_config
from .overlay import init_overlay, list_overlay_files
from .server import run_server

app = typer.Typer(help="CLI for the ADB simulator development environment and overlay management.")
overlay_app = typer.Typer(help="Manage overlay data (commands, props).")
config_app = typer.Typer(help="Inspect and manage configuration.")


@dataclass
class State:
    config: AppConfig


def _setup_logging(debug: bool, logs_dir: Path) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "cto.log"
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


@app.callback()
def _load_config(
    ctx: typer.Context,
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to a configuration file (TOML or YAML). Overrides discovery.",
    ),
    base_dir: Optional[Path] = typer.Option(
        None,
        "--base-dir",
        help="Base directory for default paths. Defaults to the current working directory.",
    ),
) -> None:
    cfg = load_config(config_path=config, base_dir=base_dir)
    _setup_logging(debug=cfg.debug, logs_dir=cfg.paths.logs_dir)
    ctx.obj = State(config=cfg)


@app.command(name="version")
def version() -> None:
    """Print version information."""
    typer.echo(__version__)


@app.command(name="run")
def run(
    ctx: typer.Context,
    host: Optional[str] = typer.Option(None, help="Server bind host. Overrides config."),
    port: Optional[int] = typer.Option(None, help="Server bind port. Overrides config."),
) -> None:
    """Start the ADB simulator server (asyncio stub)."""
    assert isinstance(ctx.obj, State)
    cfg = ctx.obj.config
    ensure_directories(cfg)

    h = host or cfg.server.host
    p = port or cfg.server.port
    typer.echo(f"Starting ADB simulator on {h}:{p} (press Ctrl+C to stop)...")

    try:
        asyncio.run(run_server(h, p, cfg.paths.logs_dir))
    except KeyboardInterrupt:
        typer.echo("Shutting down...")


# Alias for run
app.command(name="start")(run)


@overlay_app.command("init")
def overlay_init(ctx: typer.Context) -> None:
    """Create overlay directories if they do not exist."""
    assert isinstance(ctx.obj, State)
    init_overlay(ctx.obj.config)
    typer.echo(str(ctx.obj.config.paths.overlay_dir))


@overlay_app.command("path")
def overlay_path(ctx: typer.Context) -> None:
    """Print the overlay directory path."""
    assert isinstance(ctx.obj, State)
    typer.echo(str(ctx.obj.config.paths.overlay_dir))


@overlay_app.command("ls")
def overlay_ls(ctx: typer.Context) -> None:
    """List files inside the overlay directory."""
    assert isinstance(ctx.obj, State)
    files = list_overlay_files(ctx.obj.config)
    if not files:
        typer.echo("<empty>")
    else:
        for p in files:
            typer.echo(str(p.relative_to(ctx.obj.config.paths.base_dir)))


@config_app.command("show")
def config_show(ctx: typer.Context) -> None:
    """Show the resolved configuration values."""
    assert isinstance(ctx.obj, State)
    cfg = ctx.obj.config
    lines = [
        "env: " + cfg.env,
        f"debug: {cfg.debug}",
        "paths:",
        f"  base_dir:    {cfg.paths.base_dir}",
        f"  overlay_dir: {cfg.paths.overlay_dir}",
        f"  props_dir:   {cfg.paths.props_dir}",
        f"  commands_dir:{cfg.paths.commands_dir}",
        f"  logs_dir:    {cfg.paths.logs_dir}",
        "server:",
        f"  host: {cfg.server.host}",
        f"  port: {cfg.server.port}",
        f"  advertise: {cfg.server.advertise}",
    ]
    for l in lines:
        typer.echo(l)


app.add_typer(overlay_app, name="overlay")
app.add_typer(config_app, name="config")
