from __future__ import annotations

import asyncio
from typing import Optional


class MdnsAdvertiser:
    def __init__(self, port: int, name: str):
        self.port = port
        self.name = name
        self._task: Optional[asyncio.Task] = None
        self._zeroconf = None

    async def start(self) -> None:
        try:
            from zeroconf import IPVersion, ServiceInfo, Zeroconf
        except Exception:
            # zeroconf not available; run a no-op background task so lifecycle is consistent
            async def noop():
                while True:
                    await asyncio.sleep(3600)
            self._task = asyncio.create_task(noop())
            return

        # Advertise _adb._tcp with service name equal to serial
        zc = Zeroconf(ip_version=IPVersion.All)
        self._zeroconf = zc
        info = ServiceInfo(
            "_adb._tcp.local.",
            f"{self.name}._adb._tcp.local.",
            addresses=None,
            port=self.port,
            properties={},
        )
        zc.register_service(info)

        async def run():
            try:
                while True:
                    await asyncio.sleep(3600)
            finally:
                try:
                    zc.unregister_service(info)
                except Exception:
                    pass
                try:
                    zc.close()
                except Exception:
                    pass

        self._task = asyncio.create_task(run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
            self._task = None
