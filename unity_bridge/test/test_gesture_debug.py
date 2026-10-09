import asyncio
import json
import time
import urllib.error
import urllib.request

import pytest
import websockets
from websockets.asyncio.server import serve

from unity_bridge import core
from unity_bridge.bridge_relay import BridgeRelay
from unity_bridge.gesture_codec import encode_message
from unity_bridge.gesture_debug import DebugGui, ManualGestureSource, serve_debug_gui
from unity_bridge.gesture_delivery import DeliveryOutbox
from unity_bridge.gesture_probe import decode_payload

FANNING = {
    "gesture": "FANNING",
    "tracking": True,
    "booth_present": True,
    "action": "FANNING",
    "phase": "ACTIVE",
    "action_accuracy": 0.7,
}


def test_source_republishes_state_and_fires_each_occurrence_once():
    source = ManualGestureSource(refresh=0.01)
    source.set_state(FANNING)
    source.trigger("RAMUNE", 0.9)
    first = source.get(timeout=0.5)
    second = source.get(timeout=0.5)
    assert first is not None and second is not None
    assert (first.gesture, first.action, first.phase) == (
        "FANNING",
        "FANNING",
        "ACTIVE",
    )
    assert first.action_accuracy == 0.7
    assert [kind for kind, _ in first.occurrences] == ["RAMUNE"]
    assert first.occurrence_accuracies == (0.9,)
    assert second.occurrences == ()
    assert first.frame_id is not None
    assert second.frame_id == first.frame_id + 1
    source.close()
    assert source.get(timeout=0.5) is None


@pytest.mark.parametrize(
    "fields",
    [
        {"gesture": "RAMUNE"},
        {"gesture": "NONE", "action": "RAMUNE", "phase": "SWING"},
        {"gesture": "NONE", "action": "RAMUNE"},
    ],
)
def test_source_rejects_state_unity_would_reject(fields):
    source = ManualGestureSource()
    with pytest.raises(ValueError):
        source.set_state({"tracking": True, **fields})
    assert source.state()["gesture"] == "NONE"


def test_source_drops_accuracy_without_a_tracked_gesture():
    source = ManualGestureSource()
    source.set_state({**FANNING, "tracking": False})
    assert source.state()["action_accuracy"] is None
    with pytest.raises(ValueError):
        source.trigger("FANNING")


def test_browser_command_reaches_unity_and_ack_returns_to_browser():
    async def scenario():
        relay = BridgeRelay(DeliveryOutbox(), state_interval=0.02)
        source = ManualGestureSource(refresh=0.01)
        pump = asyncio.create_task(relay.pump(source))
        try:
            async with (
                serve(relay.serve, "127.0.0.1", 0, close_timeout=0.1) as unity_ws,
                serve_debug_gui(source, relay, "127.0.0.1", 0) as gui_ws,
            ):
                unity_port = unity_ws.sockets[0].getsockname()[1]
                gui_port = gui_ws.sockets[0].getsockname()[1]
                page = await asyncio.to_thread(
                    lambda: urllib.request.urlopen(
                        f"http://127.0.0.1:{gui_port}/"
                    ).read()
                )
                assert "所作デバッグ送信" in page.decode()
                async with (
                    websockets.connect(f"ws://127.0.0.1:{gui_port}/ws") as browser,
                    websockets.connect(f"ws://127.0.0.1:{unity_port}") as unity,
                ):
                    vocab = json.loads(await browser.recv())
                    assert vocab["action_phases"]["RAMUNE"][0] == "FORMING"
                    await browser.send(json.dumps({"type": "state", **FANNING}))
                    await browser.send(
                        json.dumps({"type": "event", "gesture": "UCHIMIZU"})
                    )
                    state = event = None
                    while state is None or event is None:
                        data = await asyncio.wait_for(unity.recv(), 2)
                        assert isinstance(data, bytes)
                        message = decode_payload(data)
                        if message is None:
                            continue
                        if (
                            message["type"] == "state"
                            and message["gesture"] == "FANNING"
                        ):
                            state = message
                        elif message["type"] == "event":
                            event = message
                    assert state["action_accuracy"] == 0.7
                    assert event["gesture"] == "UCHIMIZU"
                    await unity.send(
                        encode_message(
                            {
                                "version": 1,
                                "type": "ack",
                                "session_id": event["session_id"],
                                "event_id": event["event_id"],
                                "status": "accepted",
                            }
                        )
                    )
                    await browser.send(json.dumps({"type": "event", "gesture": "BOW"}))
                    errors = []
                    while True:
                        status = json.loads(await asyncio.wait_for(browser.recv(), 2))
                        if status["type"] == "error":
                            errors.append(status["message"])
                        elif status["type"] == "status" and status["acks"]:
                            break
                    assert status["unity_connected"]
                    assert status["pending"] == []
                    assert status["acks"][0] == {
                        "event_id": event["event_id"],
                        "gesture": "UCHIMIZU",
                        "status": "accepted",
                    }
                    assert errors
        finally:
            source.close()
            await asyncio.wait_for(pump, 1)

    asyncio.run(scenario())


def test_debug_gui_mode_replaces_detection(monkeypatch):
    monkeypatch.setattr(core, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        "sys.argv", ["unity-bridge", "--debug-gui", "--debug-port", "5090"]
    )
    args = core._parse_args()
    assert args.gesture and args.debug_gui
    assert args.host == "127.0.0.1"
    assert args.debug_port == 5090
    monkeypatch.setattr("sys.argv", ["unity-bridge", "--debug-gui", "--fan"])
    with pytest.raises(SystemExit):
        core._parse_args()


def test_unknown_page_is_not_found():
    async def scenario():
        relay = BridgeRelay(DeliveryOutbox())
        async with serve_debug_gui(ManualGestureSource(), relay, "127.0.0.1", 0) as ws:
            port = ws.sockets[0].getsockname()[1]

            def fetch() -> int:
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/missing")
                except urllib.error.HTTPError as error:
                    return error.code
                return 200

            assert await asyncio.to_thread(fetch) == 404

    asyncio.run(scenario())


def test_status_reports_disconnected_unity():
    relay = BridgeRelay(DeliveryOutbox())
    gui = DebugGui(ManualGestureSource(), relay)
    assert gui.handle("[]") == {"type": "error", "message": "Expected a JSON object"}
    status = gui.status()
    assert not status["unity_connected"]
    assert status["now"] <= time.monotonic()
