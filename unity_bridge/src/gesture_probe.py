"""Mock Unity receiver: print decisions and acknowledge without device output."""

import argparse
import asyncio
import json
import math
import time
from collections.abc import Callable
from typing import Any

import websockets


def finite_number(value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError("Expected finite time")
    return float(value)


class GestureReceiver:
    """Reference receiver policy. Keep this object across connection retries."""

    def __init__(self) -> None:
        self.session_id: str | None = None
        self.gesture = "NONE"
        self.tracking = False
        self.fresh = False
        self._last_state = -math.inf
        self._observed_at = -math.inf
        self._timeout = 0.5
        self._sequence = 0
        self._seen: dict[int, float] = {}

    def disconnected(self) -> None:
        self.gesture = "NONE"
        self.tracking = self.fresh = False
        self._last_state = -math.inf

    def poll(self, now: float) -> None:
        if now >= min(self._last_state, self._observed_at) + self._timeout:
            self.disconnected()

    def receive(
        self,
        message: dict[str, Any],
        now: float,
        accept: Callable[[str], bool],
    ) -> dict[str, Any] | None:
        if not isinstance(message, dict):
            raise TypeError("Expected a gesture object")
        self.poll(now)
        if (
            type(message.get("version")) is not int
            or message.get("version") != 1
            or not isinstance(message.get("session_id"), str)
            or not message["session_id"]
            or message.get("type") not in ("state", "event")
        ):
            raise ValueError("Unsupported gesture envelope")
        if message["session_id"] != self.session_id:
            self.disconnected()
            self._sequence = 0
            self._seen.clear()
            self.session_id = message["session_id"]
        self._seen = {key: expiry for key, expiry in self._seen.items() if now < expiry}
        if message["type"] == "state":
            sequence = message.get("sequence")
            if type(sequence) is not int or sequence <= 0:
                raise ValueError("Invalid state sequence")
            if sequence <= self._sequence:
                return None
            timeout = finite_number(message.get("stale_timeout"))
            if timeout <= 0:
                raise ValueError("Invalid stale timeout")
            observed = message.get("observed_at")
            observed_at = -math.inf if observed is None else finite_number(observed)
            gesture = message.get("gesture")
            if gesture not in ("NONE", "FANNING", "RELAXING"):
                raise ValueError("Unknown continuous gesture")
            if (
                type(message.get("tracking")) is not bool
                or type(message.get("fresh")) is not bool
            ):
                raise ValueError("Expected state flags")
            self._sequence = sequence
            self._last_state = now
            self._observed_at = observed_at
            self._timeout = timeout
            self.fresh = message["fresh"] and observed_at <= now < observed_at + timeout
            self.tracking = self.fresh and message["tracking"]
            self.gesture = gesture if self.tracking else "NONE"
            return None
        event_id = message.get("event_id")
        if type(event_id) is not int or event_id <= 0:
            raise ValueError("Invalid event ID")
        occurred = finite_number(message.get("occurred_at"))
        expires = finite_number(message.get("expires_at"))
        kind = message.get("gesture")
        if kind not in ("RAMUNE", "UCHIMIZU") or expires <= occurred or occurred > now:
            raise ValueError("Invalid event or incompatible host clock")
        if now >= expires:
            status = "expired"
        elif event_id in self._seen:
            status = "duplicate"
        else:
            # The callback represents Unity's scene decision, not raw receipt.
            status = "accepted" if accept(kind) else "ignored"
            self._seen[event_id] = expires
        return {
            "version": 1,
            "type": "ack",
            "session_id": self.session_id,
            "event_id": event_id,
            "status": status,
        }


async def run(url: str, ignore_events: bool = False) -> None:
    receiver = GestureReceiver()
    while True:
        try:
            async with websockets.connect(
                url, open_timeout=1, close_timeout=0.5, max_size=8192
            ) as socket:
                print(f"Connected: {url}", flush=True)
                while True:
                    try:
                        raw = await asyncio.wait_for(socket.recv(), timeout=0.1)
                    except TimeoutError:
                        receiver.poll(time.monotonic())
                        continue
                    message = json.loads(raw)
                    ack = receiver.receive(
                        message, time.monotonic(), lambda _: not ignore_events
                    )
                    print(
                        json.dumps(
                            {
                                "state": receiver.gesture,
                                "tracking": receiver.tracking,
                                "fresh": receiver.fresh,
                                "decision": ack,
                            }
                        ),
                        flush=True,
                    )
                    if ack is not None:
                        await socket.send(json.dumps(ack))
        except (
            OSError,
            ValueError,
            TypeError,
            TimeoutError,
            websockets.exceptions.ConnectionClosed,
        ) as error:
            receiver.disconnected()
            print(f"Disconnected; state cleared: {error}", flush=True)
            await asyncio.sleep(0.1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="ws://127.0.0.1:5000")
    parser.add_argument(
        "--ignore-events", action="store_true", help="Simulate a busy scene"
    )
    args = parser.parse_args()
    try:
        asyncio.run(run(args.url, args.ignore_events))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
