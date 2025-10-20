from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


def setup_logging(level: str = "INFO", log_dir: Optional[Path] = None) -> None:
    logs_dir = log_dir or Path.cwd() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "adb_overlay_server.log"

    log_level = getattr(logging, str(level).upper(), logging.INFO)

    fmt = (
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
    datefmt = "%Y-%m-%d %H:%M:%S"

    # Remove any existing handlers to avoid duplicate logs in tests/dev reload
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    handlers = [
        logging.StreamHandler(),
        RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"),
    ]

    logging.basicConfig(level=log_level, format=fmt, datefmt=datefmt, handlers=handlers)
