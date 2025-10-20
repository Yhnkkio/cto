from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from server.overlay_fs import OverlayFS
from server.props import Props
from server.shell.redirection import parse_redirection


@dataclass
class ShellResult:
    stdout: bytes
    stderr: bytes
    exit_code: int = 0


class Shell:
    def __init__(self, fs: OverlayFS, props: Props):
        self.fs = fs
        self.props = props

    def run(self, cwd: Path, cmdline: str) -> Tuple[Path, ShellResult]:
        try:
            argv = shlex.split(cmdline, posix=True)
        except Exception:
            return cwd, ShellResult(b"", f"sh: syntax error\n".encode(), 2)
        if not argv:
            return cwd, ShellResult(b"", b"", 0)
        # Redirection handling
        parsed = parse_redirection(argv)
        argv = parsed.argv

        cmd = argv[0]
        args = argv[1:]
        out = b""
        err = b""
        code = 0
        new_cwd = cwd

        try:
            if cmd == "pwd":
                out = ("/" + str(new_cwd.relative_to(self.fs.get_root())).replace("\\", "/").lstrip("/") + "\n").encode()
            elif cmd == "cd":
                target = args[0] if args else "/"
                new_cwd = self.fs.resolve(cwd, target)
                if not new_cwd.exists() or not new_cwd.is_dir():
                    err = f"cd: {target}: No such file or directory\n".encode()
                    code = 1
                    new_cwd = cwd
            elif cmd == "ls":
                target = args[0] if args else "."
                path = self.fs.resolve(cwd, target)
                if not path.exists():
                    err = f"ls: {target}: No such file or directory\n".encode()
                    code = 1
                elif path.is_dir():
                    names = [child.name for child in self.fs.listdir(path)]
                    out = ("\n".join(names) + ("\n" if names else "")).encode()
                else:
                    out = (path.name + "\n").encode()
            elif cmd == "cat":
                if not args:
                    out = b""
                else:
                    path = self.fs.resolve(cwd, args[0])
                    if not path.exists() or path.is_dir():
                        err = f"cat: {args[0]}: No such file or directory\n".encode()
                        code = 1
                    else:
                        out = self.fs.cat(path)
            elif cmd == "echo":
                text = " ".join(args).encode()
                out = text + b"\n"
            elif cmd == "mkdir":
                recursive = False
                paths = []
                for a in args:
                    if a == "-p":
                        recursive = True
                    else:
                        paths.append(a)
                for p in paths:
                    rp = self.fs.resolve(cwd, p)
                    if recursive:
                        self.fs.mkdir_p(rp)
                    else:
                        rp.mkdir()
            elif cmd == "rm":
                recursive = False
                paths = []
                for a in args:
                    if a == "-r" or a == "-R":
                        recursive = True
                    else:
                        paths.append(a)
                for p in paths:
                    rp = self.fs.resolve(cwd, p)
                    try:
                        self.fs.rm(rp, recursive=recursive)
                    except FileNotFoundError:
                        err += f"rm: {p}: No such file or directory\n".encode()
                        code = 1
            elif cmd == "touch":
                for p in args:
                    rp = self.fs.resolve(cwd, p)
                    self.fs.touch(rp)
            elif cmd == "cp":
                if len(args) < 2:
                    err = b"cp: missing file operand\n"
                    code = 1
                else:
                    src = self.fs.resolve(cwd, args[0])
                    dst = self.fs.resolve(cwd, args[1])
                    if not src.exists():
                        err = f"cp: {args[0]}: No such file or directory\n".encode()
                        code = 1
                    else:
                        self.fs.copy(src, dst)
            elif cmd == "mv":
                if len(args) < 2:
                    err = b"mv: missing file operand\n"
                    code = 1
                else:
                    src = self.fs.resolve(cwd, args[0])
                    dst = self.fs.resolve(cwd, args[1])
                    if not src.exists():
                        err = f"mv: {args[0]}: No such file or directory\n".encode()
                        code = 1
                    else:
                        self.fs.move(src, dst)
            elif cmd == "getprop":
                if not args:
                    # Dump all properties
                    lines = [f"[{k}]: [{v}]" for k, v in sorted(self.props.data.items())]
                    out = ("\n".join(lines) + "\n").encode()
                else:
                    out = (self.props.get(args[0]) + "\n").encode()
            elif cmd == "setprop":
                if len(args) < 2:
                    err = b"setprop: invalid arguments\n"
                    code = 1
                else:
                    self.props.set(args[0], " ".join(args[1:]))
            else:
                err = f"sh: {cmd}: not found\n".encode()
                code = 127
        except Exception as e:
            err = f"sh: {cmd}: {e}\n".encode()
            code = 1

        # Redirection
        if parsed.redir is not None:
            target = self.fs.resolve(cwd, parsed.redir.path)
            self.fs.write(target, out, append=parsed.redir.append)
            out = b""

        return new_cwd, ShellResult(out, err, code)
