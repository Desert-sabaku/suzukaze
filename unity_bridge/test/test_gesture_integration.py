import asyncio
import concurrent.futures
import queue
import time

import pytest
import websockets
from gesture_detection.recognition_types import GestureSample
from websockets.asyncio.server import serve

from unity_bridge.bridge_relay import (
    BridgeRelay,
    DetectionProcess,
    RestartingDetection,
)
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


def test_crashed_child_is_restarted_and_delivers_again():
    targets = iter([crashes, fake_detection])
    detection = RestartingDetection(
        lambda: DetectionProcess(next(targets)), restart_delay=0.01
    )
    detection.start()
    try:
        with pytest.raises(queue.Empty):
            detection.get(timeout=5)
        assert detection.restarts == 1
        assert isinstance(detection.get(timeout=5), GestureSample)
    finally:
        detection.close()


def test_normal_exit_is_not_restarted():
    detection = RestartingDetection(lambda: DetectionProcess(quits))
    detection.start()
    try:
        assert detection.get(timeout=5) is None
        assert detection.restarts == 0
    finally:
        detection.close()


def test_close_during_restart_delay_does_not_start_a_new_child():
    created = []

    def factory():
        created.append(DetectionProcess(crashes))
        return created[-1]

    detection = RestartingDetection(factory, restart_delay=5)
    detection.start()

    def pump():
        # Like BridgeRelay.pump: keep polling until a sample or the end.
        while True:
            try:
                return detection.get(0.1)
            except queue.Empty:
                continue

    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        waiting = pool.submit(pump)
        created[0].process.join(5)
        time.sleep(0.5)  # get() has seen the crash and is in the restart delay
        detection.close()
        assert waiting.result(timeout=1) is None
    assert len(created) == 1


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
