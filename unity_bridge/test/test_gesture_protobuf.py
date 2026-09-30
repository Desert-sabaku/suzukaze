import asyncio

import pytest
import websockets
from suzukaze_gesture_protocol import encode_message, frame_message
from websockets.asyncio.server import serve

from unity_bridge.gesture_relay import GestureRelay

EVENT = encode_message(
    {
        "version": 1,
        "type": "event",
        "session_id": "one",
        "event_id": 1,
        "gesture": "RAMUNE",
        "occurred_at": 10.0,
        "expires_at": 11.0,
    }
)
ACK = encode_message(
    {
        "version": 1,
        "type": "ack",
        "session_id": "one",
        "event_id": 1,
        "status": "accepted",
    }
)
UNKNOWN = b"\xa0\x06\x01"  # field 100, varint 1


def test_fragmented_coalesced_frames_and_unknown_fields_round_trip():
    async def scenario():
        observed = asyncio.Queue()
        release = asyncio.Event()

        async def source(reader, writer):
            try:
                data = frame_message(EVENT + UNKNOWN) * 2
                for chunk in (data[:1], data[1:3], data[3:7], data[7:]):
                    writer.write(chunk)
                    await writer.drain()
                    await asyncio.sleep(0)
                size = int.from_bytes(await reader.readexactly(4), "big")
                await observed.put(await reader.readexactly(size))
                await release.wait()
            finally:
                writer.close()
                await writer.wait_closed()

        async with await asyncio.start_server(source, "127.0.0.1", 0) as tcp:
            relay = GestureRelay(tcp.sockets[0].getsockname()[1], "protobuf")
            async with (
                serve(relay.serve, "127.0.0.1", 0) as ws,
                websockets.connect(
                    f"ws://127.0.0.1:{ws.sockets[0].getsockname()[1]}"
                ) as client,
            ):
                for _ in range(2):
                    assert await asyncio.wait_for(client.recv(), 1) == EVENT + UNKNOWN
                assert observed.empty()
                await client.send(ACK + UNKNOWN)
                assert await asyncio.wait_for(observed.get(), 1) == ACK + UNKNOWN
                release.set()

    asyncio.run(scenario())


@pytest.mark.parametrize("payload", ["text", b"\xff", EVENT, b"x" * 8193])
def test_bad_websocket_ack_closes_both_legs(payload):
    async def scenario():
        closed = asyncio.Event()

        async def source(reader, writer):
            try:
                assert await reader.read() == b""
            finally:
                writer.close()
                await writer.wait_closed()
                closed.set()

        async with await asyncio.start_server(source, "127.0.0.1", 0) as tcp:
            relay = GestureRelay(tcp.sockets[0].getsockname()[1], "protobuf")
            async with (
                serve(relay.serve, "127.0.0.1", 0) as ws,
                websockets.connect(
                    f"ws://127.0.0.1:{ws.sockets[0].getsockname()[1]}"
                ) as client,
            ):
                await client.send(payload)
                await asyncio.wait_for(client.wait_closed(), 1)
                await asyncio.wait_for(closed.wait(), 1)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "data",
    [
        b"\0\0\0\0",
        b"\0\0\x20\x01",
        b"\0\0",
        b"\0\0\0\x05\x08",
        frame_message(b"\xff"),
        frame_message(ACK),
    ],
)
def test_bad_tcp_payload_closes_websocket(data):
    async def scenario():
        async def source(reader, writer):
            writer.write(data)
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        async with await asyncio.start_server(source, "127.0.0.1", 0) as tcp:
            relay = GestureRelay(tcp.sockets[0].getsockname()[1], "protobuf")
            async with (
                serve(relay.serve, "127.0.0.1", 0) as ws,
                websockets.connect(
                    f"ws://127.0.0.1:{ws.sockets[0].getsockname()[1]}"
                ) as client,
            ):
                await asyncio.wait_for(client.wait_closed(), 1)
                assert client.close_code == 1011

    asyncio.run(scenario())
