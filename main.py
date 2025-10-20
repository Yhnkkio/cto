from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from server.config import Config
from server.device_server import AdbDeviceTCPServer
from server.log import init_log_dir
from server.discovery.mdns import MdnsAdvertiser


async def run_device(cfg: Config) -> None:
    init_log_dir(cfg.log_dir)
    server = AdbDeviceTCPServer(cfg)

    mdns = None
    if cfg.mdns:
        mdns = MdnsAdvertiser(cfg.device_port, cfg.serial)
        await mdns.start()

    try:
        await server.start()
    finally:
        if mdns is not None:
            await mdns.stop()


def parse_args() -> Config:
    parser = argparse.ArgumentParser(description="Python ADB server")
    parser.add_argument("--mode", choices=["device", "host", "both"], default=os.getenv("ADB_MODE", "device"))
    parser.add_argument("--device-port", type=int, default=int(os.getenv("ADB_DEVICE_PORT", "5555")))
    parser.add_argument("--host-port", type=int, default=int(os.getenv("ADB_HOST_PORT", "5037")))
    parser.add_argument("--serial", default=os.getenv("ADB_SERIAL", "emu-00000001"))
    parser.add_argument("--overlay", default=os.getenv("ADB_OVERLAY", str(Path(__file__).parent / "overlay")))
    parser.add_argument("--log-dir", default=os.getenv("ADB_LOG_DIR", str(Path(__file__).parent / "logs")))
    parser.add_argument("--mdns", action="store_true", default=os.getenv("ADB_MDNS", "0") in ("1", "true", "yes"))

    args = parser.parse_args()
    return Config(
        mode=args.mode,
        device_port=args.device_port,
        host_port=args.host_port,
        serial=args.serial,
        overlay_path=Path(args.overlay),
        log_dir=Path(args.log_dir),
        mdns=args.mdns,
    )


async def main_async():
    cfg = parse_args()

    if cfg.mode == "device":
        await run_device(cfg)
    elif cfg.mode == "host":
        print("Host server mode is not yet implemented; start with --mode device for now.")
    else:
        print("Combined mode is not yet implemented; starting device mode only.")
        await run_device(cfg)


if __name__ == "__main__":
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass
