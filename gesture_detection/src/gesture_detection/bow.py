"""Recognize a held waist bow from a side-visible torso and straight neck."""

import math

from .config import (
    BOW_DWELL_SECONDS,
    BOW_MAX_ANGLE_DEGREES,
    BOW_MAX_FRAME_GAP,
    BOW_MAX_HEAD_DEVIATION_DEGREES,
    BOW_MIN_ANGLE_DEGREES,
    BOW_MIN_VISIBILITY,
)
from .gesture_position import Landmarks


class BowAnalyzer:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.state = False
        self.torso_angle: float | None = None
        self.head_deviation: float | None = None
        self.head_aligned = False
        self.hold_seconds = 0.0
        self._since: float | None = None
        self._last_time: float | None = None

    def update(self, landmarks: Landmarks, timestamp: float, aspect_ratio: float) -> bool:
        if not math.isfinite(timestamp) or not math.isfinite(aspect_ratio) or aspect_ratio <= 0:
            self.reset()
            return False
        indices = (0, 11, 12, 23, 24)
        if len(landmarks) <= max(indices) or any(
            not math.isfinite(landmarks[i].x)
            or not math.isfinite(landmarks[i].y)
            or not 0 <= landmarks[i].x <= 1
            or not 0 <= landmarks[i].y <= 1
            or getattr(landmarks[i], "visibility", 1.0) < BOW_MIN_VISIBILITY
            for i in indices
        ):
            self.reset()
            return False
        shoulder_x = (landmarks[11].x + landmarks[12].x) / 2 * aspect_ratio
        shoulder_y = (landmarks[11].y + landmarks[12].y) / 2
        hip_x = (landmarks[23].x + landmarks[24].x) / 2 * aspect_ratio
        hip_y = (landmarks[23].y + landmarks[24].y) / 2
        dx, dy = shoulder_x - hip_x, hip_y - shoulder_y
        head_dx = (landmarks[0].x * aspect_ratio) - shoulder_x
        head_dy = shoulder_y - landmarks[0].y
        torso_angle = math.degrees(math.atan2(abs(dx), dy)) if dy > 0 else 180.0
        head_angle = math.degrees(math.atan2(abs(head_dx), head_dy)) if head_dy > 0 else 180.0
        self.torso_angle = torso_angle
        self.head_deviation = abs(torso_angle - head_angle)
        # The face should continue the torso line: a head nod alone is not a bow.
        aligned = (
            dx * head_dx >= 0 and abs(torso_angle - head_angle) <= BOW_MAX_HEAD_DEVIATION_DEGREES
        )
        self.head_aligned = aligned
        valid = BOW_MIN_ANGLE_DEGREES <= torso_angle <= BOW_MAX_ANGLE_DEGREES and aligned
        gap = timestamp - self._last_time if self._last_time is not None else None
        if not valid or (gap is not None and (gap <= 0 or gap > BOW_MAX_FRAME_GAP)):
            self._since = None
            self.state = False
            self.hold_seconds = 0.0
        elif self._since is None:
            self._since = timestamp
        else:
            self.hold_seconds = timestamp - self._since
            self.state = self.hold_seconds >= BOW_DWELL_SECONDS
        self._last_time = timestamp
        return self.state
