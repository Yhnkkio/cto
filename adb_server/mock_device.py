"""Mock Android device representation used by the ADB server."""

from __future__ import annotations

import itertools
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from .filesystem import MockFileSystem


@dataclass
class ProcessInfo:
    pid: int
    user: str
    name: str
    cpu: float = 0.0
    mem: float = 0.0


@dataclass
class PackageInfo:
    package: str
    path: str = ""


def _to_package_info(packages: Iterable[Dict[str, str] | str]) -> List[PackageInfo]:
    result: List[PackageInfo] = []
    for item in packages:
        if isinstance(item, str):
            result.append(PackageInfo(package=item, path="/data/app/" + item.replace(".", "_") + "-1/base.apk"))
        else:
            result.append(PackageInfo(package=item["package"], path=item.get("path", "")))
    return result


def _to_process_info(processes: Iterable[Dict[str, object]]) -> List[ProcessInfo]:
    result: List[ProcessInfo] = []
    for process in processes:
        result.append(
            ProcessInfo(
                pid=int(process.get("pid", 0)),
                user=str(process.get("user", "root")),
                name=str(process.get("name", "unknown")),
                cpu=float(process.get("cpu", 0.0)),
                mem=float(process.get("mem", 0.0)),
            )
        )
    return result


@dataclass
class DeviceMetadata:
    serial: str
    model: str
    manufacturer: str
    android_version: str
    sdk_version: str
    kernel_version: str
    state: str = "device"


