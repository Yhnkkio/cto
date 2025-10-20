from __future__ import annotations

import asyncio
import logging
import os
import random
import string
from dataclasses import dataclass
from typing import Optional

from .protocol import (
    ADBPacket,
    A_AUTH,
    A_CNXN,
    A_OPEN,
    A_OKAY,
    A_WRTE,
    A_CLSE,
    ADB_MAX_PAYLOAD,
    ADB_PROTOCOL_VERSION,
    build_cnxn_payload,
    parse_cnxn_payload,
    features_from_payload,
)
from .transport import Transport

log = logging.getLogger(__name__)


DEFAULT_FEATURES = {
    "shell_v2",
    "cmd",
    "ls_v2",
}


@dataclass
class DeviceInfo:
    serial: str
    ro_adb_secure: int = 0  # 0 disables auth (no AUTH handshake)


def _generate_serial() -> str:
    # Simple deterministic-ish serial per process
    pid = os.getpid()
    rnd = "".join(random.choice(string.hexdigits.lower()) for _ in range(6))
    return f"cto-{pid}-{rnd}"


class ADBSession:
    def __init__(self, transport: Transport, device: Optional[DeviceInfo] = None, features: Optional[set[str]] = None) -> None:
        self.transport = transport
        self.device = device or DeviceInfo(serial=_generate_serial(), ro_adb_secure=0)
        self.features = set(features or DEFAULT_FEATURES)
        self._max_payload = ADB_MAX_PAYLOAD
        self._peer_features: set[str] = set()
        self._connected = False

    @property
    def max_payload(self) -> int:
        return self._max_payload

    async def perform_handshake(self) -> None:
        # Wait for CNXN from peer; ignore AUTH and other packets until we get CNXN
        while True:
            pkt = await self.transport.read_packet()
            if pkt.command == A_CNXN:
                break
            if pkt.command == A_AUTH:
                # Ignore unexpected AUTH from peer
                log.debug("Ignoring unexpected AUTH during handshake")
                continue
            # For any other packets before CNXN, ignore or close? We'll ignore.
            log.debug("Ignoring packet before CNXN: cmd=0x%08x", pkt.command)

        # Parse peer CNXN payload for features and banner
        peer_banner = parse_cnxn_payload(pkt.payload)
        self._peer_features = features_from_payload(peer_banner)
        # Negotiate max payload and version (we accept whatever peer suggested)
        their_max = pkt.arg1 or ADB_MAX_PAYLOAD
        self._max_payload = min(their_max, ADB_MAX_PAYLOAD)
        log.debug("Peer CNXN banner: %s; features=%s; max_payload=%d", peer_banner, self._peer_features, self._max_payload)

        # If secure=0, do not send AUTH. Reply with our CNXN immediately.
        banner = f"ro.serialno={self.device.serial};ro.adb.secure={self.device.ro_adb_secure}"
        cnxn_payload = build_cnxn_payload("device", banner, sorted(self.features))
        reply = ADBPacket(command=A_CNXN, arg0=ADB_PROTOCOL_VERSION, arg1=self._max_payload, payload=cnxn_payload)
        await self.transport.write_packet(reply)
        self._connected = True

    async def run(self) -> None:
        # Perform handshake then idle, ignoring packets we don't implement yet
        await self.perform_handshake()
        try:
            while True:
                pkt = await self.transport.read_packet()
                cmd = pkt.command
                if cmd == A_OPEN:
                    # Minimal implementation: reply OKAY immediately to open requests but don't handle data
                    local_id = 1  # we can use a fixed local id for now
                    remote_id = pkt.arg0
                    # For correctness we should track ids; here we bounce back OKAY
                    ok = ADBPacket(command=A_OKAY, arg0=local_id, arg1=remote_id, payload=b"")
                    await self.transport.write_packet(ok)
                elif cmd in (A_OKAY, A_WRTE, A_CLSE):
                    # Ignore for now
                    pass
                elif cmd == A_AUTH:
                    # Ignore any stray auth packets
                    log.debug("Ignoring AUTH after handshake")
                elif cmd == A_CNXN:
                    # Peer trying to renegotiate; send our CNXN again
                    await self.perform_handshake()
                else:
                    # Unknown - ignore
                    pass
        except asyncio.IncompleteReadError:
            # Peer disconnected
            log.debug("Client disconnected")
        except Exception:
            log.exception("Session error")
        finally:
            await self.transport.close()
