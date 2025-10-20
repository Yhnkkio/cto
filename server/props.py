from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict


DEFAULT_PROPS = {
    "ro.product.manufacturer": "Google",
    "ro.product.brand": "google",
    "ro.product.model": "Pixel 7",
    "ro.serialno": "emu-00000001",
    "ro.product.name": "aosp_cf_x86_64_phone",
    "ro.build.version.sdk": "34",
}


@dataclass
class Props:
    data: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None) -> "Props":
        data = DEFAULT_PROPS.copy()
        if path is None:
            return cls(data)
        try:
            with open(path, "r", encoding="utf-8") as f:
                user = json.load(f)
                if isinstance(user, dict):
                    for k, v in user.items():
                        data[str(k)] = str(v)
        except FileNotFoundError:
            pass
        return cls(data)

    def get(self, key: str) -> str:
        return self.data.get(key, "")

    def set(self, key: str, value: str) -> None:
        self.data[key] = value

    def to_banner(self) -> bytes:
        parts = [
            f"device::ro.product.name={self.get('ro.product.name')};" \
            f"ro.product.model={self.get('ro.product.model')};" \
            f"ro.product.manufacturer={self.get('ro.product.manufacturer')};" \
            f"ro.serialno={self.get('ro.serialno')};",
            # Keep features minimal to stay compatible with v1 services we implement
            "features=abb_exec,apex,cmd,stat,ls,shell,track_app"  # basic feature set
        ]
        return ";".join(parts).encode("utf-8")
