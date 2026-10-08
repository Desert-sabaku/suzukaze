"""Debug GUI that sends gestures to Unity without gesture_detection.

ManualGestureSource stands in for DetectionProcess: the browser sets the
current state and fires occurrences, and the relay delivers them through the
same DeliveryOutbox as real recognition. The page and its control WebSocket are
served on a separate loopback port so Unity's single-consumer socket is
untouched.
"""

import asyncio
import json
import queue
import threading
import time
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.resources import files
from typing import Any

import websockets
from gesture_detection.gesture_types import (
    ACTION_PHASES,
    CONTINUOUS_GESTURES,
    OCCURRENCE_GESTURES,
    Gesture,
    Phase,
    valid_action_phase,
)
from gesture_detection.recognition_types import GestureSample
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Request, Response

from .gesture_relay import GestureRelay

DEFAULT_DEBUG_PORT = 5080
STATUS_INTERVAL = 0.2
ACK_HISTORY = 20


class ManualGestureSource:
    """Sample source driven by the debug GUI instead of the cameras.

    get() republishes the current state every refresh seconds so it stays
    fresh, and attaches occurrences fired since the previous sample. Only the
    relay's pump thread calls get().
    """

    def __init__(self, refresh: float = 0.05) -> None:
        self.refresh = refresh
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "gesture": Gesture.NONE,
            "tracking": True,
            "booth_present": True,
            "action": None,
            "phase": None,
            "action_accuracy": None,
        }
        self._occurrences: queue.Queue[tuple[Gesture, float, float | None]] = (
            queue.Queue()
        )
        self._closed = threading.Event()
        self._frame_id = 0

    def state(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def set_state(self, fields: dict[str, Any]) -> None:
        """Replace the current state; raise ValueError if Unity would reject it."""
        state = {key: fields.get(key) for key in self._state}
        progress = (state["action"], state["phase"])
        if progress != (None, None) and not valid_action_phase(*progress):
            raise ValueError(
                f"Invalid action/phase: {state['action']} / {state['phase']}"
            )
        if not state["tracking"] or state["gesture"] == Gesture.NONE:
            state["action_accuracy"] = None
        sample = self._sample(state, time.monotonic(), (), 0)
        state.update(
            gesture=sample.gesture,
            action=sample.action,
            phase=sample.phase,
            tracking=bool(state["tracking"]),
            booth_present=bool(state["booth_present"]),
        )
        with self._lock:
            self._state = state

    def trigger(self, gesture: str, accuracy: float | None = None) -> None:
        """Queue one occurrence for delivery; raise ValueError if invalid."""
        now = time.monotonic()
        self._sample(self.state(), now, ((gesture, now, accuracy),), 0)
        self._occurrences.put((Gesture(gesture), now, accuracy))

    def get(self, timeout: float) -> GestureSample | None:
        """Return the next sample, or None once closed (like Esc in recognition)."""
        if self._closed.is_set():
            return None
        fired = []
        try:
            fired.append(self._occurrences.get(timeout=min(timeout, self.refresh)))
            while True:
                fired.append(self._occurrences.get_nowait())
        except queue.Empty:
            pass
        self._frame_id += 1
        return self._sample(
            self.state(), time.monotonic(), tuple(fired), self._frame_id
        )

    def close(self) -> None:
        self._closed.set()

    def _sample(
        self,
        state: dict[str, Any],
        now: float,
        fired: tuple[tuple[str, float, float | None], ...],
        frame_id: int,
    ) -> GestureSample:
        return GestureSample(
            state["gesture"],
            bool(state["tracking"]),
            now,
            tuple((kind, at) for kind, at, _ in fired),
            frame_id,
            now,
            action=state["action"],
            phase=state["phase"],
            booth_present=bool(state["booth_present"]),
            action_accuracy=state["action_accuracy"],
            occurrence_accuracies=tuple(accuracy for _, _, accuracy in fired),
        )


def vocabulary() -> dict[str, Any]:
    """Gesture names and valid action/phase pairs, in declaration order."""
    order = list(Gesture)
    return {
        "type": "vocab",
        "continuous": [g for g in order if g in CONTINUOUS_GESTURES],
        "occurrences": [g for g in order if g in OCCURRENCE_GESTURES],
        "action_phases": {
            action: [p for p in Phase if p in ACTION_PHASES[action]]
            for action in order
            if action in ACTION_PHASES
        },
    }


class DebugGui:
    """Browser control panel for one ManualGestureSource."""

    def __init__(self, source: ManualGestureSource, relay: GestureRelay) -> None:
        self.source = source
        self.relay = relay
        self.acks: deque[dict[str, Any]] = deque(maxlen=ACK_HISTORY)
        relay.on_ack = self._record_ack

    def _record_ack(self, ack: dict[str, Any]) -> None:
        pending = {
            event["event_id"]: event["gesture"]
            for event in self.relay.outbox.pending(time.monotonic())
        }
        self.acks.appendleft(
            {
                "event_id": ack["event_id"],
                "gesture": pending.get(ack["event_id"]),
                "status": ack["status"],
            }
        )

    def status(self) -> dict[str, Any]:
        now = time.monotonic()
        return {
            "type": "status",
            "unity_connected": self.relay.connected,
            "session_id": self.relay.outbox.session_id,
            "now": now,
            "state": self.source.state(),
            "pending": [
                {
                    "event_id": event["event_id"],
                    "gesture": event["gesture"],
                    "expires_in": event["expires_at"] - now,
                }
                for event in self.relay.outbox.pending(now)
            ],
            "acks": list(self.acks),
        }

    def handle(self, raw: str | bytes) -> dict[str, Any] | None:
        """Apply one browser command; return an error message if it failed."""
        try:
            command = json.loads(raw)
            if not isinstance(command, dict):
                raise ValueError("Expected a JSON object")  # noqa: TRY004
            if command.get("type") == "state":
                self.source.set_state(command)
            elif command.get("type") == "event":
                self.source.trigger(
                    str(command.get("gesture")), command.get("action_accuracy")
                )
            else:
                raise ValueError("Unknown command")
        except (ValueError, TypeError) as error:
            return {"type": "error", "message": str(error)}
        return None

    def process_request(self, connection: Any, request: Request) -> Response | None:
        if request.path == "/ws":
            return None
        if request.path not in ("/", "/index.html"):
            return connection.respond(404, "Not found\n")
        body = files(__package__).joinpath("gesture_debug.html").read_bytes()
        headers = Headers(
            [
                ("Content-Type", "text/html; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
            ]
        )
        return Response(200, "OK", headers, body)

    async def serve(self, websocket: Any) -> None:
        await websocket.send(json.dumps(vocabulary()))
        sender = asyncio.create_task(self._send_status(websocket))
        try:
            async for raw in websocket:
                error = self.handle(raw)
                if error is not None:
                    await websocket.send(json.dumps(error))
        except ConnectionClosed:
            pass
        finally:
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)

    async def _send_status(self, websocket: Any) -> None:
        while True:
            await websocket.send(json.dumps(self.status()))
            await asyncio.sleep(STATUS_INTERVAL)


@asynccontextmanager
async def serve_debug_gui(
    source: ManualGestureSource, relay: GestureRelay, host: str, port: int
) -> AsyncIterator[Any]:
    gui = DebugGui(source, relay)
    async with websockets.serve(
        gui.serve,
        host,
        port,
        process_request=gui.process_request,
        close_timeout=0.5,
    ) as server:
        yield server
