import asyncio
import queue
import threading
import time
from typing import cast

import pytest
import websockets
from gesture_detection.recognition_types import GestureSample
from websockets.asyncio.server import serve

from unity_bridge.bridge_relay import BridgeRelay
from unity_bridge.fan import FanController, McuFadeSender
from unity_bridge.gesture_codec import encode_message
from unity_bridge.gesture_delivery import DeliveryOutbox
from unity_bridge.gesture_probe import decode_payload


def ramune(now: float) -> GestureSample:
    return GestureSample("NONE", True, now, (("RAMUNE", now),), 1, now)


async def receive(client, kind: str) -> dict:
    while True:
        message = decode_payload(await asyncio.wait_for(client.recv(), 1))
        if message is not None and message["type"] == kind:
            return message


def test_relay_continues_sending_state_after_booth_exit():
    async def scenario():
        outbox = DeliveryOutbox()
        now = time.monotonic()
        outbox.publish(
            GestureSample("NONE", True, now, (), booth_present=True), now=now
        )
        relay = BridgeRelay(outbox, state_interval=0.02)
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
        relay = BridgeRelay(outbox, state_interval=0.02)
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
        relay = BridgeRelay(DeliveryOutbox())
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
        asyncio.run(BridgeRelay(outbox).pump(source))  # type: ignore[arg-type]
    assert [e["gesture"] for e in outbox.events(time.monotonic())] == ["RAMUNE"]


def test_pump_returns_when_recognition_exits_normally():
    source = FakeSource(queue.Empty(), None)
    asyncio.run(BridgeRelay(DeliveryOutbox()).pump(source))  # type: ignore[arg-type]


def test_fan_command_is_applied_and_state_is_read_back():
    from bridge.v1 import bridge_pb2
    from fan.v1 import fan_pb2

    async def read_fan(client) -> dict[int, int]:
        while True:
            envelope = bridge_pb2.BridgeEnvelope.FromString(
                await asyncio.wait_for(client.recv(), 1)
            )
            if envelope.WhichOneof("payload") == "fan_state":
                return {r.channel: r.value for r in envelope.fan_state.readings}

    async def scenario():
        sent = []
        relay = BridgeRelay(
            DeliveryOutbox(),
            state_interval=0.02,
            fan=FanController(send_fade=lambda *args: sent.append(args)),
        )
        async with serve(relay.serve, "127.0.0.1", 0, close_timeout=0.1) as ws:
            port = ws.sockets[0].getsockname()[1]
            async with websockets.connect(f"ws://127.0.0.1:{port}") as client:
                command = fan_pb2.Fan(
                    channel=fan_pb2.FAN_CHANNEL_LEFT_SIDE, value=200, duration_ms=0
                )
                await client.send(
                    bridge_pb2.BridgeEnvelope(fan_command=command).SerializeToString()
                )
                readings = await read_fan(client)
                assert readings[fan_pb2.FAN_CHANNEL_LEFT_SIDE] == round(
                    255 * (200 / 255) ** 2.2
                )
                assert readings[fan_pb2.FAN_CHANNEL_RIGHT_BACK] == 0
        assert sent == [(fan_pb2.FAN_CHANNEL_LEFT_SIDE, 200, 0)]

    asyncio.run(scenario())


def test_fan_fades_on_a_gamma_curve_and_rejects_bad_commands():
    from fan.v1 import fan_pb2

    now = [0.0]
    fan = FanController(clock=lambda: now[0])
    fan.command(
        fan_pb2.Fan(channel=cast("fan_pb2.FanChannel", 1), value=255, duration_ms=1000)
    )
    # firmware/cmd/pwm.go と同じ: 0 から value まで (t * value / 255) ** 2.2。
    now[0] = 0.5
    assert fan._value(1, now[0]) == round(255 * 0.5**2.2)
    now[0] = 2.0
    assert fan._value(1, now[0]) == 255
    for bad in (
        fan_pb2.Fan(channel=cast("fan_pb2.FanChannel", 0), value=1),
        fan_pb2.Fan(channel=cast("fan_pb2.FanChannel", 7), value=1),
        fan_pb2.Fan(channel=cast("fan_pb2.FanChannel", 1), value=256),
    ):
        with pytest.raises(ValueError, match="Invalid fan command"):
            fan.command(bad)


def test_mcu_sender_maps_channels_to_pins_and_survives_a_missing_mcu():
    done = threading.Event()
    calls = []

    class Handshake:
        matched = True

    class Client:
        attempts = 0

        def __init__(self, port, baudrate):
            assert (port, baudrate) == ("PORT", 115200)

        def connect(self):
            Client.attempts += 1
            if Client.attempts == 1:
                raise OSError("no such device")

        def handshake(self):
            return Handshake()

        def send_fade(self, pin, value, duration_ms):
            calls.append((pin, value, duration_ms))
            done.set()

        def close(self):
            pass

    errors = []
    sender = McuFadeSender(
        "PORT", (10, 11, 12, 13, 14, 15), client_factory=Client, on_error=errors.append
    )
    sender(1, 50, 0)  # MCU がなくて落とされる
    sender(6, 200, 300)  # 再接続して送られる
    assert done.wait(2)
    assert calls == [(15, 200, 300)]
    assert len(errors) == 1 and "no such device" in errors[0]
    deadline = time.monotonic() + 1
    while not sender.connected and time.monotonic() < deadline:
        time.sleep(0.01)
    assert sender.connected and sender.last_error is None


def test_mcu_sender_pulses_a_pin_on_the_shared_port():
    pulses = []
    done = threading.Event()

    class Handshake:
        matched = True

    class Client:
        def __init__(self, port, baudrate):
            pass

        def connect(self):
            pass

        def handshake(self):
            return Handshake()

        def send_pulse(self, pin, duration_ms):
            pulses.append((pin, duration_ms))
            done.set()

        def close(self):
            pass

    sender = McuFadeSender("PORT", (1, 2, 3, 4, 5, 6), client_factory=Client)
    sender.pulse(9, 300)
    assert done.wait(2)
    assert pulses == [(9, 300)]
