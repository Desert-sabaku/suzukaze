"""Causal fusion of timestamped camera results, independent of capture and UI."""

import heapq
import math

from .config import GESTURE_EVENT_TTL, MULTICAM_EVENT_DEDUP_SECONDS, MULTICAM_MAX_AGE_SECONDS
from .event_rearm import EVENT_GESTURES, EventRearmGate
from .gesture_types import Gesture, Phase
from .recognition_types import OccurrenceEvidence, PoseResult, recognition_phase

PRIORITY: dict[str, int] = {
    Gesture.NONE: 0,
    Gesture.RELAXING: 1,
    Gesture.BOW: 2,
    Gesture.FANNING: 3,
    Gesture.UCHIMIZU: 4,
    Gesture.RAMUNE: 5,
}
# WAIT_RELEASE ends an occurrence, so another camera's new preparation wins.
PHASE_PROGRESS: dict[str | None, int] = {
    Phase.FORMING: 1,
    Phase.READY: 2,
    Phase.SWING: 3,
    Phase.OPENED: 3,
}


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
        current = result.get("current", {"gesture": Gesture.NONE, "tracking": False})
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
        event_scores: dict[str, float | None] = {}
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
                event_scores[label] = result.get("occurrence_accuracies", {}).get(label)
        fresh = [
            r for r in self.latest.values() if now - r.get("timestamp", -math.inf) <= self.max_age
        ]
        candidates = {
            r.get("current", {"gesture": Gesture.NONE, "tracking": False})["gesture"] for r in fresh
        }
        # As in a single view, Ramune preparation suppresses fanning. Another
        # angle often reads the stacked hands' small motion as fanning.
        if any(r.get("ramune_state") in {Phase.FORMING, Phase.READY} for r in fresh):
            candidates.discard(Gesture.FANNING)
        candidates.update(events)
        gesture = max(candidates, key=PRIORITY.__getitem__) if candidates else Gesture.NONE
        gesture, accepted = self.gate.update(
            gesture, tuple(events), now, [r["landmarks"] for r in fresh], evidence
        )
        phases = [(*recognition_phase(r), r.get("timestamp", 0.0)) for r in fresh]
        phases = [item for item in phases if item[0] is not None]
        # Prefer progress for the fused action; otherwise use action priority,
        # then the furthest phase, so independent per-camera analyzers do not
        # alternate the output. Never combine two cameras' fields.
        selected_phase = max(
            phases,
            key=lambda item: (
                item[0] == gesture,
                PRIORITY.get(item[0] or Gesture.NONE, 0),
                PHASE_PROGRESS.get(item[1], 0),
                item[2],
            ),
            default=(None, None, 0.0),
        )
        score_source = max(
            (
                r
                for r in fresh
                if r.get("current", {}).get("gesture") == gesture
                and r.get("current", {}).get("tracking")
            ),
            key=lambda r: r.get("timestamp", 0.0),
            default=None,
        )
        return {
            "action_accuracy": score_source.get("action_accuracy") if score_source else None,
            "occurrence_accuracies": {g: event_scores[g] for g in accepted},
            # Only the first (ROI/subject-selection) camera owns booth presence.
            "booth_present": any(
                r is self.latest.get(0) and r.get("booth_present", False) for r in fresh
            ),
            "landmarks": [],
            "current": {"gesture": gesture, "tracking": any(r["landmarks"] for r in fresh)},
            "selected_action": gesture
            if gesture in {Gesture.FANNING, Gesture.RAMUNE, Gesture.UCHIMIZU}
            else Gesture.NONE,
            "relaxing_state": gesture == Gesture.RELAXING,
            "bow_state": gesture == Gesture.BOW,
            "action": selected_phase[0],
            "phase": selected_phase[1],
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
