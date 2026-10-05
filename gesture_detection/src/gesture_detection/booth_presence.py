"""Debounced foreground presence, independent of the selected gesture."""

import math

from .config import BOOTH_DWELL_SECONDS, BOOTH_RELEASE_SECONDS, SUBJECT_MAX_FRAME_GAP
from .subject_selection import Candidate, Pose, SubjectSelector


class BoothPresence:
    """Require continuous acquisition; tolerate brief loss only after arrival."""

    def __init__(
        self,
        *,
        dwell_seconds: float = BOOTH_DWELL_SECONDS,
        release_seconds: float = BOOTH_RELEASE_SECONDS,
    ) -> None:
        if any(not math.isfinite(v) or v <= 0 for v in (dwell_seconds, release_seconds)):
            raise ValueError("Booth durations must be positive and finite")
        self.dwell_seconds = dwell_seconds
        self.release_seconds = release_seconds
        self.present = False
        self.candidate: Candidate | None = None
        self.since = 0.0
        self.last_seen = 0.0
        self.last_time: float | None = None
        self.missing = False

    def update(self, landmarks: Pose, timestamp: float, aspect_ratio: float) -> bool:
        if not math.isfinite(timestamp) or timestamp < 0:
            raise ValueError("Booth timestamps must be finite and non-negative")
        if not math.isfinite(aspect_ratio) or aspect_ratio <= 0:
            raise ValueError("Aspect ratio must be positive and finite")
        if self.last_time is not None and (
            timestamp <= self.last_time or timestamp - self.last_time > SUBJECT_MAX_FRAME_GAP
        ):
            self.present = False
            self.candidate = None
        self.last_time = timestamp
        candidate = SubjectSelector.candidate(landmarks, aspect_ratio)
        if candidate is None:
            self.missing = True
            if not self.present or timestamp - self.last_seen >= self.release_seconds:
                self.present = False
                self.candidate = None
            return self.present
        if (
            self.candidate is None
            or not SubjectSelector.matches(candidate, self.candidate)
            or (self.missing and timestamp - self.last_seen >= self.release_seconds)
        ):
            self.present = False
            self.since = timestamp
        self.candidate = candidate
        self.missing = False
        self.last_seen = timestamp
        self.present = self.present or timestamp - self.since >= self.dwell_seconds
        return self.present
