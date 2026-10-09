"""Admin page for the venue: watch the bridge and Unity, and change settings.

It starts with every gesture-mode bridge. Unlike the debug GUI it listens on
the LAN (default 0.0.0.0) so a phone on the venue Wi-Fi can open it; Unity's
socket stays on loopback. Set ADMIN_TOKEN to require ?token=... on the page and
its WebSocket.
"""

import asyncio
import hmac
import json
import socket
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from importlib.resources import files
from typing import Any
from urllib.parse import parse_qs, urlsplit

import websockets
from bridge.v1 import bridge_pb2
from diffuser.v1 import diffuser_pb2
from fan.v1 import fan_pb2
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Request, Response

from .bridge_relay import BridgeRelay
from .fan import CHANNELS

DEFAULT_ADMIN_HOST = "0.0.0.0"
DEFAULT_ADMIN_PORT = 5081
STATUS_INTERVAL = 0.5


class AdminPanel:
    """Status snapshot and settings commands for the admin page."""

    def __init__(
        self,
        relay: BridgeRelay,
        gesture_source: str = "gesture_detection",
        token: str | None = None,
    ) -> None:
        self.relay = relay
        self.gesture_source = gesture_source
        self.token = token or None
        self._started_at = time.monotonic()

    def status(self) -> dict[str, Any]:
        now = time.monotonic()
        relay = self.relay
        return {
            "type": "status",
            "uptime": now - self._started_at,
            "unity": self._unity(now),
            "gesture": self._gesture(now),
            "fan": {
                "active": relay.fan.active,
                "mcu": self._mcu(),
                "channels": [
                    {
                        "name": fan_pb2.FanChannel.Name(c).removeprefix("FAN_CHANNEL_"),
                        "value": value,
                    }
                    for c, value in zip(CHANNELS, relay.fan.values(), strict=True)
                ],
            },
            "diffuser": {
                "wired": relay.diffuser.wired,
                "channels": [
                    {
                        **channel,
                        "name": diffuser_pb2.DiffuserChannel.Name(
                            channel["channel"]
                        ).removeprefix("DIFFUSER_CHANNEL_"),
                    }
                    for channel in relay.diffuser.channels()
                ],
            },
            "settings": asdict(relay.settings.current),
            "errors": relay.errors.entries(),
        }

    def _unity(self, now: float) -> dict[str, Any]:
        status = self.relay.unity_status
        at = self.relay.unity_status_at
        return {
            "connected": self.relay.connected,
            "status_age": None if at is None else now - at,
            "status": None if status is None else _unity_status(status),
        }

    def _gesture(self, now: float) -> dict[str, Any]:
        sample = self.relay.latest_sample
        return {
            "source": self.gesture_source,
            "sample_age": None if sample is None else now - sample.observed_at,
            "sample": None
            if sample is None
            else {
                "gesture": str(sample.gesture),
                "tracking": sample.tracking,
                "booth_present": sample.booth_present,
                "action": sample.action,
                "phase": sample.phase,
                "action_accuracy": sample.action_accuracy,
                "frame_id": sample.frame_id,
            },
            "occurrences": list(self.relay.recent_occurrences),
            "pending_events": len(self.relay.outbox.pending(now)),
        }

    def _mcu(self) -> dict[str, Any]:
        mcu = self.relay.mcu
        if mcu is None:
            return {"configured": False}
        return {
            "configured": True,
            "port": mcu.port,
            "connected": mcu.connected,
            "last_error": mcu.last_error,
        }

    def handle(self, raw: str | bytes) -> dict[str, Any] | None:
        """Apply one browser command; return an error message if it failed."""
        try:
            command = json.loads(raw)
            if not isinstance(command, dict):
                raise ValueError("Expected a JSON object")  # noqa: TRY004
            kind = command.pop("type", None)
            if kind == "settings":
                settings = self.relay.settings.update(command)
                print(f"Settings changed: {asdict(settings)}", flush=True)
            elif kind == "clear_errors":
                self.relay.errors.clear()
            else:
                raise ValueError("Unknown command")
        except (ValueError, TypeError) as error:
            return {"type": "error", "message": str(error)}
        return None

    def authorized(self, path: str) -> bool:
        if self.token is None:
            return True
        given = parse_qs(urlsplit(path).query).get("token", [""])[0]
        return hmac.compare_digest(given.encode(), self.token.encode())

    def process_request(self, connection: Any, request: Request) -> Response | None:
        route = urlsplit(request.path).path
        if route not in ("/", "/index.html", "/ws"):
            return connection.respond(404, "Not found\n")
        if not self.authorized(request.path):
            return connection.respond(403, "Forbidden: add ?token=...\n")
        if route == "/ws":
            return None
        body = files(__package__).joinpath("admin.html").read_bytes()
        headers = Headers(
            [
                ("Content-Type", "text/html; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
            ]
        )
        return Response(200, "OK", headers, body)

    async def serve(self, websocket: Any) -> None:
        sender = asyncio.create_task(self._send_status(websocket))
        try:
            async for raw in websocket:
                error = self.handle(raw)
                if error is not None:
                    await websocket.send(json.dumps(error))
                else:
                    # 変更をすぐ画面に返す。
                    await websocket.send(json.dumps(self.status()))
        except ConnectionClosed:
            pass
        finally:
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)

    async def _send_status(self, websocket: Any) -> None:
        while True:
            await websocket.send(json.dumps(self.status()))
            await asyncio.sleep(STATUS_INTERVAL)


def _unity_status(status: bridge_pb2.RuntimeStatus) -> dict[str, Any]:
    return {
        "settings": {
            "diffuser_enabled": status.settings.diffuser_enabled,
            "time_scale_multiplier": status.settings.time_scale_multiplier,
        },
        "scene": status.scene,
        "current_hour": (
            status.current_hour if status.HasField("current_hour") else None
        ),
        "effective_time_scale": status.effective_time_scale,
        "fps": status.fps,
    }


def lan_addresses() -> list[str]:
    """IPv4 addresses a phone on the same network might reach, best effort."""
    addresses: set[str] = set()
    try:
        addresses.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    # 経路の決まる宛先へ UDP を connect すると、使うアドレスがわかる(送信はしない)。
    for probe in ("192.168.0.1", "10.0.0.1"):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            try:
                udp.connect((probe, 9))
                addresses.add(udp.getsockname()[0])
            except OSError:
                pass
    return sorted(a for a in addresses if not a.startswith(("127.", "0.")))


@asynccontextmanager
async def serve_admin(panel: AdminPanel, host: str, port: int) -> AsyncIterator[Any]:
    async with websockets.serve(
        panel.serve,
        host,
        port,
        process_request=panel.process_request,
        close_timeout=0.5,
    ) as server:
        yield server
