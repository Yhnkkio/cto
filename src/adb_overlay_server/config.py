from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class Config:
    config_dir: Path
    overlay_dir: Path
    props: Dict[str, Any]
    commands: Dict[str, Any]


def _default_data_dir() -> Path:
    return Path(__file__).resolve().parent / "data"


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_config(config_dir: Optional[Path] = None, overlay_dir: Optional[Path] = None) -> Config:
    base_dir = config_dir if config_dir is not None else _default_data_dir()

    props_path = base_dir / "prop.json"
    cmds_path = base_dir / "commands.json"
    ovl_dir = overlay_dir if overlay_dir is not None else base_dir / "overlay"

    if not props_path.exists():
        raise FileNotFoundError(f"prop.json not found at {props_path}")
    if not cmds_path.exists():
        raise FileNotFoundError(f"commands.json not found at {cmds_path}")
    if not ovl_dir.exists():
        # Create an empty overlay directory if missing (helpful during dev)
        ovl_dir.mkdir(parents=True, exist_ok=True)

    logger.debug("Loading props from %s", props_path)
    props = _read_json(props_path)

    logger.debug("Loading commands from %s", cmds_path)
    commands = _read_json(cmds_path)

    return Config(config_dir=base_dir, overlay_dir=ovl_dir, props=props, commands=commands)