class MockDevice:
    """Complete simulated Android device state."""

    def __init__(
        self,
        metadata: DeviceMetadata,
        properties: Dict[str, str],
        filesystem: MockFileSystem,
        packages: List[PackageInfo],
        processes: List[ProcessInfo],
        log_messages: Optional[List[str]] = None,
    ) -> None:
        self.metadata = metadata
        self.properties = properties
        self.filesystem = filesystem
        self.packages = packages
        self.processes = processes
        self.forwarded_ports: Dict[str, str] = {}
        self.log_messages = log_messages or [
            "01-01 00:00:00.000  1000  1000 I ActivityManager: Start proc 1000:com.android.systemui/u0a100 for service",
            "01-01 00:00:01.000  1000  1000 I PackageManager: Package manager ready",
        ]
        self._log_cursor = 0
        self._pid_counter = itertools.count(max([p.pid for p in processes], default=1000) + 1)
        self.installed_paths: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------
    @classmethod
    def from_config(cls, config: Dict[str, object]) -> "MockDevice":
        device_cfg = dict(config.get("device", {}))
        metadata = DeviceMetadata(
            serial=str(device_cfg.get("serial", "MOCK123456")),
            model=str(device_cfg.get("model", "MockPhone")),
            manufacturer=str(device_cfg.get("manufacturer", "MockMaker")),
            android_version=str(device_cfg.get("android_version", "12")),
            sdk_version=str(device_cfg.get("sdk_version", "31")),
            kernel_version=str(device_cfg.get("kernel_version", "5.4.0")),
            state=str(device_cfg.get("state", "device")),
        )

        properties = {str(k): str(v) for k, v in dict(config.get("properties", {})).items()}
        properties.setdefault("ro.product.model", metadata.model)
        properties.setdefault("ro.product.manufacturer", metadata.manufacturer)
        properties.setdefault("ro.build.version.release", metadata.android_version)
        properties.setdefault("ro.build.version.sdk", metadata.sdk_version)
        properties.setdefault("ro.serialno", metadata.serial)

        fs = MockFileSystem()
        fs.create_from_config(config.get("filesystem", []))

        packages = _to_package_info(config.get("packages", []))
        processes = _to_process_info(config.get("processes", []))
        logs = list(config.get("logs", [])) if config.get("logs") else None
        return cls(metadata, properties, fs, packages, processes, logs)

    # ------------------------------------------------------------------
    # Basic information
    # ------------------------------------------------------------------
    def get_state(self) -> str:
        return self.metadata.state

    def get_serial(self) -> str:
        return self.metadata.serial

    def get_version_string(self) -> str:
        return f"Android Debug Bridge version 1.0.41\nMock Device SDK {self.metadata.sdk_version}"

    def get_device_banner(self) -> str:
        return (
            f"device::ro.product.name={self.properties.get('ro.product.name', 'mock')};"
            f"ro.product.model={self.metadata.model};"
            f"ro.product.device={self.properties.get('ro.product.device', 'mockdevice')};"
        )

    # ------------------------------------------------------------------
    # Properties and packages
    # ------------------------------------------------------------------
    def get_property(self, name: str) -> Optional[str]:
        return self.properties.get(name)

    def set_property(self, name: str, value: str) -> None:
        self.properties[name] = value

    def list_properties(self) -> Dict[str, str]:
        return dict(sorted(self.properties.items()))

    def list_packages(self) -> List[PackageInfo]:
        return sorted(self.packages, key=lambda pkg: pkg.package)

    def install_package(self, package_path: str) -> str:
        package_name = package_path.split("/")[-1].replace(".apk", "")
        package_info = PackageInfo(package=package_name, path=package_path)
        self.packages.append(package_info)
        self.installed_paths[package_name] = package_path
        return package_name

    def uninstall_package(self, package_name: str) -> bool:
        before = len(self.packages)
        self.packages = [pkg for pkg in self.packages if pkg.package != package_name]
        removed = before != len(self.packages)
        if removed:
            self.installed_paths.pop(package_name, None)
        return removed

    # ------------------------------------------------------------------
    # Processes
    # ------------------------------------------------------------------
    def list_processes(self) -> List[ProcessInfo]:
        return sorted(self.processes, key=lambda proc: proc.pid)

    def spawn_process(self, name: str, user: str = "shell") -> ProcessInfo:
        pid = next(self._pid_counter)
        process = ProcessInfo(pid=pid, user=user, name=name)
        self.processes.append(process)
        return process

    def kill_process(self, pid: int) -> bool:
        before = len(self.processes)
        self.processes = [proc for proc in self.processes if proc.pid != pid]
        return before != len(self.processes)

    # ------------------------------------------------------------------
    # Port forwarding
    # ------------------------------------------------------------------
    def add_forward_rule(self, local: str, remote: str) -> None:
        self.forwarded_ports[local] = remote

    def remove_forward_rule(self, local: str) -> bool:
        return self.forwarded_ports.pop(local, None) is not None

    def list_forward_rules(self) -> Dict[str, str]:
        return dict(self.forwarded_ports)

    # ------------------------------------------------------------------
    # Logcat
    # ------------------------------------------------------------------
    def next_log_lines(self, count: int = 50) -> List[str]:
        if not self.log_messages:
            return []
        lines: List[str] = []
        for _ in range(count):
            line = self.log_messages[self._log_cursor % len(self.log_messages)]
            self._log_cursor += 1
            lines.append(line)
        return lines

    # ------------------------------------------------------------------
    # Reboot simulation
    # ------------------------------------------------------------------
    def reboot(self) -> None:
        self.metadata.state = "rebooting"
        self.append_log("I BootReceiver: Device reboot requested")
        time.sleep(0.01)
        self.metadata.state = "device"
        self.append_log("I BootReceiver: Device boot completed")

    def append_log(self, message: str) -> None:
        timestamp = time.strftime("%m-%d %H:%M:%S.000")
        self.log_messages.append(f"{timestamp}  1000  1000 I MockDevice: {message}")

    # ------------------------------------------------------------------
    # Filesystem helpers (proxy methods)
    # ------------------------------------------------------------------
    def read_file(self, path: str) -> bytes:
        return self.filesystem.read_file(path)

    def write_file(self, path: str, data: bytes, append: bool = False) -> None:
        self.filesystem.write_file(path, data, append=append)

    def mkdir(self, path: str, parents: bool = False) -> None:
        self.filesystem.mkdir(path, parents=parents)

    def remove(self, path: str, recursive: bool = False) -> None:
        self.filesystem.remove(path, recursive=recursive)

    def move(self, source: str, destination: str) -> None:
        self.filesystem.move(source, destination)

    def copy(self, source: str, destination: str, recursive: bool = False) -> None:
        self.filesystem.copy(source, destination, recursive=recursive)

    def chmod(self, path: str, mode: int) -> None:
        self.filesystem.set_permissions(path, mode)

    def chown(self, path: str, owner: str, group: Optional[str] = None) -> None:
        self.filesystem.set_owner(path, owner, group)
