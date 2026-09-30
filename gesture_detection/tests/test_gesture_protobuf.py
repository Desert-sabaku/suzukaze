import socket
import time

import pytest
from suzukaze_gesture_protocol import FrameDecoder, decode_message, encode_message, frame_message

from gesture_detection.gesture_delivery import DeliveryOutbox
from gesture_detection.gesture_server import GestureServer


@pytest.mark.parametrize(
    "bad",
    [
        b"\0\0\0\0",
        b"\0\0\x20\x01",
        frame_message(b"\xff"),
        b"\0\0",
        b"\0\0\0\x05\x08",
        frame_message(
            encode_message(
                dict(
                    version=1,
                    type="event",
                    session_id="x",
                    event_id=1,
                    gesture="RAMUNE",
                    occurred_at=1.0,
                    expires_at=2.0,
                )
            )
        ),
    ],
)
def test_invalid_client_disconnects_without_killing_worker(bad):
    server = GestureServer(DeliveryOutbox(), port=0, message_format="protobuf")
    server.start()
    try:
        with socket.create_connection(("127.0.0.1", server.port), timeout=1) as client:
            for byte in bad:
                client.sendall(bytes([byte]))
            client.shutdown(socket.SHUT_WR)
            while client.recv(4096):
                pass
        with socket.create_connection(("127.0.0.1", server.port), timeout=1) as client:
            decoder = FrameDecoder()
            frames = []
            while not frames:
                frames = decoder.feed(client.recv(4096))
            assert decode_message(frames[0])["type"] == "state"
        server.check()
    finally:
        server.close()


def test_fragmented_ack_wrong_session_does_not_remove_pending_event():
    outbox = DeliveryOutbox(event_ttl=10)
    now = time.monotonic()
    outbox.publish(
        {
            "landmarks": [],
            "selected_action": "RAMUNE",
            "relaxing_state": False,
            "occurrences": ("RAMUNE",),
        },
        observed_at=now,
        now=now,
    )
    server = GestureServer(outbox, port=0, message_format="protobuf")
    server.start()
    try:
        with socket.create_connection(("127.0.0.1", server.port), timeout=1) as client:
            ack = dict(version=1, type="ack", session_id="wrong", event_id=1, status="accepted")
            client.sendall(frame_message(encode_message(ack)))
            decoder = FrameDecoder()
            # Wait for a later state, after the server has processed this ACK.
            states = 0
            while states < 2:
                states += sum(
                    decode_message(p)["type"] == "state" for p in decoder.feed(client.recv(4096))
                )
            assert outbox.events(time.monotonic(), reconnect=True)
            ack["session_id"] = outbox.session_id
            for byte in frame_message(encode_message(ack)):
                client.sendall(bytes([byte]))
            deadline = time.monotonic() + 1
            while outbox.events(time.monotonic(), reconnect=True):
                assert time.monotonic() < deadline
                time.sleep(0.01)
    finally:
        server.close()
