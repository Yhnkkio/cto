"""In-memory filesystem used by the mock ADB device."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Dict, Iterable, Iterator, List, Optional, Set, Tuple


@dataclass
class FileEntry:
    """Representation of a file system entry."""

    path: PurePosixPath
    node_type: str  # 'file', 'dir', 'symlink'
    permissions: int = 0o755
    owner: str = "root"
    group: str = "root"
    content: bytearray = field(default_factory=bytearray)
    link_target: Optional[PurePosixPath] = None

    def clone(self, new_path: PurePosixPath) -> "FileEntry":
        return FileEntry(
            path=new_path,
            node_type=self.node_type,
            permissions=self.permissions,
            owner=self.owner,
            group=self.group,
            content=bytearray(self.content),
            link_target=self.link_target,
        )


class FilesystemError(RuntimeError):
    """Raised when an invalid filesystem operation is requested."""


class MockFileSystem:
    """A very small POSIX-like filesystem with permission metadata."""

    def __init__(self) -> None:
        self.entries: Dict[PurePosixPath, FileEntry] = {}
        self.children: Dict[PurePosixPath, Set[PurePosixPath]] = {}
        # Ensure root exists
        root_path = PurePosixPath("/")
        self.entries[root_path] = FileEntry(path=root_path, node_type="dir")
        self.children[root_path] = set()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _normalize(self, path: PurePosixPath | str, cwd: PurePosixPath | str | None = None) -> PurePosixPath:
        if isinstance(path, str):
            path = PurePosixPath(path)
        if isinstance(cwd, str):
            cwd = PurePosixPath(cwd)
        if cwd is None:
            cwd = PurePosixPath("/")
        if not path.is_absolute():
            path = cwd.joinpath(path)
        parts: List[str] = []
        for part in path.parts:
            if part in {"", "/", "."}:
                continue
            if part == "..":
                if parts:
                    parts.pop()
                continue
            parts.append(part)
        return PurePosixPath("/" + "/".join(parts))

    def _ensure_directory(self, path: PurePosixPath) -> None:
        if path == PurePosixPath("/"):
            return
        if path in self.entries:
            entry = self.entries[path]
            if entry.node_type != "dir":
                raise FilesystemError(f"Path exists and is not a directory: {path}")
            return
        parent = path.parent
        self._ensure_directory(parent)
        entry = FileEntry(path=path, node_type="dir")
        self.entries[path] = entry
        self.children.setdefault(path, set())
        self.children.setdefault(parent, set()).add(path)

    def _ensure_parent_dirs(self, path: PurePosixPath) -> None:
        parent = path.parent
        if parent == path:
            return
        self._ensure_directory(parent)

    def _add_entry(self, entry: FileEntry) -> None:
        if entry.path in self.entries:
            raise FilesystemError(f"Path already exists: {entry.path}")
        parent = entry.path.parent if entry.path != PurePosixPath("/") else PurePosixPath("/")
        if parent not in self.entries:
            self._ensure_directory(parent)
        self.entries[entry.path] = entry
        self.children.setdefault(entry.path, set())
        self.children.setdefault(parent, set()).add(entry.path)

    def _remove_entry(self, path: PurePosixPath) -> None:
        entry = self.entries.pop(path, None)
        if entry is None:
            raise FilesystemError(f"Path not found: {path}")
        parent = path.parent if path != PurePosixPath("/") else PurePosixPath("/")
        if parent in self.children:
            self.children[parent].discard(path)
        self.children.pop(path, None)

    def _resolve_symlink(self, entry: FileEntry, follow: bool = True) -> FileEntry:
        if entry.node_type == "symlink" and follow and entry.link_target:
            target = self._normalize(entry.link_target)
            if target not in self.entries:
                raise FilesystemError(f"Dangling symlink: {entry.path} -> {entry.link_target}")
            return self._resolve_symlink(self.entries[target], follow)
        return entry

    # ------------------------------------------------------------------
    # Creation helpers
    # ------------------------------------------------------------------
    def create_from_config(self, definitions: Iterable[Dict[str, object]]) -> None:
        for definition in definitions:
            path = PurePosixPath(str(definition["path"]))
            node_type = str(definition.get("type", "file"))
            permissions = int(str(definition.get("permissions", "0755")), 8)
            owner = str(definition.get("owner", "root"))
            group = str(definition.get("group", "root"))
            if node_type == "dir":
                entry = FileEntry(path=path, node_type="dir", permissions=permissions, owner=owner, group=group)
                if path not in self.entries:
                    self._add_entry(entry)
                else:
                    existing = self.entries[path]
                    existing.permissions = permissions
                    existing.owner = owner
                    existing.group = group
                continue
            if node_type == "file":
                content = definition.get("content", b"")
                if isinstance(content, str):
                    data = content.encode("utf-8")
                elif isinstance(content, bytes):
                    data = content
                else:
                    raise FilesystemError(f"Unsupported content type for {path}")
                entry = FileEntry(
                    path=path,
                    node_type="file",
                    permissions=permissions,
                    owner=owner,
                    group=group,
                    content=bytearray(data),
                )
                if path in self.entries:
                    self.remove(path)
                self._ensure_parent_dirs(path)
                self._add_entry(entry)
                continue
            if node_type == "symlink":
                target = definition.get("target")
                if not target:
                    raise FilesystemError(f"Symlink requires target: {path}")
                entry = FileEntry(
                    path=path,
                    node_type="symlink",
                    permissions=permissions,
                    owner=owner,
                    group=group,
                    link_target=self._normalize(str(target)),
                )
                if path in self.entries:
                    self.remove(path)
                self._ensure_parent_dirs(path)
                self._add_entry(entry)
                continue
            raise FilesystemError(f"Unsupported node type '{node_type}' for {path}")

    # ------------------------------------------------------------------
    # Introspection helpers
    # ------------------------------------------------------------------
    def exists(self, path: str | PurePosixPath, cwd: str | PurePosixPath | None = None) -> bool:
        normalized = self._normalize(path, cwd)
        return normalized in self.entries

    def get_entry(self, path: str | PurePosixPath, cwd: str | PurePosixPath | None = None, follow: bool = True) -> FileEntry:
        normalized = self._normalize(path, cwd)
        if normalized not in self.entries:
            raise FilesystemError(f"Path not found: {normalized}")
        entry = self.entries[normalized]
        if follow:
            return self._resolve_symlink(entry)
        return entry

    def list_dir(self, path: str | PurePosixPath, cwd: str | PurePosixPath | None = None) -> List[FileEntry]:
        entry = self.get_entry(path, cwd)
        if entry.node_type != "dir":
            raise FilesystemError(f"Not a directory: {entry.path}")
        children = self.children.get(entry.path, set())
        return [self._resolve_symlink(self.entries[child], follow=False) for child in sorted(children)]

    # ------------------------------------------------------------------
    # Mutating operations
    # ------------------------------------------------------------------
    def read_file(self, path: str | PurePosixPath, cwd: str | PurePosixPath | None = None) -> bytes:
        entry = self.get_entry(path, cwd)
        if entry.node_type != "file":
            raise FilesystemError(f"Not a file: {entry.path}")
        return bytes(entry.content)

    def write_file(
        self,
        path: str | PurePosixPath,
        data: bytes,
        cwd: str | PurePosixPath | None = None,
        mode: int = 0o664,
        owner: str = "shell",
        group: str = "shell",
        append: bool = False,
    ) -> None:
        normalized = self._normalize(path, cwd)
        if normalized in self.entries:
            entry = self.get_entry(normalized)
            if entry.node_type != "file":
                raise FilesystemError(f"Cannot write to non-file: {normalized}")
            if append:
                entry.content.extend(data)
            else:
                entry.content = bytearray(data)
            entry.permissions = mode
            entry.owner = owner
            entry.group = group
            return
        self._ensure_parent_dirs(normalized)
        entry = FileEntry(
            path=normalized,
            node_type="file",
            permissions=mode,
            owner=owner,
            group=group,
            content=bytearray(data),
        )
        self._add_entry(entry)

    def mkdir(
        self,
        path: str | PurePosixPath,
        cwd: str | PurePosixPath | None = None,
        mode: int = 0o755,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        normalized = self._normalize(path, cwd)
        if normalized in self.entries:
            entry = self.entries[normalized]
            if entry.node_type != "dir" and not exist_ok:
                raise FilesystemError(f"Path exists and is not a directory: {normalized}")
            return
        parent = normalized.parent
        if parent not in self.entries:
            if parents:
                self.mkdir(parent, mode=mode, parents=True, exist_ok=True)
            else:
                raise FilesystemError(f"Parent directory does not exist: {parent}")
        entry = FileEntry(path=normalized, node_type="dir", permissions=mode)
        self._add_entry(entry)

    def remove(
        self,
        path: str | PurePosixPath,
        cwd: str | PurePosixPath | None = None,
        recursive: bool = False,
    ) -> None:
        normalized = self._normalize(path, cwd)
        entry = self.get_entry(normalized, follow=False)
        if entry.node_type == "dir" and self.children.get(entry.path) and not recursive:
            raise FilesystemError(f"Directory not empty: {normalized}")
        if entry.node_type == "dir" and recursive:
            for child in list(self.children.get(entry.path, set())):
                self.remove(child, recursive=True)
        self._remove_entry(entry.path)

    def copy(
        self,
        source: str | PurePosixPath,
        destination: str | PurePosixPath,
        cwd: str | PurePosixPath | None = None,
        recursive: bool = False,
    ) -> None:
        src_entry = self.get_entry(source, cwd, follow=False)
        dest_path = self._normalize(destination, cwd)
        if src_entry.node_type == "dir" and not recursive:
            raise FilesystemError("Recursive flag required to copy directories")
        if src_entry.node_type == "dir":
            self.mkdir(dest_path, parents=True, exist_ok=True)
            for child in self.children.get(src_entry.path, set()):
                rel = child.relative_to(src_entry.path)
                self.copy(src_entry.path / rel, dest_path / rel, recursive=True)
            return
        data = bytes(src_entry.content)
        self.write_file(dest_path, data, mode=src_entry.permissions, owner=src_entry.owner, group=src_entry.group)

    def move(
        self,
        source: str | PurePosixPath,
        destination: str | PurePosixPath,
        cwd: str | PurePosixPath | None = None,
    ) -> None:
        src_entry = self.get_entry(source, cwd, follow=False)
        dest_path = self._normalize(destination, cwd)
        if dest_path in self.entries:
            self.remove(dest_path, recursive=True)
        self._ensure_parent_dirs(dest_path)
        # Gather all entries within the subtree (including the source itself)
        subtree = []
        for path, entry in list(self.entries.items()):
            if path == src_entry.path:
                new_path = dest_path
            else:
                try:
                    rel = path.relative_to(src_entry.path)
                except ValueError:
                    continue
                new_path = dest_path / rel
            subtree.append((path, new_path, entry))
        # Remove existing entries starting from the deepest paths
        for path, _, _ in sorted(subtree, key=lambda item: len(item[0].parts), reverse=True):
            self._remove_entry(path)
        # Re-create entries at their new location from top to bottom
        for _, new_path, entry in sorted(subtree, key=lambda item: len(item[1].parts)):
            cloned = entry.clone(new_path)
            if cloned.node_type == "symlink" and cloned.link_target:
                cloned.link_target = self._normalize(cloned.link_target)
            self._add_entry(cloned)

    def set_permissions(self, path: str | PurePosixPath, mode: int, cwd: str | PurePosixPath | None = None) -> None:
        entry = self.get_entry(path, cwd, follow=False)
        entry.permissions = mode

    def set_owner(
        self,
        path: str | PurePosixPath,
        owner: str,
        group: Optional[str] = None,
        cwd: str | PurePosixPath | None = None,
    ) -> None:
        entry = self.get_entry(path, cwd, follow=False)
        entry.owner = owner
        if group is not None:
            entry.group = group

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------
    def format_permissions(self, mode: int, node_type: str) -> str:
        prefix = {"file": "-", "dir": "d", "symlink": "l"}.get(node_type, "-")
        bits = ["r", "w", "x"] * 3
        result = []
        for idx in range(9):
            if mode & (1 << (8 - idx)):
                result.append(bits[idx])
            else:
                result.append("-")
        return prefix + "".join(result)

    def walk(self, start: str | PurePosixPath = "/") -> Iterator[Tuple[PurePosixPath, List[PurePosixPath]]]:
        start_path = self._normalize(start)
        stack = [start_path]
        while stack:
            current = stack.pop()
            children = sorted(self.children.get(current, set()))
            yield current, children
            for child in reversed(children):
                if self.entries[child].node_type == "dir":
                    stack.append(child)
