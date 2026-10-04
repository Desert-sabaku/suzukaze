"""Causal fusion of timestamped camera results, independent of capture and UI."""

import heapq
import math

from .config import GESTURE_EVENT_TTL, MULTICAM_EVENT_DEDUP_SECONDS, MULTICAM_MAX_AGE_SECONDS
from .event_rearm import EVENT_GESTURES, EventRearmGate
from .recognition_types import OccurrenceEvidence, PoseResult

PRIORITY = {"NONE": 0, "RELAXING": 1, "BOW": 2, "FANNING": 3, "UCHIMIZU": 4, "RAMUNE": 5}


class MultiCameraFusion:
    """Merge once, then rearm once. Per-camera queues must preserve occurrences.

    Inputs share a monotonic source clock. Live inference can arrive out of order
    between cameras; observations and events expire according to source time.
    """

    def __init__(
        self,
        *,
        max_age: float = MULTICAM_MAX_AGE_SECONDS,
        event_ttl: float = GESTURE_EVENT_TTL,
        max_pending: int = 128,
    ) -> None:
        if any(not math.isfinite(v) or v <= 0 for v in (max_age, event_ttl)) or max_pending <= 0:
            raise ValueError("Fusion bounds must be positive and finite")
        self.max_age, self.event_ttl, self.max_pending = max_age, event_ttl, max_pending
        self.gate = EventRearmGate()
        self.latest: dict[int, PoseResult] = {}
        self._pending: list[tuple[float, int, int, PoseResult]] = []
        self._submitted: dict[int, tuple[float, int]] = {}
        self._last_event: dict[str, float] = {}
        self._time = -math.inf
        self._frame_id = -1

    def submit(self, camera: int, result: PoseResult) -> None:
        if camera not in (0, 1):
            raise ValueError("Expected camera slot 0 or 1")
        timestamp, frame_id = result.get("timestamp"), result.get("frame_id")
        if (
            timestamp is None
            or frame_id is None
            or not math.isfinite(timestamp)
            or timestamp < 0
            or frame_id < 0
        ):
            raise ValueError("Camera result needs a finite source time and frame ID")
        if camera in self._submitted:
            previous_time, previous_id = self._submitted[camera]
            if timestamp <= previous_time or frame_id <= previous_id:
                raise ValueError("Camera results must strictly increase")
        current = result.get("current", {"gesture": "NONE", "tracking": False})
        if current["gesture"] not in PRIORITY or any(
            g not in EVENT_GESTURES for g in result.get("occurrences", ())
        ):
            raise ValueError("Unknown gesture in camera result")
        if len(self._pending) >= self.max_pending:
            raise RuntimeError("Fusion input capacity exceeded")
        self._submitted[camera] = timestamp, frame_id
        heapq.heappush(self._pending, (timestamp, camera, frame_id, result))

    def advance(self, now: float) -> PoseResult:
        if not math.isfinite(now) or now < 0 or now <= self._time:
            raise ValueError("Fusion ticks must strictly increase")
        self._time = now
        self._frame_id += 1
        events: list[str] = []
        evidence: dict[str, OccurrenceEvidence] = {}
        event_times: dict[str, float] = {}
        while self._pending and self._pending[0][0] <= now + 1e-9:
            timestamp, camera, _, result = heapq.heappop(self._pending)
            self.latest[camera] = result
            if now - timestamp >= self.event_ttl:
                continue
            for label in result.get("occurrences", ()):
                if (
                    timestamp - self._last_event.get(label, -math.inf)
                    < MULTICAM_EVENT_DEDUP_SECONDS
                ):
                    continue
                item = result.get("occurrence_evidence", {}).get(label)
                if item is None:
                    continue
                if label in evidence:
                    raise RuntimeError("Multiple distinct events of one kind in a fusion tick")
                self._last_event[label] = timestamp
                events.append(label)
                evidence[label], event_times[label] = item, min(timestamp, now)
        fresh = [
            r for r in self.latest.values() if now - r.get("timestamp", -math.inf) <= self.max_age
        ]
        candidates = {
            r.get("current", {"gesture": "NONE", "tracking": False})["gesture"] for r in fresh
        }
        candidates.update(events)
        gesture = max(candidates, key=PRIORITY.__getitem__) if candidates else "NONE"
        gesture, accepted = self.gate.update(
            gesture, tuple(events), now, [r["landmarks"] for r in fresh], evidence
        )
        return {
            "landmarks": [],
            "current": {"gesture": gesture, "tracking": any(r["landmarks"] for r in fresh)},
            "selected_action": gesture if gesture in {"FANNING", "RAMUNE", "UCHIMIZU"} else "NONE",
            "relaxing_state": gesture == "RELAXING",
            "bow_state": gesture == "BOW",
            "occurrences": accepted,
            "occurrence_evidence": {g: evidence[g] for g in accepted},
            "occurrence_timestamps": {g: event_times[g] for g in accepted},
            "timestamp": now,
            "frame_id": self._frame_id,
            "observed_at": min(
                now, max((r.get("timestamp", now) for r in self.latest.values()), default=now)
            ),
            "locked_events": tuple(sorted(self.gate.locked)),
            "release_pending": self.gate.release_pending,
        }
