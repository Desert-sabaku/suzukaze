import asyncio
import queue
import time

import pytest
import websockets
from gesture_detection.recognition_types import GestureSample
from websockets.asyncio.server import serve

from unity_bridge.gesture_codec import decode_message, encode_message
from unity_bridge.gesture_delivery import DeliveryOutbox
from unity_bridge.gesture_relay import GestureRelay


def ramune(now: float) -> GestureSample:
    return GestureSample("NONE", True, now, (("RAMUNE", now),), 1, now)


async def receive(client, kind: str) -> dict:
    while True:
        message = decode_message(await asyncio.wait_for(client.recv(), 1))
        if message["type"] == kind:
            return message


def test_relay_continues_sending_state_after_booth_exit():
    async def scenario():
        outbox = DeliveryOutbox()
        now = time.monotonic()
        outbox.publish(
            GestureSample("NONE", True, now, (), booth_present=True), now=now
        )
        relay = GestureRelay(outbox, state_interval=0.02)
        async with serve(relay.serve, "127.0.0.1", 0, close_timeout=0.1) as ws:
            port = ws.sockets[0].getsockname()[1]
            async with websockets.connect(f"ws://127.0.0.1:{port}") as client:
                present = await receive(client, "state")
                assert present["booth_present"]
                now = time.monotonic()
                outbox.publish(
                    GestureSample("NONE", False, now, (), booth_present=False), now=now
                )
                async with asyncio.timeout(1):
                    while True:
                        absent = await receive(client, "state")
                        if not absent["booth_present"]:
                            break
                assert absent["fresh"] and not absent["tracking"]
                following = await receive(client, "state")
                assert not following["booth_present"]
                assert following["sequence"] > absent["sequence"] > present["sequence"]

    asyncio.run(scenario())


def test_relay_sends_protobuf_and_applies_unity_ack():
    async def scenario():
        outbox = DeliveryOutbox()
        outbox.publish(ramune(time.monotonic()), now=time.monotonic())
        relay = GestureRelay(outbox, state_interval=0.02)
        async with serve(relay.serve, "127.0.0.1", 0, close_timeout=0.1) as ws:
            port = ws.sockets[0].getsockname()[1]
            async with websockets.connect(f"ws://127.0.0.1:{port}") as client:
                assert (await receive(client, "state"))["tracking"]
                event = await receive(client, "event")
                assert event["gesture"] == "RAMUNE"
                async with websockets.connect(f"ws://127.0.0.1:{port}") as other:
                    await asyncio.wait_for(other.wait_closed(), 1)
                    assert other.close_code == 1013
                ack = {
                    "version": 1,
                    "type": "ack",
                    "session_id": event["session_id"],
                    "event_id": event["event_id"],
                    "status": "accepted",
                }
                await client.send(encode_message(ack))
                await receive(client, "state")
                assert outbox.events(time.monotonic(), reconnect=True) == []

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "payload",
    [
        "text",
        b"\xff",
        encode_message(
            {
                "version": 1,
                "type": "event",
                "session_id": "one",
                "event_id": 1,
                "gesture": "RAMUNE",
                "occurred_at": 10.0,
                "expires_at": 11.0,
            }
        ),
    ],
)
def test_bad_unity_message_closes_connection(payload):
    async def scenario():
        relay = GestureRelay(DeliveryOutbox())
        async with serve(relay.serve, "127.0.0.1", 0, close_timeout=0.1) as ws:
            port = ws.sockets[0].getsockname()[1]
            async with websockets.connect(f"ws://127.0.0.1:{port}") as client:
                await client.send(payload)
                await asyncio.wait_for(client.wait_closed(), 1)
                assert client.close_code == 1011
        assert not relay._connected

    asyncio.run(scenario())


class FakeSource:
    def __init__(self, *items):
        self.items = list(items)

    def get(self, timeout: float) -> GestureSample | None:
        item = self.items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def test_pump_publishes_samples_and_stops_when_recognition_exits():
    outbox = DeliveryOutbox()
    now = time.monotonic()
    source = FakeSource(queue.Empty(), ramune(now), RuntimeError("exited"))
    with pytest.raises(RuntimeError, match="exited"):
        asyncio.run(GestureRelay(outbox).pump(source))  # type: ignore[arg-type]
    assert [e["gesture"] for e in outbox.events(time.monotonic())] == ["RAMUNE"]


def test_pump_returns_when_recognition_exits_normally():
    source = FakeSource(queue.Empty(), None)
    asyncio.run(GestureRelay(DeliveryOutbox()).pump(source))  # type: ignore[arg-type]
