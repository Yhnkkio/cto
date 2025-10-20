from __future__ import annotations

import asyncio
import logging
import socket
from typing import Optional

from zeroconf import ServiceInfo, Zeroconf

from .config import Config

logger = logging.getLogger(__name__)


async def serve_forever(port: int, config: Config, advertise: bool = True) -> None:
    zc: Optional[Zeroconf] = None
    info: Optional[ServiceInfo] = None

    if advertise:
        try:
            zc = Zeroconf()
            hostname = socket.gethostname()
            try:
                ip = socket.gethostbyname(hostname)
                addr_bytes = socket.inet_aton(ip)
            except Exception:
                addr_bytes = socket.inet_aton("127.0.0.1")

            info = ServiceInfo(
                type_="_adb-mock._tcp.local.",
                name=f"ADB Mock Server._adb-mock._tcp.local.",
                addresses=[addr_bytes],
                port=port,
                properties={
                    b"path": b"/",
                    b"version": b"1",
                },
            )
            zc.register_service(info)
            logger.info("Registered Zeroconf service '%s' on port %s", info.name, port)
        except Exception as e:
            logger.warning("Failed to register Zeroconf service: %s", e)
            zc = None
            info = None

    logger.info(
        "ADB overlay mock server is running (placeholder). Props=%d, Commands=%d, Overlay=%s",
        len(config.props or {}),
        len(config.commands or {}),
        str(config.overlay_dir),
    )

    try:
        # Placeholder async loop; Replace with actual protocol handling in the future
        while True:
            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        pass
    finally:
        if zc is not None:
            if info is not None:
                try:
                    zc.unregister_service(info)
                except Exception:
                    pass
            try:
                zc.close()
            except Exception:
                pass
        logger.info("Server shutdown complete.")
