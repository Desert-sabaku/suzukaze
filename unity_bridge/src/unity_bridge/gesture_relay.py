"""Transparent local gesture TCP -> Unity WebSocket adapter.

The bridge owns no experience state and never acknowledges events itself.
If either leg fails, close the other; Unity reconnects to restore the session.
"""

import asyncio
import json
from typing import Any

from suzukaze_gesture_protocol import (
    MAX_MESSAGE_BYTES,
    FrameDecoder,
    decode_message,
    frame_message,
)
from websockets.exceptions import ConnectionClosed


class GestureRelay:
    def __init__(self, port: int = 5001, message_format: str = "protobuf") -> None:
        if message_format not in {"json", "protobuf"}:
            raise ValueError("Expected json or protobuf gesture format")
        self.message_format = message_format
        self.port = port
        self._connected = False

    async def serve(self, websocket: Any) -> None:
        if self._connected:
            await websocket.close(
                code=1013, reason="One Unity consumer is already connected"
            )
            return
        self._connected = True
        writer: asyncio.StreamWriter | None = None
        tasks: list[asyncio.Task] = []
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    "127.0.0.1", self.port, limit=MAX_MESSAGE_BYTES
                ),
                timeout=0.5,
            )
            tasks = [
                asyncio.create_task(self._to_unity(reader, websocket)),
                asyncio.create_task(self._to_detection(websocket, writer)),
            ]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except OSError, ValueError, TypeError, TimeoutError, ConnectionClosed:
            pass
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            try:
                if writer is not None:
                    writer.close()
                    try:
                        await asyncio.wait_for(writer.wait_closed(), 0.5)
                    except OSError, TimeoutError:
                        writer.transport.abort()
                await websocket.close(
                    code=1011, reason="Gesture connection closed; reconnect"
                )
            finally:
                self._connected = False

    async def _to_unity(self, reader: asyncio.StreamReader, websocket: Any) -> None:
        if self.message_format == "protobuf":
            decoder = FrameDecoder()
            while chunk := await reader.read(4096):
                for payload in decoder.feed(chunk):
                    if decode_message(payload)["type"] not in {"state", "event"}:
                        raise ValueError("Expected state or event payload")
                    # Validate without re-encoding: retain unknown protobuf fields.
                    await asyncio.wait_for(websocket.send(payload), 0.5)
            decoder.eof()
            return
        while True:
            line = await reader.readline()
            if not line:
                return
            if len(line) > MAX_MESSAGE_BYTES or not line.endswith(b"\n"):
                raise ValueError("Invalid gesture message")
            # Preserve timestamps and IDs, and use text WebSocket frames.
            await asyncio.wait_for(
                websocket.send(line.decode("utf-8").rstrip("\n")), 0.5
            )

    async def _to_detection(self, websocket: Any, writer: asyncio.StreamWriter) -> None:
        async for message in websocket:
            if self.message_format == "protobuf":
                if not isinstance(message, bytes):
                    raise ValueError("Expected a binary ACK")
                if decode_message(message)["type"] != "ack":
                    raise ValueError("Only ACKs are accepted in gesture mode")
                writer.write(frame_message(message))
                await asyncio.wait_for(writer.drain(), 0.5)
                continue
            if (
                not isinstance(message, str)
                or len(message.encode("utf-8")) > MAX_MESSAGE_BYTES
            ):
                raise ValueError("Expected a bounded text ACK")
            ack = json.loads(message)
            if not isinstance(ack, dict) or ack.get("type") != "ack":
                raise ValueError("Only ACKs are accepted in gesture mode")
            writer.write((json.dumps(ack, allow_nan=False) + "\n").encode("utf-8"))
            await asyncio.wait_for(writer.drain(), 0.5)
