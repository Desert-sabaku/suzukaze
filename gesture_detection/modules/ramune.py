"""Two-hand Ramune motion, independent of camera and object detection."""

import math
from collections.abc import Sequence
from typing import Protocol

from .config import (
    RAMUNE_ALIGN_TOLERANCE,
    RAMUNE_BASE_TOLERANCE,
    RAMUNE_CONTACT_GAP,
    RAMUNE_DWELL_SECONDS,
    RAMUNE_HOLD_SECONDS,
    RAMUNE_MAX_FRAME_GAP,
    RAMUNE_MAX_READY_GAP,
    RAMUNE_MIN_PRESS,
    RAMUNE_MIN_READY_GAP,
    RAMUNE_PRESS_TIMEOUT,
)


class Landmark(Protocol):
    x: float
    y: float
    visibility: float


class RamuneAnalyzer:
    """Require a stable lower hand followed by a downward upper-hand press."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.state = "IDLE"
        self.base_index: int | None = None
        self.base = (0.0, 0.0)
        self.upper_y = 0.0
        self.scale = 1.0
        self.since = 0.0
        self.last_time: float | None = None

    def update(self, landmarks: Sequence[Landmark], now: float) -> bool:
        if self.last_time is not None and (
            now <= self.last_time or now - self.last_time > RAMUNE_MAX_FRAME_GAP
        ):
            self.reset()
        self.last_time = now
        if len(landmarks) < 25 or any(
            landmarks[i].visibility <= 0.5
            or not all(math.isfinite(v) for v in (landmarks[i].x, landmarks[i].y))
            for i in (11, 12, 15, 16, 23, 24)
        ):
            self.reset()
            return False
        scale = abs(landmarks[11].x - landmarks[12].x)
        if scale < 1e-6:
            self.reset()
            return False
        lower = max((15, 16), key=lambda i: landmarks[i].y)
        upper = 31 - lower
        gap = (landmarks[lower].y - landmarks[upper].y) / scale
        aligned = abs(landmarks[15].x - landmarks[16].x) / scale <= RAMUNE_ALIGN_TOLERANCE
        shoulder_y = (landmarks[11].y + landmarks[12].y) / 2
        hip_y = (landmarks[23].y + landmarks[24].y) / 2
        in_torso = shoulder_y <= landmarks[lower].y <= hip_y
        ready = aligned and in_torso and RAMUNE_MIN_READY_GAP <= gap <= RAMUNE_MAX_READY_GAP

        if self.state == "OPENED":
            if now - self.since < RAMUNE_HOLD_SECONDS:
                return True
            self.state = "WAIT_RELEASE"
        if self.state == "WAIT_RELEASE":
            # A new separated-hand preparation is required after each opening.
            if ready:
                self.reset()
            return False
        if self.state == "IDLE":
            if ready:
                self.state = "FORMING"
                self.base_index = lower
                self.base = (landmarks[lower].x, landmarks[lower].y)
                self.upper_y = landmarks[upper].y
                self.scale = scale
                self.since = now
            return False

        assert self.base_index is not None
        base = landmarks[self.base_index]
        pressing = landmarks[31 - self.base_index]
        stable = math.dist(self.base, (base.x, base.y)) / self.scale <= RAMUNE_BASE_TOLERANCE
        if not stable or not aligned or not in_torso:
            self.reset()
            return False
        if self.state == "FORMING":
            if not ready or lower != self.base_index:
                self.reset()
            elif now - self.since >= RAMUNE_DWELL_SECONDS:
                self.state = "READY"
                self.upper_y = pressing.y
                self.since = now
            return False
        if now - self.since > RAMUNE_PRESS_TIMEOUT:
            self.reset()
            return False
        press = (pressing.y - self.upper_y) / self.scale
        remaining = (base.y - pressing.y) / self.scale
        if press < -RAMUNE_BASE_TOLERANCE or remaining < -RAMUNE_CONTACT_GAP:
            self.reset()
            return False
        if press >= RAMUNE_MIN_PRESS and abs(remaining) <= RAMUNE_CONTACT_GAP:
            self.state = "OPENED"
            self.since = now
            return True
        return False
