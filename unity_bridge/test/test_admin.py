import asyncio
import json
import time
import urllib.error
import urllib.request

import pytest
import websockets
from bridge.v1 import bridge_pb2
from diffuser.v1 import diffuser_pb2
from gesture_detection.recognition_types import GestureSample
from websockets.asyncio.server import serve

from unity_bridge import core
from unity_bridge.admin import AdminPanel, serve_admin
from unity_bridge.bridge_relay import BridgeRelay
from unity_bridge.diffuser import DiffuserController
from unity_bridge.gesture_delivery import DeliveryOutbox


class FakeSource:
    def __init__(self, sample: GestureSample) -> None:
        self.samples = [sample]

    def get(self, timeout: float) -> GestureSample | None:
        return self.samples.pop() if self.samples else None


def unity_status(**settings) -> bytes:
    status = bridge_pb2.RuntimeStatus(
        settings=bridge_pb2.RuntimeSettings(**settings),
        scene="Forest",
        current_hour=18.5,
        effective_time_scale=2.0,
        fps=60,
    )
    return bridge_pb2.BridgeEnvelope(runtime_status=status).SerializeToString()


async def read_settings(client) -> bridge_pb2.RuntimeSettings:
    while True:
        envelope = bridge_pb2.BridgeEnvelope.FromString(
            await asyncio.wait_for(client.recv(), 1)
        )
        if envelope.WhichOneof("payload") == "runtime_settings":
            return envelope.runtime_settings


def test_settings_reach_unity_and_unity_reports_back():
    async def scenario():
        relay = BridgeRelay(DeliveryOutbox(), state_interval=0.02)
        panel = AdminPanel(relay)
        async with serve(relay.serve, "127.0.0.1", 0, close_timeout=0.1) as ws:
            port = ws.sockets[0].getsockname()[1]
            async with websockets.connect(f"ws://127.0.0.1:{port}") as unity:
                # 接続直後に、いまの設定が届く。
                first = await read_settings(unity)
                assert first.diffuser_enabled and first.time_scale_multiplier == 1
                assert (
                    panel.handle(
                        json.dumps({"type": "settings", "diffuser_enabled": False})
                    )
                    is None
                )
                changed = await read_settings(unity)
                assert not changed.diffuser_enabled
                await unity.send(unity_status(diffuser_enabled=False))
                log = bridge_pb2.UnityLog(
                    level=bridge_pb2.UNITY_LOG_LEVEL_EXCEPTION,
                    message="NullReferenceException",
                    stack_trace="at Foo()",
                )
                await unity.send(
                    bridge_pb2.BridgeEnvelope(unity_log=log).SerializeToString()
                )
                async with asyncio.timeout(1):
                    while not relay.errors.entries():
                        await asyncio.sleep(0.01)
                status = panel.status()
                assert status["unity"]["connected"]
                assert status["unity"]["status"]["scene"] == "Forest"
                assert status["unity"]["status"]["current_hour"] == 18.5
                assert not status["unity"]["status"]["settings"]["diffuser_enabled"]
                [error] = status["errors"]
                assert (error["source"], error["level"]) == ("unity", "exception")
                assert error["detail"] == "at Foo()"
        async with asyncio.timeout(1):
            while relay.connected:
                await asyncio.sleep(0.01)
        assert panel.status()["unity"] == {
            "connected": False,
            "status_age": None,
            "status": None,
        }

    asyncio.run(scenario())


def test_status_shows_recognition_fans_and_estimated_diffusers():
    relay = BridgeRelay(DeliveryOutbox(), diffuser=DiffuserController())
    now = time.monotonic()
    sample = GestureSample(
        "FANNING",
        True,
        now,
        (("RAMUNE", now),),
        action="FANNING",
        phase="ACTIVE",
        booth_present=True,
        occurrence_accuracies=(0.8,),
    )
    asyncio.run(relay.pump(FakeSource(sample)))
    relay.diffuser.press(
        diffuser_pb2.DiffuserPress(
            channel=diffuser_pb2.DIFFUSER_CHANNEL_FOREST, duration_ms=200
        )
    )
    status = AdminPanel(relay).status()
    assert status["gesture"]["sample"]["gesture"] == "FANNING"
    assert status["gesture"]["occurrences"][0]["gesture"] == "RAMUNE"
    assert status["gesture"]["occurrences"][0]["action_accuracy"] == 0.8
    assert [c["name"] for c in status["fan"]["channels"]][:2] == [
        "LEFT_BACK",
        "LEFT_SIDE",
    ]
    assert status["fan"]["mcu"] == {"configured": False}
    assert [(d["name"], d["on"]) for d in status["diffuser"]["channels"]] == [
        ("RAMUNE", False),
        ("FOREST", True),
    ]
    assert not status["diffuser"]["wired"]


def test_bad_commands_are_reported():
    panel = AdminPanel(BridgeRelay(DeliveryOutbox()))
    assert panel.handle("[]") == {"type": "error", "message": "Expected a JSON object"}
    assert panel.handle('{"type": "reboot"}') == {
        "type": "error",
        "message": "Unknown command",
    }
    error = panel.handle('{"type": "settings", "time_scale_multiplier": -1}')
    assert error is not None and error["type"] == "error"


def test_clear_errors():
    relay = BridgeRelay(DeliveryOutbox())
    relay.errors.record("bridge", "error", "boom")
    assert AdminPanel(relay).handle('{"type": "clear_errors"}') is None
    assert relay.errors.entries() == []


@pytest.mark.parametrize(
    ("token", "query", "code"),
    [
        (None, "", 200),
        ("secret", "", 403),
        ("secret", "?token=nope", 403),
        ("secret", "?token=secret", 200),
    ],
)
def test_page_requires_the_token_when_set(token, query, code):
    async def scenario():
        panel = AdminPanel(BridgeRelay(DeliveryOutbox()), token=token)
        async with serve_admin(panel, "127.0.0.1", 0) as ws:
            port = ws.sockets[0].getsockname()[1]

            def fetch() -> int:
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/{query}"):
                        return 200
                except urllib.error.HTTPError as error:
                    return error.code

            assert await asyncio.to_thread(fetch) == code

    asyncio.run(scenario())


def test_browser_changes_settings_over_the_websocket():
    async def scenario():
        relay = BridgeRelay(DeliveryOutbox())
        async with serve_admin(AdminPanel(relay), "127.0.0.1", 0) as ws:
            port = ws.sockets[0].getsockname()[1]
            async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as browser:
                assert json.loads(await browser.recv())["type"] == "status"
                await browser.send(
                    json.dumps({"type": "settings", "time_scale_multiplier": 3})
                )
                async with asyncio.timeout(1):
                    while True:
                        message = json.loads(await browser.recv())
                        if message["settings"]["time_scale_multiplier"] == 3:
                            break
        assert relay.settings.current.time_scale_multiplier == 3

    asyncio.run(scenario())


def test_admin_is_on_by_default_and_can_be_disabled(monkeypatch):
    monkeypatch.setattr(core, "load_dotenv", lambda: None)
    monkeypatch.delenv("ADMIN_PORT", raising=False)
    monkeypatch.delenv("ADMIN_HOST", raising=False)
    monkeypatch.setattr("sys.argv", ["unity-bridge", "--gesture"])
    args = core._parse_args()
    assert (args.admin_host, args.admin_port, args.no_admin) == ("0.0.0.0", 5081, False)
    # Unity のソケットは loopback のまま。
    assert args.host == "127.0.0.1"
    monkeypatch.setattr("sys.argv", ["unity-bridge", "--gesture", "--no-admin"])
    assert core._parse_args().no_admin
