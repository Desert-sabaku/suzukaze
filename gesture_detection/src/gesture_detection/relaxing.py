"""Whole-body stillness in source time, with immediate motion release."""

import math

import numpy as np

from .config import (
    RELAXING_DWELL_SECONDS,
    RELAXING_LANDMARKS,
    RELAXING_MAX_DRIFT,
    RELAXING_MAX_FRAME_GAP,
    RELAXING_MAX_SPEED,
    RELAXING_MIN_VISIBILITY,
    RELAXING_TORSO_LANDMARKS,
)
from .gesture_position import Landmarks


class RelaxingAnalyzer:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.state = False
        self.motion_speed: float | None = None
        self.drift = 0.0
        self.still_seconds = 0.0
        self._previous: np.ndarray | None = None
        self._anchor: np.ndarray | None = None
        self._visible: np.ndarray | None = None
        self._last_time: float | None = None
        self._still_since = 0.0
        self._scale = 1.0

    def update(self, landmarks: Landmarks, timestamp: float, aspect_ratio: float) -> bool:
        if not math.isfinite(timestamp) or not math.isfinite(aspect_ratio) or aspect_ratio <= 0:
            self.reset()
            return False
        points = np.asarray([(point.x, point.y) for point in landmarks], dtype=np.float64)
        visible = np.asarray(
            [
                getattr(point, "visibility", 1.0) >= RELAXING_MIN_VISIBILITY
                and math.isfinite(point.x)
                and math.isfinite(point.y)
                and 0 <= point.x <= 1
                and 0 <= point.y <= 1
                for point in landmarks
            ],
            dtype=bool,
        )
        if len(points) <= max(RELAXING_LANDMARKS) or not all(
            visible[index] for index in RELAXING_TORSO_LANDMARKS
        ):
            self.reset()
            return False
        # Put x and y in the same image-height units before comparing distances.
        points[:, 0] *= aspect_ratio
        scale = float(np.linalg.norm((points[11] + points[12] - points[23] - points[24]) / 2))
        if scale <= 1e-6:
            self.reset()
            return False
        current = points[list(RELAXING_LANDMARKS)]
        tracked = visible[list(RELAXING_LANDMARKS)]
        dt = timestamp - self._last_time if self._last_time is not None else 0.0
        if (
            self._previous is None
            or self._anchor is None
            or dt <= 0
            or dt > RELAXING_MAX_FRAME_GAP
            or self._visible is None
            or not np.array_equal(tracked, self._visible)
        ):
            # Unknown motion across a gap or tracking change is not stillness.
            self.state = False
            self.motion_speed = None
            self.drift = 0.0
            self._anchor = current.copy()
            self._still_since = timestamp
            self._scale = scale
        else:
            self.motion_speed = float(
                np.max(np.linalg.norm(current[tracked] - self._previous[tracked], axis=1))
                / self._scale
                / dt
            )
            self.drift = float(
                np.max(np.linalg.norm(current[tracked] - self._anchor[tracked], axis=1))
                / self._scale
            )
            if self.motion_speed > RELAXING_MAX_SPEED or self.drift > RELAXING_MAX_DRIFT:
                self.state = False
                self._anchor = current.copy()
                self._still_since = timestamp
                self._scale = scale
            else:
                self.state = timestamp - self._still_since >= RELAXING_DWELL_SECONDS
        self.still_seconds = timestamp - self._still_since
        self._previous = current
        self._visible = tracked
        self._last_time = timestamp
        return self.state
