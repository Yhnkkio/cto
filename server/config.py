from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Config:
    mode: str = "device"
    device_port: int = 5555
    host_port: int = 5037
    serial: str = "emu-00000001"
    overlay_path: Path = Path("overlay")
    log_dir: Path = Path("logs")
    mdns: bool = False
