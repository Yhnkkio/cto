from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple


@dataclass(slots=True)
class FSStats:
    mode: int
    size: int
    mtime: int
    is_dir: bool


def _normalize(root: Path, cwd: Path, p: str) -> Path:
    # Accept absolute ("/x") or relative ("x"); both resolved within overlay root.
    if p.startswith("/"):
        rel = p[1:]
        abs_p = root / rel
    else:
        abs_p = cwd / p
    # Normalize
    abs_p = abs_p.resolve()
    root = root.resolve()
    if not str(abs_p).startswith(str(root)):
        return root  # clamp to root
    return abs_p


class OverlayFS:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def get_root(self) -> Path:
        return self.root.resolve()

    def resolve(self, cwd: Path, p: str) -> Path:
        return _normalize(self.root, cwd, p)

    def listdir(self, p: Path) -> Iterable[Path]:
        if not p.exists():
            raise FileNotFoundError
        return sorted(p.iterdir(), key=lambda x: x.name)

    def stat(self, p: Path) -> FSStats:
        st = p.stat()
        return FSStats(mode=st.st_mode, size=st.st_size, mtime=int(st.st_mtime), is_dir=p.is_dir())

    def mkdir_p(self, p: Path) -> None:
        p.mkdir(parents=True, exist_ok=True)

    def rm(self, p: Path, recursive: bool = False) -> None:
        if not p.exists():
            raise FileNotFoundError
        if p.is_dir():
            if recursive:
                shutil.rmtree(p)
            else:
                os.rmdir(p)
        else:
            p.unlink()

    def cat(self, p: Path) -> bytes:
        with open(p, "rb") as f:
            return f.read()

    def write(self, p: Path, data: bytes, append: bool = False) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        mode = "ab" if append else "wb"
        with open(p, mode) as f:
            f.write(data)

    def touch(self, p: Path) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "ab"):
            os.utime(p, None)

    def copy(self, src: Path, dst: Path) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)

    def move(self, src: Path, dst: Path) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))

    def set_mtime(self, p: Path, mtime: int) -> None:
        try:
            os.utime(p, (mtime, mtime))
        except Exception:
            pass

    def list_entries(self, p: Path) -> Iterable[Tuple[str, FSStats]]:
        for child in self.listdir(p):
            st = self.stat(child)
            yield child.name, st
