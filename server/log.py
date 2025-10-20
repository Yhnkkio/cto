from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

_log_dir: Optional[Path] = None


def init_log_dir(path: Path) -> None:
    global _log_dir
    path.mkdir(parents=True, exist_ok=True)
    _log_dir = path


class ConnLogger:
    def __init__(self, name: str):
        assert _log_dir is not None
        ts = time.strftime("%Y%m%d-%H%M%S")
        self.path = _log_dir / f"{ts}-{name}.jsonl"
        self.fp = open(self.path, "a", encoding="utf-8")

    def log(self, event: str, **fields: Any) -> None:
        rec: Dict[str, Any] = {"ts": time.time(), "event": event}
        rec.update(fields)
        self.fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.fp.flush()

    def close(self) -> None:
        try:
            self.fp.close()
        except Exception:
            pass
