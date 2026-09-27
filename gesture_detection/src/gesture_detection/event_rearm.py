"""Shared, observation-based rearming for discrete actions only."""

import math

import numpy as np

from .config import (
    FANNING_EXIT_TORSO_HEIGHT,
    MULTICAM_RELEASE_MAX_GAP,
    MULTICAM_RELEASE_SECONDS,
    RAMUNE_HOLD_SECONDS,
    UCHIMIZU_FEEDBACK_SECONDS,
)
from .recognition_types import Landmark, OccurrenceEvidence

EVENT_GESTURES = frozenset({"UCHIMIZU", "RAMUNE"})


def observes_release(points: list[Landmark], gesture: str, wrist: int | None) -> bool:
    if len(points) != 33:
        return False
    p = np.asarray(points)
    wrists = [wrist] if wrist in (15, 16) else [15, 16]
    indices = [11, 12, 23, 24] + wrists
    if not np.isfinite(p[indices]).all() or (p[indices, 2] <= 0.5).any():
        return False
    if not ((p[indices, :2] >= 0) & (p[indices, :2] <= 1)).all():
        return False
    shoulder = p[[11, 12], 1].mean()
    scale = p[[23, 24], 1].mean() - shoulder
    width = abs(p[11, 0] - p[12, 0])
    if min(scale, width) <= 1e-6:
        return False
    lowered = bool(((p[wrists, 1] - shoulder) / scale >= FANNING_EXIT_TORSO_HEIGHT).all())
    if gesture == "UCHIMIZU":
        return lowered
    separated = (
        np.isfinite(p[[15, 16]]).all()
        and (p[[15, 16], 2] > 0.5).all()
        and ((p[[15, 16], :2] >= 0) & (p[[15, 16], :2] <= 1)).all()
        and abs(p[15, 0] - p[16, 0]) / width > 1.0
    )
    return lowered or bool(separated)


class EventRearmGate:
    """Release from either view plus a new setup; loss never means release."""

    def __init__(self) -> None:
        self.locked: set[str] = set()
        self._wrists: dict[str, int] = {}
        self._neutral_since: dict[str, float] = {}
        self._last_observed: dict[str, float] = {}
        self._release_at: dict[str, float] = {}
        self._feedback_end: dict[str, float] = {}
        self._active: str | None = None
        self._last_time = -math.inf

    @property
    def release_pending(self) -> tuple[str, ...]:
        return tuple(sorted(self.locked - self._release_at.keys()))

    def update(
        self,
        gesture: str,
        events: tuple[str, ...],
        now: float,
        views: list[list[Landmark]],
        evidence: dict[str, OccurrenceEvidence],
    ) -> tuple[str, tuple[str, ...]]:
        if not math.isfinite(now) or now < 0 or now <= self._last_time:
            raise ValueError("Fusion timestamps must strictly increase")
        self._last_time = now
        for label in self.locked:
            if any(observes_release(view, label, self._wrists.get(label)) for view in views):
                if now - self._last_observed.get(label, -math.inf) > MULTICAM_RELEASE_MAX_GAP:
                    self._neutral_since.pop(label, None)
                self._last_observed[label] = now
                self._neutral_since.setdefault(label, now)
                if (
                    now - self._neutral_since[label] + 1e-9 >= MULTICAM_RELEASE_SECONDS
                    and now >= self._feedback_end[label]
                ):
                    self._release_at.setdefault(label, now)
                    self._neutral_since.pop(label, None)
            else:
                self._neutral_since.pop(label, None)
                self._last_observed.pop(label, None)
        accepted = []
        for label in events:
            if label not in EVENT_GESTURES:
                raise ValueError("Unknown discrete gesture")
            item = evidence.get(label)
            if item is None:
                # Do not emit pulses that cannot subsequently be rearmed safely.
                continue
            setup = item["setup_timestamp"]
            if (
                not math.isfinite(setup)
                or setup < 0
                or setup > now
                or item["wrist_index"] not in (15, 16)
            ):
                raise ValueError("Invalid occurrence evidence")
            if label in self.locked and setup > self._release_at.get(label, math.inf):
                self.locked.remove(label)
            if label in self.locked:
                continue
            accepted.append(label)
            self.locked.add(label)
            self._wrists[label] = item["wrist_index"]
            self._neutral_since.pop(label, None)
            self._last_observed.pop(label, None)
            self._release_at.pop(label, None)
            self._feedback_end[label] = now + (
                RAMUNE_HOLD_SECONDS if label == "RAMUNE" else UCHIMIZU_FEEDBACK_SECONDS
            )
            self._active = label
        if self._active is not None and now < self._feedback_end[self._active]:
            gesture = self._active
        elif gesture in EVENT_GESTURES:
            gesture = "NONE"
        return gesture, tuple(accepted)
