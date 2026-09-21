import asyncio
import json

import websockets
from websockets.asyncio.server import serve

from src.gesture_relay import GestureRelay


def test_relay_preserves_event_and_forwards_only_unity_ack():
    async def scenario():
        observed = asyncio.Queue()
        release = asyncio.Event()
        payload = {
            "version": 1,
            "type": "event",
            "session_id": "one",
            "event_id": 1,
            "gesture": "RAMUNE",
            "occurred_at": 10.0,
            "expires_at": 11.0,
        }

        async def source(reader, writer):
            try:
                writer.write((json.dumps(payload) + "\n").encode())
                await writer.drain()
                ack = await reader.readline()
                await observed.put(json.loads(ack))
                await release.wait()
            finally:
                writer.close()
                await writer.wait_closed()

        async with await asyncio.start_server(source, "127.0.0.1", 0) as tcp:
            relay = GestureRelay(tcp.sockets[0].getsockname()[1])
            async with serve(relay.serve, "127.0.0.1", 0, close_timeout=0.1) as ws:
                port = ws.sockets[0].getsockname()[1]
                async with websockets.connect(f"ws://127.0.0.1:{port}") as client:
                    forwarded = await asyncio.wait_for(client.recv(), 1)
                    assert isinstance(forwarded, str)
                    assert json.loads(forwarded) == payload
                    assert observed.empty()
                    async with websockets.connect(f"ws://127.0.0.1:{port}") as other:
                        await asyncio.wait_for(other.wait_closed(), 1)
                        assert other.close_code == 1013
                    ack = {
                        "version": 1,
                        "type": "ack",
                        "session_id": "one",
                        "event_id": 1,
                        "status": "ignored",
                    }
                    await client.send(json.dumps(ack))
                    assert await asyncio.wait_for(observed.get(), 1) == ack
                    release.set()
                    await asyncio.wait_for(client.wait_closed(), 1)
            assert not relay._connected

    asyncio.run(scenario())
