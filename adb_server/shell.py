"""Shell environment that mimics a subset of the Android shell."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable, List

from .filesystem import FileEntry, FilesystemError
from .mock_device import MockDevice


@dataclass
class ShellResponse:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0

    def as_text(self) -> str:
        if self.stderr:
            return self.stdout + self.stderr
        return self.stdout


class ShellError(RuntimeError):
    """Raised when a shell command fails."""


class ShellEnvironment:
    """Stateful shell session for a mock Android device."""

    def __init__(self, device: MockDevice, user: str = "shell") -> None:
        self.device = device
        self.user = user
        self.cwd = PurePosixPath("/data") if user == "shell" else PurePosixPath("/")
        if not self.device.filesystem.exists(self.cwd):
            self.cwd = PurePosixPath("/")
        self.history: List[str] = []
        self.prompt_template = "{user}@{device}:{cwd}$ "

    # ------------------------------------------------------------------
    # Prompt & history
    # ------------------------------------------------------------------
    @property
    def prompt(self) -> str:
        device_name = self.device.properties.get("ro.product.device", "mock")
        cwd_display = str(self.cwd)
        if not cwd_display:
            cwd_display = "/"
        return self.prompt_template.format(user=self.user, device=device_name, cwd=cwd_display)

    def add_history(self, command: str) -> None:
        if command.strip():
            self.history.append(command)

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------
    def execute(self, command: str) -> ShellResponse:
        command = command.strip()
        if not command:
            return ShellResponse(stdout="")
        self.add_history(command)
        try:
            responses = [self._execute_single(tokens) for tokens in self._split_commands(command)]
        except ShellError as exc:
            return ShellResponse(stderr=str(exc) + "\n", exit_code=1)
        stdout = "".join(response.stdout for response in responses)
        stderr = "".join(response.stderr for response in responses)
        exit_code = responses[-1].exit_code if responses else 0
        return ShellResponse(stdout=stdout, stderr=stderr, exit_code=exit_code)

    def _split_commands(self, command: str) -> List[List[str]]:
        tokens = shlex.split(command, posix=True)
        commands: List[List[str]] = []
        current: List[str] = []
        for token in tokens:
            if token == ";":
                if current:
                    commands.append(current)
                    current = []
                continue
            current.append(token)
        if current:
            commands.append(current)
        if not commands:
            raise ShellError("No command provided")
        return commands

    def _execute_single(self, tokens: List[str]) -> ShellResponse:
        if not tokens:
            return ShellResponse()
        cmd = tokens[0]
        args = tokens[1:]
        handler_name = f"cmd_{cmd.replace('-', '_')}"
        handler = getattr(self, handler_name, None)
        if handler is None:
            # fallback to toy busybox style message
            return ShellResponse(stderr=f"/system/bin/sh: {cmd}: not found\n", exit_code=127)
        return handler(args)

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------
    def cmd_pwd(self, args: List[str]) -> ShellResponse:
        return ShellResponse(stdout=str(self.cwd) + "\n")

    def cmd_cd(self, args: List[str]) -> ShellResponse:
        target = args[0] if args else "/"
        entry = self.device.filesystem.get_entry(target, self.cwd)
        if entry.node_type != "dir":
            raise ShellError(f"cd: not a directory: {target}")
        self.cwd = entry.path
        return ShellResponse()

    def cmd_ls(self, args: List[str]) -> ShellResponse:
        long_format = False
        all_entries = False
        targets: List[str] = []
        for arg in args:
            if arg.startswith("-"):
                if "l" in arg:
                    long_format = True
                if "a" in arg:
                    all_entries = True
            else:
                targets.append(arg)
        if not targets:
            targets = ["."]
        outputs: List[str] = []
        for target in targets:
            entry = self.device.filesystem.get_entry(target, self.cwd, follow=False)
            if entry.node_type == "dir":
                entries = self.device.filesystem.list_dir(target, self.cwd)
                listing = self._format_ls(entries, long_format, all_entries)
                outputs.append(listing)
            else:
                outputs.append(self._format_ls([entry], long_format, all_entries))
        return ShellResponse(stdout="".join(outputs))

    def _format_ls(
        self,
        entries: Iterable[FileEntry],
        long_format: bool,
        all_entries: bool,
    ) -> str:
        lines: List[str] = []
        for entry in entries:
            name = entry.path.name or "/"
            if not all_entries and name.startswith(".") and name not in {".", ".."}:
                continue
            if long_format:
                size = len(entry.content) if entry.node_type == "file" else 0
                perms = self.device.filesystem.format_permissions(entry.permissions, entry.node_type)
                lines.append(f"{perms} {entry.owner} {entry.group} {size:>6} {name}")
            else:
                lines.append(name)
        suffix = "\n" if long_format else "  \n"
        if long_format:
            return "\n".join(lines) + ("\n" if lines else "")
        if not lines:
            return "\n"
        return "  ".join(lines) + "\n"

    def cmd_cat(self, args: List[str]) -> ShellResponse:
        if not args:
            raise ShellError("cat: missing operand")
        outputs = []
        for path in args:
            data = self.device.filesystem.read_file(path, self.cwd)
            outputs.append(data.decode("utf-8"))
        return ShellResponse(stdout="".join(outputs))

    def cmd_echo(self, args: List[str]) -> ShellResponse:
        newline = True
        output_args: List[str] = []
        for arg in args:
            if arg == "-n":
                newline = False
                continue
            output_args.append(arg)
        text = " ".join(output_args)
        return ShellResponse(stdout=text + ("\n" if newline else ""))

    def cmd_mkdir(self, args: List[str]) -> ShellResponse:
        if not args:
            raise ShellError("mkdir: missing operand")
        parents = any(arg == "-p" for arg in args)
        paths = [arg for arg in args if arg != "-p"]
        for path in paths:
            self.device.filesystem.mkdir(path, self.cwd, parents=parents)
        return ShellResponse()

    def cmd_rm(self, args: List[str]) -> ShellResponse:
        if not args:
            raise ShellError("rm: missing operand")
        recursive = any(arg == "-r" or arg == "-rf" for arg in args)
        force = any(arg in {"-f", "-rf"} for arg in args)
        paths = [arg for arg in args if not arg.startswith("-")]
        for path in paths:
            try:
                self.device.filesystem.remove(path, self.cwd, recursive=recursive)
            except FilesystemError as exc:
                if force:
                    continue
                raise ShellError(f"rm: {exc}") from exc
        return ShellResponse()

    def cmd_cp(self, args: List[str]) -> ShellResponse:
        if len(args) < 2:
            raise ShellError("cp: missing operand")
        recursive = any(arg == "-r" for arg in args)
        filtered = [arg for arg in args if not arg.startswith("-")]
        *sources, destination = filtered
        for source in sources:
            dst = destination
            entry = self.device.filesystem.get_entry(destination, self.cwd) if self.device.filesystem.exists(destination, self.cwd) else None
            if entry and entry.node_type == "dir":
                dst = str(PurePosixPath(destination) / PurePosixPath(source).name)
            self.device.filesystem.copy(source, dst, self.cwd, recursive=recursive)
        return ShellResponse()

    def cmd_mv(self, args: List[str]) -> ShellResponse:
        if len(args) < 2:
            raise ShellError("mv: missing operand")
        *sources, destination = args
        for source in sources:
            dst = destination
            if self.device.filesystem.exists(destination, self.cwd):
                entry = self.device.filesystem.get_entry(destination, self.cwd)
                if entry.node_type == "dir":
                    dst = str(entry.path / PurePosixPath(source).name)
            self.device.filesystem.move(source, dst, self.cwd)
        return ShellResponse()

    def cmd_chmod(self, args: List[str]) -> ShellResponse:
        if len(args) < 2:
            raise ShellError("chmod: missing operand")
        mode_text, *paths = args
        try:
            mode = int(mode_text, 8)
        except ValueError as exc:
            raise ShellError("chmod: invalid mode") from exc
        for path in paths:
            self.device.filesystem.set_permissions(path, mode, self.cwd)
        return ShellResponse()

    def cmd_chown(self, args: List[str]) -> ShellResponse:
        if len(args) < 2:
            raise ShellError("chown: missing operand")
        owner_spec, *paths = args
        if ":" in owner_spec:
            owner, group = owner_spec.split(":", 1)
        else:
            owner, group = owner_spec, None
        for path in paths:
            self.device.filesystem.set_owner(path, owner, group, self.cwd)
        return ShellResponse()

    def cmd_ps(self, args: List[str]) -> ShellResponse:
        header = "USER     PID   NAME\n"
        rows = [f"{proc.user:<8} {proc.pid:<5} {proc.name}" for proc in self.device.list_processes()]
        return ShellResponse(stdout=header + "\n".join(rows) + ("\n" if rows else ""))

    def cmd_top(self, args: List[str]) -> ShellResponse:
        # Provide a simplified snapshot similar to `top -n 1`
        header = "PID   USER     CPU%   MEM%   COMMAND\n"
        rows = [
            f"{proc.pid:<5} {proc.user:<8} {proc.cpu:>4.1f}   {proc.mem:>4.1f}   {proc.name}"
            for proc in self.device.list_processes()
        ]
        return ShellResponse(stdout=header + "\n".join(rows) + ("\n" if rows else ""))

    def cmd_getprop(self, args: List[str]) -> ShellResponse:
        if not args:
            lines = [f"[{key}]: [{value}]" for key, value in self.device.list_properties().items()]
            return ShellResponse(stdout="\n".join(lines) + ("\n" if lines else ""))
        value = self.device.get_property(args[0]) or ""
        return ShellResponse(stdout=value + "\n")

    def cmd_setprop(self, args: List[str]) -> ShellResponse:
        if len(args) < 2:
            raise ShellError("setprop: usage: setprop <key> <value>")
        key, value = args[0], " ".join(args[1:])
        self.device.set_property(key, value)
        return ShellResponse()

    def cmd_pm(self, args: List[str]) -> ShellResponse:
        if not args:
            raise ShellError("pm: missing command")
        subcommand, *rest = args
        if subcommand == "list" and rest and rest[0] == "packages":
            lines = [f"package:{pkg.package}" for pkg in self.device.list_packages()]
            return ShellResponse(stdout="\n".join(lines) + ("\n" if lines else ""))
        if subcommand == "path" and rest:
            package = rest[0]
            for pkg in self.device.list_packages():
                if pkg.package == package:
                    return ShellResponse(stdout=f"package:{pkg.path}\n")
            return ShellResponse(stderr=f"Package {package} not found\n", exit_code=1)
        if subcommand == "install" and rest:
            apk_path = rest[-1]
            package_name = self.device.install_package(apk_path)
            return ShellResponse(stdout=f"Success: {package_name}\n")
        if subcommand == "uninstall" and rest:
            package = rest[0]
            if self.device.uninstall_package(package):
                return ShellResponse(stdout="Success\n")
            return ShellResponse(stderr=f"Failure [NOT_INSTALLED]\n", exit_code=1)
        return ShellResponse(stderr=f"pm: unknown command {subcommand}\n", exit_code=1)

    def cmd_logcat(self, args: List[str]) -> ShellResponse:
        lines = self.device.next_log_lines(50)
        return ShellResponse(stdout="\n".join(lines) + ("\n" if lines else ""))

    def cmd_am(self, args: List[str]) -> ShellResponse:
        if not args:
            raise ShellError("am: missing command")
        subcommand, *rest = args
        if subcommand == "start" and rest:
            component = rest[-1]
            self.device.spawn_process(component, user="u0a100")
            return ShellResponse(stdout=f"Starting: Intent {{ {component} }}\n")
        if subcommand == "broadcast" and rest:
            action = rest[-1]
            return ShellResponse(stdout=f"Broadcast completed: {action}\n")
        return ShellResponse(stderr=f"am: unknown command {subcommand}\n", exit_code=1)

    def cmd_history(self, args: List[str]) -> ShellResponse:
        lines = [f"{idx + 1}  {cmd}" for idx, cmd in enumerate(self.history)]
        return ShellResponse(stdout="\n".join(lines) + ("\n" if lines else ""))

    def cmd_exit(self, args: List[str]) -> ShellResponse:
        return ShellResponse(stderr="exit\n", exit_code=0)

    def cmd_true(self, args: List[str]) -> ShellResponse:  # pragma: no cover - trivial
        return ShellResponse(exit_code=0)

    def cmd_false(self, args: List[str]) -> ShellResponse:  # pragma: no cover - trivial
        return ShellResponse(exit_code=1)

    def cmd_whoami(self, args: List[str]) -> ShellResponse:
        return ShellResponse(stdout=self.user + "\n")

    def cmd_id(self, args: List[str]) -> ShellResponse:
        return ShellResponse(stdout=f"uid=2000({self.user}) gid=2000({self.user}) groups=2000({self.user})\n")
