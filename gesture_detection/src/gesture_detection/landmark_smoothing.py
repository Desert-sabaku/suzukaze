"""Time-based smoothing for the local skeleton overlay only."""

import math

from .config import POSE_DISPLAY_MAX_GAP, POSE_DISPLAY_TIME_CONSTANT
from .recognition_types import Landmark


class LandmarkSmoother:
    """Smooth visible points without carrying coordinates across tracking loss."""

    def __init__(self) -> None:
        self._points: list[Landmark] = []
        self._timestamp: float | None = None

    def update(self, points: list[Landmark], timestamp: float) -> list[Landmark]:
        dt = timestamp - self._timestamp if self._timestamp is not None else 0.0
        if (
            not points
            or not math.isfinite(timestamp)
            or dt <= 0
            or dt > POSE_DISPLAY_MAX_GAP
            or len(points) != len(self._points)
        ):
            self._points = list(points)
            self._timestamp = timestamp if math.isfinite(timestamp) else None
            return list(points)
        alpha = -math.expm1(-dt / POSE_DISPLAY_TIME_CONSTANT)
        smoothed = []
        for (x, y, visibility), (old_x, old_y, old_visibility) in zip(
            points, self._points, strict=True
        ):
            if visibility > 0.5 and old_visibility > 0.5:
                x = old_x + alpha * (x - old_x)
                y = old_y + alpha * (y - old_y)
            smoothed.append((x, y, visibility))
        self._points = smoothed
        self._timestamp = timestamp
        return list(smoothed)
