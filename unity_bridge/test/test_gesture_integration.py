import asyncio
import time

import pytest
import websockets
from gesture_detection.recognition_types import GestureSample
from websockets.asyncio.server import serve

from unity_bridge.bridge_relay import BridgeRelay, DetectionProcess
from unity_bridge.gesture_codec import encode_message
from unity_bridge.gesture_delivery import DeliveryOutbox
from unity_bridge.gesture_probe import GestureReceiver, decode_payload


def fake_detection(samples, stop) -> None:
    """Stand-in for gesture_detection.app.main, run in a real child process."""
    now = time.monotonic()
    samples.put(
        GestureSample(
            "FANNING",
            True,
            now,
            (("RAMUNE", now),),
            1,
            now,
            action="FANNING",
            phase="ACTIVE",
        )
    )
    while not stop.wait(0.02):
        samples.put(
            GestureSample(
                "FANNING",
                True,
                time.monotonic(),
                (),
                action="FANNING",
                phase="ACTIVE",
            )
        )


def quits(samples, stop) -> None:
    """Like pressing Esc: recognition ends on its own with exit code 0."""


def crashes(samples, stop) -> None:
    raise SystemExit(3)


@pytest.mark.parametrize("target, expected", [(quits, None), (crashes, "code 3")])
def test_child_exit_is_reported(target, expected):
    detection = DetectionProcess(target)
    detection.start()
    try:
        detection.process.join(5)
        if expected is None:
            assert detection.get(timeout=0.1) is None
        else:
            with pytest.raises(RuntimeError, match=expected):
                detection.get(timeout=0.1)
    finally:
        detection.close()


def wrong_type(samples, stop) -> None:
    samples.put({"gesture": "FANNING"})
    stop.wait(5)


def test_child_process_through_bridge_to_receiver_and_back():
    async def scenario():
        outbox = DeliveryOutbox()
        relay = BridgeRelay(outbox, state_interval=0.02)
        detection = DetectionProcess(fake_detection)
        detection.start()
        adopted = []
        receiver = GestureReceiver()
        pump = asyncio.create_task(relay.pump(detection))
        try:
            async with serve(relay.serve, "127.0.0.1", 0, close_timeout=0.1) as ws:
                port = ws.sockets[0].getsockname()[1]
                async with websockets.connect(f"ws://127.0.0.1:{port}") as client:
                    while True:
                        message = decode_payload(
                            await asyncio.wait_for(client.recv(), 5)
                        )
                        if message is None:
                            continue
                        ack = receiver.receive(
                            message,
                            time.monotonic(),
                            lambda kind: adopted.append(kind) or True,
                        )
                        if ack is not None:
                            assert ack["status"] == "accepted"
                            await client.send(encode_message(ack))
                            break
                    for _ in range(30):
                        message = decode_payload(
                            await asyncio.wait_for(client.recv(), 1)
                        )
                        if message is None:
                            continue
                        receiver.receive(message, time.monotonic(), lambda _: True)
                        if (
                            message["type"] == "state"
                            and message["gesture"] == "FANNING"
                        ):
                            break
                    assert outbox.events(time.monotonic(), reconnect=True) == []
                    assert adopted == ["RAMUNE"]
                    assert receiver.gesture == "FANNING"
                    assert (receiver.action, receiver.phase) == (
                        "FANNING",
                        "ACTIVE",
                    )
                    receiver.disconnected()
                    assert receiver.action is None and receiver.phase is None
        finally:
            pump.cancel()
            await asyncio.gather(pump, return_exceptions=True)
            detection.close()
        assert detection.process.exitcode == 0

    asyncio.run(scenario())


def test_non_sample_from_child_is_rejected():
    detection = DetectionProcess(wrong_type)
    detection.start()
    try:
        with pytest.raises(TypeError, match="GestureSample"):
            detection.get(timeout=5)
    finally:
        detection.close()
