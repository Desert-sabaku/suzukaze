from collections import deque

from .config import (
    READY_FACE_EXCLUSION_DISTANCE,
    UCHIMIZU_COOLDOWN_SECONDS,
    UCHIMIZU_FEEDBACK_SECONDS,
    UCHIMIZU_FINISH_HEIGHT,
    UCHIMIZU_LOW_HEIGHT,
    UCHIMIZU_MAX_FRAME_GAP,
    UCHIMIZU_MIN_DROP,
    UCHIMIZU_MIN_RAISE,
    UCHIMIZU_RAISE_WINDOW_SECONDS,
    UCHIMIZU_READY_TIMEOUT_SECONDS,
    UCHIMIZU_X_MARGIN,
)
from .gesture_position import (
    Landmarks,
    normalized_wrist_distances,
)


class UchimizuAnalyzer:
    """Remember a low, central scoop before accepting a downward release."""

    def __init__(self, wrist_index: int):
        self.wrist_index = wrist_index
        self.reset()

    def reset(self) -> None:
        self.state = "IDLE"
        self.history: deque[tuple[float, float]] = deque()
        self.peak = 0.0
        self.ready_at = 0.0
        self.completed_at: float | None = None
        self.last_time: float | None = None

    def update(self, landmarks: Landmarks, now: float) -> bool:
        shoulder_y = (landmarks[11].y + landmarks[12].y) / 2
        torso_height = (landmarks[23].y + landmarks[24].y) / 2 - shoulder_y
        if torso_height <= 1e-6 or any(
            getattr(landmarks[index], "visibility", 1.0) <= 0.5
            for index in (0, 11, 12, 23, 24, self.wrist_index)
        ):
            self.reset()
            return False
        if self.last_time is not None and (
            now <= self.last_time or now - self.last_time > UCHIMIZU_MAX_FRAME_GAP
        ):
            self.reset()
        self.last_time = now
        height = (landmarks[self.wrist_index].y - shoulder_y) / torso_height
        if self.completed_at is not None:
            elapsed = now - self.completed_at
            if elapsed < UCHIMIZU_FEEDBACK_SECONDS:
                return True
            self.state = "IDLE"
            if elapsed < UCHIMIZU_COOLDOWN_SECONDS:
                return False
            self.completed_at = None

        face_distance, _ = normalized_wrist_distances(landmarks, self.wrist_index)
        away_from_face = face_distance >= READY_FACE_EXCLUSION_DISTANCE
        if self.state == "READY":
            if now - self.ready_at > UCHIMIZU_READY_TIMEOUT_SECONDS or not away_from_face:
                self.state = "IDLE"
                self.history.clear()
                return False
            if height < self.peak:
                self.peak = height
                # Give the release its full window after the upward motion.
                self.ready_at = now
            # The wrist may leave the torso horizontally during the release.
            if height >= UCHIMIZU_FINISH_HEIGHT and height - self.peak >= UCHIMIZU_MIN_DROP:
                self.state = "SWING"
                self.completed_at = now
                self.history.clear()
                return True
            return False

        torso_x = [landmarks[index].x for index in (11, 12, 23, 24)]
        margin = abs(landmarks[11].x - landmarks[12].x) * UCHIMIZU_X_MARGIN
        within_torso = (
            min(torso_x) - margin <= landmarks[self.wrist_index].x <= max(torso_x) + margin
        )
        if not away_from_face or not within_torso:
            self.history.clear()
            return False
        while self.history and now - self.history[0][0] > UCHIMIZU_RAISE_WINDOW_SECONDS:
            self.history.popleft()
        if any(
            previous_height >= UCHIMIZU_LOW_HEIGHT
            and previous_height - height >= UCHIMIZU_MIN_RAISE
            for _, previous_height in self.history
        ):
            self.state = "READY"
            self.ready_at = now
            self.peak = height
            self.history.clear()
        else:
            self.history.append((now, height))
        return False
