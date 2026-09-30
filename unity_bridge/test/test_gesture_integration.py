import asyncio
import time

import pytest
import websockets
from gesture_detection.gesture_delivery import DeliveryOutbox
from gesture_detection.gesture_server import GestureServer
from websockets.asyncio.server import serve

from unity_bridge.gesture_probe import GestureReceiver, decode_payload, encode_ack
from unity_bridge.gesture_relay import GestureRelay


@pytest.mark.parametrize("message_format", ["json", "protobuf"])
def test_recognition_outbox_through_bridge_to_receiver_and_back(message_format):
    async def scenario():
        outbox = DeliveryOutbox()
        now = time.monotonic()
        outbox.publish(
            {
                "landmarks": [],
                "selected_action": "RAMUNE",
                "relaxing_state": False,
                "current": {"gesture": "RAMUNE", "tracking": True},
                "occurrences": ("RAMUNE",),
                "timestamp": now,
                "frame_id": 1,
            },
            observed_at=now,
            now=now,
        )
        server = GestureServer(
            outbox, port=0, state_interval=0.02, message_format=message_format
        )
        server.start()
        adopted = []
        receiver = GestureReceiver()
        try:
            relay = GestureRelay(server.port, message_format)
            async with serve(relay.serve, "127.0.0.1", 0, close_timeout=0.1) as ws:
                port = ws.sockets[0].getsockname()[1]
                async with websockets.connect(f"ws://127.0.0.1:{port}") as client:
                    while True:
                        message = decode_payload(
                            await asyncio.wait_for(client.recv(), 1), message_format
                        )
                        ack = receiver.receive(
                            message,
                            time.monotonic(),
                            lambda kind: adopted.append(kind) or True,
                        )
                        if ack is not None:
                            assert ack["status"] == "accepted"
                            await client.send(encode_ack(ack, message_format))
                            break
                    for _ in range(30):
                        message = decode_payload(
                            await asyncio.wait_for(client.recv(), 1), message_format
                        )
                        receiver.receive(message, time.monotonic(), lambda _: True)
                        if message["type"] == "state" and not message["fresh"]:
                            break
                    assert outbox.events(time.monotonic(), reconnect=True) == []
                    assert adopted == ["RAMUNE"]
                    assert not receiver.fresh
                    assert receiver.gesture == "NONE"
        finally:
            server.close()

    asyncio.run(scenario())
