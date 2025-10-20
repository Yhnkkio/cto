from __future__ import annotations

from pathlib import Path
from typing import List

from .config import AppConfig, ensure_directories


def init_overlay(cfg: AppConfig) -> None:
    ensure_directories(cfg)


def list_overlay_files(cfg: AppConfig) -> List[Path]:
    if not cfg.paths.overlay_dir.exists():
        return []
    return sorted(p for p in cfg.paths.overlay_dir.rglob("*") if p.is_file())
