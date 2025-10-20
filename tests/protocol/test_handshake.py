from __future__ import annotations

import asyncio
from typing import List

from cto.adb_session import ADBSession, DeviceInfo, DEFAULT_FEATURES
from cto.protocol import (
    ADBPacket,
    A_AUTH,
    A_CNXN,
    ADB_MAX_PAYLOAD,
    ADB_PROTOCOL_VERSION,
    build_cnxn_payload,
)
from cto.transport import Transport


class FakeTransport(Transport):
    def __init__(self) -> None:
        self.incoming: asyncio.Queue[ADBPacket] = asyncio.Queue()
        self.outgoing: List[ADBPacket] = []
        self.closed = False

    async def read_packet(self) -> ADBPacket:
        return await self.incoming.get()

    async def write_packet(self, pkt: ADBPacket) -> None:
        self.outgoing.append(pkt)

    async def close(self) -> None:
        self.closed = True


def make_host_cnxn(features: List[str] | None = None, *, max_payload: int = ADB_MAX_PAYLOAD) -> ADBPacket:
    feats = features or sorted(DEFAULT_FEATURES)
    payload = build_cnxn_payload("host", "", feats)
    return ADBPacket(command=A_CNXN, arg0=ADB_PROTOCOL_VERSION, arg1=max_payload, payload=payload)


def test_handshake_responds_with_device_cnxn_and_features() -> None:
    async def _run() -> None:
        ft = FakeTransport()
        session = ADBSession(transport=ft, device=DeviceInfo(serial="unit-serial", ro_adb_secure=0))
        # Prepend an unexpected AUTH packet, then a proper CNXN
        await ft.incoming.put(ADBPacket(command=A_AUTH, arg0=1, arg1=0, payload=b"token"))
        await ft.incoming.put(make_host_cnxn(["cmd", "shell_v2"]))

        await session.perform_handshake()

        # We should have sent a single CNXN in response
        assert len(ft.outgoing) == 1
        reply = ft.outgoing[0]
        assert reply.command == A_CNXN
        assert reply.arg0 == ADB_PROTOCOL_VERSION
        assert 0 < reply.arg1 <= ADB_MAX_PAYLOAD
        banner = reply.payload.decode("utf-8", errors="replace")
        assert banner.startswith("device::")
        assert "ro.serialno=unit-serial" in banner
        assert "ro.adb.secure=0" in banner
        assert "features=" in banner
        # Should not send AUTH at all
        assert all(p.command != A_AUTH for p in ft.outgoing)

    asyncio.run(_run())


def test_handshake_negotiates_max_payload() -> None:
    async def _run() -> None:
        ft = FakeTransport()
        session = ADBSession(transport=ft)
        # Host advertises a smaller max payload
        host_max = 1024
        await ft.incoming.put(make_host_cnxn(max_payload=host_max))
        await session.perform_handshake()
        assert len(ft.outgoing) == 1
        assert ft.outgoing[0].arg1 == host_max

    asyncio.run(_run())
