"""Select a foreground participant without cropping their limbs."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from .config import (
    SUBJECT_ACQUIRE_SECONDS,
    SUBJECT_AREA,
    SUBJECT_MAX_CENTER_DISTANCE,
    SUBJECT_MAX_FRAME_GAP,
    SUBJECT_MAX_SCALE_RATIO,
    SUBJECT_MIN_SCALE_RATIO,
    SUBJECT_MIN_SHOULDER_WIDTH,
    SUBJECT_MIN_TORSO_HEIGHT,
    SUBJECT_MIN_VISIBILITY,
    SUBJECT_RELEASE_SECONDS,
)


class Landmark(Protocol):
    x: float
    y: float
    visibility: float


type Pose = Sequence[Landmark]


@dataclass(frozen=True)
class Candidate:
    landmarks: Pose
    x: float
    y: float
    scale: float


class SubjectSelector:
    """Geometric continuity, not biometric identity; ambiguity produces no pose."""

    def __init__(self) -> None:
        self.active: Candidate | None = None
        self.pending: Candidate | None = None
        self.pending_since = 0.0
        self.last_seen = 0.0
        self.last_time: float | None = None
        self.state = "SEARCHING"

    @staticmethod
    def candidate(points: Pose, aspect_ratio: float) -> Candidate | None:
        if len(points) < 25:
            return None
        torso = [points[i] for i in (11, 12, 23, 24)]
        if any(
            not math.isfinite(p.visibility)
            or p.visibility <= SUBJECT_MIN_VISIBILITY
            or not all(math.isfinite(v) and 0 <= v <= 1 for v in (p.x, p.y))
            for p in torso
        ):
            return None
        shoulder_x = (torso[0].x + torso[1].x) / 2
        shoulder_y = (torso[0].y + torso[1].y) / 2
        hip_x = (torso[2].x + torso[3].x) / 2
        hip_y = (torso[2].y + torso[3].y) / 2
        x, y = (shoulder_x + hip_x) / 2, (shoulder_y + hip_y) / 2
        left, top, right, bottom = SUBJECT_AREA
        if not (left <= x <= right and top <= y <= bottom):
            return None
        if abs(torso[0].x - torso[1].x) < SUBJECT_MIN_SHOULDER_WIDTH:
            return None
        if hip_y - shoulder_y < SUBJECT_MIN_TORSO_HEIGHT:
            return None
        scale = math.hypot((hip_x - shoulder_x) * aspect_ratio, hip_y - shoulder_y)
        return Candidate(points, x * aspect_ratio, y, scale)

    @staticmethod
    def matches(candidate: Candidate, previous: Candidate) -> bool:
        return (
            SUBJECT_MIN_SCALE_RATIO <= candidate.scale / previous.scale <= SUBJECT_MAX_SCALE_RATIO
            and math.hypot(candidate.x - previous.x, candidate.y - previous.y)
            <= previous.scale * SUBJECT_MAX_CENTER_DISTANCE
        )

    def select(self, poses: Sequence[Pose], timestamp: float, aspect_ratio: float) -> Pose:
        if not math.isfinite(timestamp) or timestamp < 0:
            raise ValueError("Subject timestamps must be finite and non-negative")
        if not math.isfinite(aspect_ratio) or aspect_ratio <= 0:
            raise ValueError("Aspect ratio must be positive and finite")
        if self.last_time is not None and (
            timestamp <= self.last_time or timestamp - self.last_time > SUBJECT_MAX_FRAME_GAP
        ):
            self.active = self.pending = None
        self.last_time = timestamp
        candidates = [
            candidate
            for points in poses
            if (candidate := self.candidate(points, aspect_ratio)) is not None
        ]
        if self.active is not None:
            matches = [c for c in candidates if self.matches(c, self.active)]
            if len(matches) == 1:
                self.active = matches[0]
                self.last_seen = timestamp
                self.state = "TRACKING"
                return self.active.landmarks
            self.state = "LOST"
            self.pending = None
            if timestamp - self.last_seen < SUBJECT_RELEASE_SECONDS:
                return []
            self.active = None
        # Wait for a sole eligible foreground person; never use result order as identity.
        if len(candidates) != 1:
            self.pending = None
            self.state = "SEARCHING"
            return []
        candidate = candidates[0]
        if self.pending is None or not self.matches(candidate, self.pending):
            self.pending_since = timestamp
        self.pending = candidate
        self.state = "ACQUIRING"
        if timestamp - self.pending_since < SUBJECT_ACQUIRE_SECONDS:
            return []
        self.active = candidate
        self.pending = None
        self.last_seen = timestamp
        self.state = "TRACKING"
        return candidate.landmarks
