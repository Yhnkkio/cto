from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict


@dataclass
class CommandResponse:
    stdout: bytes
    stderr: bytes
    exit_code: int


class CommandSim:
    def __init__(self, path: Path | None):
        self.map: Dict[str, CommandResponse] = {}
        if path is not None:
            self._load(path)

    def _load(self, path: Path) -> None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return
        if not isinstance(data, dict):
            return
        for k, v in data.items():
            if not isinstance(v, dict):
                continue
            stdout = v.get("stdout", "").encode("utf-8")
            stderr = v.get("stderr", "").encode("utf-8")
            code = int(v.get("exit_code", 0))
            self.map[str(k)] = CommandResponse(stdout, stderr, code)

    def match(self, cwd: str, cmdline: str) -> Optional[CommandResponse]:
        # Highest priority: exact match on the command string; ignore CWD for now
        return self.map.get(cmdline)
