"""Thread-safe current state and expiring, acknowledged occurrence delivery."""

import math
import threading
import uuid
from typing import Any

from gesture_detection.gesture_types import Gesture
from gesture_detection.recognition_types import GestureSample

PROTOCOL_VERSION = 1
ACK_STATUSES = {"accepted", "ignored", "expired", "duplicate"}
type Message = dict[str, Any]


class DeliveryOutbox:
    """Own delivery state only. All times are host monotonic seconds.

    Samples arrive from the recognition process. No socket operation is
    performed under this lock. Pending storage is bounded and never silently
    drops an unexpired event: exhaustion is an explicit application failure.
    """

    def __init__(
        self,
        *,
        event_ttl: float = 1.0,
        stale_timeout: float = 0.5,
        retry_interval: float = 0.1,
        max_pending: int = 64,
    ) -> None:
        if (
            any(
                not math.isfinite(v) or v <= 0
                for v in (event_ttl, stale_timeout, retry_interval)
            )
            or max_pending <= 0
        ):
            raise ValueError("Delivery limits must be positive and finite")
        self.session_id = str(uuid.uuid4())
        self.event_ttl = event_ttl
        self.stale_timeout = stale_timeout
        self.retry_interval = retry_interval
        self.max_pending = max_pending
        self._lock = threading.Lock()
        self._event_sequence = 0
        self._state_sequence = 0
        self._latest: Message | None = None
        self._pending: dict[int, Message] = {}
        self._last_sent: dict[int, float] = {}

    def _expire(self, now: float) -> None:
        for event_id, event in list(self._pending.items()):
            if now >= event["expires_at"]:
                del self._pending[event_id]
                self._last_sent.pop(event_id, None)

    def publish(self, sample: GestureSample, *, now: float) -> None:
        observed_at = sample.observed_at
        if (
            not math.isfinite(observed_at)
            or not math.isfinite(now)
            or observed_at > now
        ):
            raise ValueError("Invalid monotonic observation time")
        with self._lock:
            self._expire(now)
            self._latest = {
                "gesture": sample.gesture,
                "tracking": sample.tracking,
                "observed_at": observed_at,
                "frame_id": sample.frame_id,
                "source_timestamp": sample.source_timestamp,
                "action": sample.action,
                "phase": sample.phase,
                "booth_present": sample.booth_present,
                "action_accuracy": sample.action_accuracy,
            }
            for (kind, occurred_at), accuracy in zip(
                sample.occurrences, sample.occurrence_accuracies, strict=True
            ):
                if not math.isfinite(occurred_at) or occurred_at > now:
                    raise ValueError("Invalid occurrence source time")
                if now >= occurred_at + self.event_ttl:
                    continue
                if len(self._pending) >= self.max_pending:
                    raise RuntimeError("Gesture event outbox capacity exceeded")
                self._event_sequence += 1
                self._pending[self._event_sequence] = {
                    "version": PROTOCOL_VERSION,
                    "type": "event",
                    "session_id": self.session_id,
                    "event_id": self._event_sequence,
                    "gesture": kind,
                    "occurred_at": occurred_at,
                    "expires_at": occurred_at + self.event_ttl,
                    "frame_id": sample.frame_id,
                    "source_timestamp": sample.source_timestamp,
                }
                if accuracy is not None:
                    self._pending[self._event_sequence]["action_accuracy"] = accuracy

    def state(self, now: float) -> Message:
        with self._lock:
            self._state_sequence += 1
            latest = self._latest
            fresh = (
                latest is not None and now < latest["observed_at"] + self.stale_timeout
            )
            message = {
                "version": PROTOCOL_VERSION,
                "type": "state",
                "session_id": self.session_id,
                "sequence": self._state_sequence,
                "sent_at": now,
                "stale_timeout": self.stale_timeout,
                "fresh": fresh,
                "gesture": latest["gesture"] if fresh and latest else Gesture.NONE,
                "tracking": bool(fresh and latest and latest["tracking"]),
                "booth_present": bool(fresh and latest and latest["booth_present"]),
                "observed_at": latest["observed_at"] if latest else None,
                "frame_id": latest["frame_id"] if latest else None,
                "source_timestamp": latest["source_timestamp"] if latest else None,
            }
            if fresh and latest and latest["tracking"] and latest["action"] is not None:
                message["action"] = latest["action"]
                message["phase"] = latest["phase"]
            if (
                fresh
                and latest
                and latest["tracking"]
                and latest["gesture"] != Gesture.NONE
                and latest["action_accuracy"] is not None
            ):
                message["action_accuracy"] = latest["action_accuracy"]
            return message

    def events(self, now: float, *, reconnect: bool = False) -> list[Message]:
        with self._lock:
            self._expire(now)
            events = []
            for event_id, event in self._pending.items():
                if (
                    reconnect
                    or now - self._last_sent.get(event_id, -math.inf)
                    >= self.retry_interval
                ):
                    events.append(dict(event))
                    self._last_sent[event_id] = now
            return events

    def acknowledge(self, message: object) -> bool:
        if not isinstance(message, dict):
            return False
        if (
            type(message.get("version")) is not int
            or message.get("version") != PROTOCOL_VERSION
            or message.get("type") != "ack"
            or message.get("session_id") != self.session_id
            or type(message.get("event_id")) is not int
            or not isinstance(message.get("status"), str)
            or message["status"] not in ACK_STATUSES
        ):
            return False
        with self._lock:
            event_id = message["event_id"]
            removed = self._pending.pop(event_id, None)
            self._last_sent.pop(event_id, None)
            return removed is not None
