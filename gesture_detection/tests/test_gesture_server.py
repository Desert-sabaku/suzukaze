import json
import socket
import time

from modules.gesture_delivery import DeliveryOutbox
from modules.gesture_server import GestureServer

from test_gesture_delivery import result


def read_type(stream, kind):
    for _ in range(30):
        message = json.loads(stream.readline())
        if message["type"] == kind:
            return message
    raise AssertionError(f"No {kind} message")


def test_tcp_reconnect_fragmented_ack_and_stale_state():
    outbox = DeliveryOutbox(event_ttl=5.0, stale_timeout=0.1)
    now = time.monotonic()
    outbox.publish(result("RAMUNE", "RAMUNE"), observed_at=now, now=now)
    server = GestureServer(outbox, port=0, state_interval=0.02)
    server.start()
    try:
        with socket.create_connection(("127.0.0.1", server.port), timeout=2) as client:
            with client.makefile("rb") as stream:
                event = read_type(stream, "event")
        with socket.create_connection(("127.0.0.1", server.port), timeout=2) as client:
            with client.makefile("rb") as stream:
                assert read_type(stream, "event") == event
                ack = (
                    json.dumps(
                        {
                            "version": 1,
                            "type": "ack",
                            "session_id": event["session_id"],
                            "event_id": event["event_id"],
                            "status": "accepted",
                        }
                    ).encode()
                    + b"\n"
                )
                client.sendall(ack[:5])
                client.sendall(ack[5:])
                state = {"fresh": True}
                for _ in range(30):
                    state = read_type(stream, "state")
                    if not state["fresh"]:
                        break
                assert not state["fresh"]
                assert state["gesture"] == "NONE"
                assert outbox.events(time.monotonic(), reconnect=True) == []
        server.check()
    finally:
        server.close()
