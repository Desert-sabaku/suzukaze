"""Deterministic source, real production transports; JSON-lines control on stdio.

NUnit supplies stdin commands and waits for one flushed response per command.
The only transport instrumentation records calls after delegating to the actual
outbox. It never constructs wire messages, fabricates ACKs, or changes retries.
"""

import asyncio
import json
import sys
import threading
import time
from typing import Any

from gesture_detection.gesture_delivery import DeliveryOutbox
from gesture_detection.gesture_server import GestureServer
from unity_bridge.gesture_relay import GestureRelay
from websockets.asyncio.server import serve


class ObservedOutbox(DeliveryOutbox):
    def __init__(self) -> None:
        # Long TTL makes accepted/ignored independent of CI scheduling delays.
        super().__init__(event_ttl=60, stale_timeout=60, retry_interval=0.2)
        self.audit_lock = threading.Lock()
        self.sent: list[dict[str, Any]] = []
        self.acks: list[dict[str, Any]] = []
        self.polls = 0

    def events(self, now: float, *, reconnect: bool = False) -> list[dict[str, Any]]:
        with self.audit_lock:
            result = super().events(now, reconnect=reconnect)
            self.sent.extend(result)
            self.polls += 1
            return result

    def acknowledge(self, message: object) -> bool:
        with self.audit_lock:
            removed = super().acknowledge(message)
            self.acks.append({"message": message, "removed": removed})
            return removed

    def snapshot(self) -> dict[str, Any]:
        with self.audit_lock:
            return {
                "sent": list(self.sent),
                "acks": list(self.acks),
                "polls": self.polls,
                "now": time.monotonic(),
            }


def respond(value: dict[str, Any]) -> None:
    print(json.dumps(value, allow_nan=False), flush=True)


async def main() -> None:
    outbox = ObservedOutbox()
    source = GestureServer(outbox, port=0, message_format="protobuf")
    source.start()
    relay = GestureRelay(source.port, message_format="protobuf")
    try:
        async with serve(relay.serve, "127.0.0.1", 0) as websocket:
            port = websocket.sockets[0].getsockname()[1]
            respond({
                "ready": True,
                "uri": f"ws://127.0.0.1:{port}",
                "session": outbox.session_id,
            })
            while line := await asyncio.to_thread(sys.stdin.readline):
                source.check()
                command = json.loads(line)
                match command["command"]:
                    case "publish":
                        now = time.monotonic()
                        outbox.publish(
                            {
                                "current": {"gesture": "FANNING", "tracking": True},
                                "occurrences": ("RAMUNE",),
                                "frame_id": 42,
                                "timestamp": 1.25,
                            },
                            observed_at=now,
                            now=now,
                        )
                        respond({"occurred_at": now, "expires_at": now + 60})
                    case "snapshot":
                        respond(outbox.snapshot())
                    case "stop":
                        respond({"stopped": True})
                        break
                    case _:
                        raise ValueError("Unknown fixture command")
    finally:
        source.close()


if __name__ == "__main__":
    asyncio.run(main())
