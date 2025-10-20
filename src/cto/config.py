from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import os
import sys
import logging

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - for safety if run on <3.11
    import tomli as tomllib  # type: ignore[no-redef]

import yaml

log = logging.getLogger(__name__)


CONFIG_FILENAMES_TOML = ("cto.toml", "config.toml")
CONFIG_FILENAMES_YAML = ("cto.yaml", "cto.yml", "config.yaml", "config.yml")
DEFAULT_CONFIG_DIR_UNIX = Path.home() / ".config" / "cto"


@dataclass(frozen=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 5555
    advertise: bool = False  # whether to advertise via zeroconf, not implemented yet


@dataclass(frozen=True)
class PathsConfig:
    base_dir: Path
    overlay_dir: Path
    props_dir: Path
    commands_dir: Path
    logs_dir: Path


@dataclass(frozen=True)
class AppConfig:
    paths: PathsConfig
    server: ServerConfig
    env: str = "dev"
    debug: bool = False


def _find_config_file(explicit: Optional[Path]) -> Optional[Path]:
    if explicit is not None:
        return explicit

    env_path = os.environ.get("CTO_CONFIG")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    cwd = Path.cwd()
    for name in (*CONFIG_FILENAMES_TOML, *CONFIG_FILENAMES_YAML):
        candidate = cwd / name
        if candidate.exists():
            return candidate

    # Home config directory
    for name in (*CONFIG_FILENAMES_TOML, *CONFIG_FILENAMES_YAML):
        candidate = DEFAULT_CONFIG_DIR_UNIX / name
        if candidate.exists():
            return candidate

    return None


def _read_toml(p: Path) -> Dict[str, Any]:
    with p.open("rb") as f:
        return tomllib.load(f)  # type: ignore[no-any-return]


def _read_yaml(p: Path) -> Dict[str, Any]:
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML config must be a mapping at top-level: {p}")
    return data


def _to_path(value: Optional[str | os.PathLike[str]], *, base_dir: Path) -> Path:
    if value is None:
        return base_dir
    p = Path(value)
    if not p.is_absolute():
        p = (base_dir / p).resolve()
    return p


def _defaults(base_dir: Path) -> Tuple[PathsConfig, ServerConfig, Dict[str, Any]]:
    overlay = base_dir / "overlay"
    props = overlay / "props"
    commands = overlay / "commands"
    logs = base_dir / "logs"
    paths = PathsConfig(
        base_dir=base_dir,
        overlay_dir=overlay,
        props_dir=props,
        commands_dir=commands,
        logs_dir=logs,
    )
    server = ServerConfig()
    meta: Dict[str, Any] = {"env": "dev", "debug": False}
    return paths, server, meta


def load_config(*, config_path: Optional[Path] = None, base_dir: Optional[Path] = None) -> AppConfig:
    base_dir = base_dir or Path.cwd()
    base_dir = base_dir.resolve()
    # Defaults first
    default_paths, default_server, meta_defaults = _defaults(base_dir)

    # Load file if available
    file_path = _find_config_file(config_path)
    raw: Dict[str, Any] = {}
    if file_path is not None:
        try:
            if file_path.suffix.lower() == ".toml":
                raw = _read_toml(file_path)
            else:
                raw = _read_yaml(file_path)
            log.debug("Loaded config from %s", file_path)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"Failed to load config: {exc}", file=sys.stderr)
            raw = {}

    # Extract sections
    raw_paths = (raw.get("paths") or {}) if isinstance(raw.get("paths"), dict) else {}
    raw_server = (raw.get("server") or {}) if isinstance(raw.get("server"), dict) else {}

    # Paths resolution
    overlay_dir = _to_path(raw_paths.get("overlay"), base_dir=base_dir)
    props_dir = _to_path(raw_paths.get("props"), base_dir=overlay_dir)
    commands_dir = _to_path(raw_paths.get("commands"), base_dir=overlay_dir)
    logs_dir = _to_path(raw_paths.get("logs"), base_dir=base_dir)

    paths = PathsConfig(
        base_dir=base_dir,
        overlay_dir=overlay_dir if raw_paths.get("overlay") else default_paths.overlay_dir,
        props_dir=props_dir if raw_paths.get("props") else default_paths.props_dir,
        commands_dir=commands_dir if raw_paths.get("commands") else default_paths.commands_dir,
        logs_dir=logs_dir if raw_paths.get("logs") else default_paths.logs_dir,
    )

    # Server section
    server = ServerConfig(
        host=str(raw_server.get("host", default_server.host)),
        port=int(raw_server.get("port", default_server.port)),
        advertise=bool(raw_server.get("advertise", default_server.advertise)),
    )

    env = str(raw.get("env", meta_defaults["env"]))
    debug = bool(raw.get("debug", meta_defaults["debug"]))

    return AppConfig(paths=paths, server=server, env=env, debug=debug)


def ensure_directories(cfg: AppConfig) -> None:
    cfg.paths.overlay_dir.mkdir(parents=True, exist_ok=True)
    cfg.paths.props_dir.mkdir(parents=True, exist_ok=True)
    cfg.paths.commands_dir.mkdir(parents=True, exist_ok=True)
    cfg.paths.logs_dir.mkdir(parents=True, exist_ok=True)

