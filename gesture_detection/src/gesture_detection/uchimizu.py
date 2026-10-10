import math
from collections import deque

from .action_accuracy import aggregate, maximum, minimum
from .config import (
    MULTICAM_SCOOP_MIN_MOTION_SECONDS,
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
from .gesture_position import normalized_wrist_distances
from .gesture_types import Phase
from .pose_landmarks import (
    NOSE,
    TORSO,
    Landmarks,
    hip_center_y,
    shoulder_center_y,
    shoulder_width,
    torso_x_range,
)


class UchimizuAnalyzer:
    """Remember a low, central scoop before accepting a downward release."""

    def __init__(self, wrist_index: int):
        self.wrist_index = wrist_index
        self.reset()

    def reset(self) -> None:
        self.state = Phase.IDLE
        self.setup_started_at: float | None = None
        self.history: deque[tuple[float, float]] = deque()
        self.peak = 0.0
        self.ready_at = 0.0
        self.completed_at: float | None = None
        self.last_time: float | None = None
        self.action_accuracy: float | None = None
        self._preparation_scores: tuple[float, ...] = ()

    def update(self, landmarks: Landmarks, now: float) -> bool:
        shoulder_y = shoulder_center_y(landmarks)
        torso_height = hip_center_y(landmarks) - shoulder_y
        if torso_height <= 1e-6 or any(
            getattr(landmarks[index], "visibility", 1.0) <= 0.5
            for index in (NOSE, *TORSO, self.wrist_index)
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
            self.state = Phase.IDLE
            if elapsed < UCHIMIZU_COOLDOWN_SECONDS:
                return False
            self.completed_at = None

        face_distance, _ = normalized_wrist_distances(landmarks, self.wrist_index)
        away_from_face = face_distance >= READY_FACE_EXCLUSION_DISTANCE
        if self.state == Phase.READY:
            # A close camera puts a chest-height scoop near the face; only a
            # wrist raised beside the face (above the shoulders) cancels it.
            if now - self.ready_at > UCHIMIZU_READY_TIMEOUT_SECONDS or (
                not away_from_face and height < 0
            ):
                self.state = Phase.IDLE
                self.history.clear()
                return False
            if height < self.peak:
                self.peak = height
                # Give the release its full window after the upward motion.
                self.ready_at = now
            # The wrist may leave the torso horizontally during the release.
            if height >= UCHIMIZU_FINISH_HEIGHT and height - self.peak >= UCHIMIZU_MIN_DROP:
                self.action_accuracy = aggregate(
                    *self._preparation_scores,
                    minimum(height, UCHIMIZU_FINISH_HEIGHT),
                    minimum(height - self.peak, UCHIMIZU_MIN_DROP),
                    maximum(now - self.ready_at, UCHIMIZU_READY_TIMEOUT_SECONDS),
                )
                self.state = Phase.SWING
                self.completed_at = now
                self.history.clear()
                return True
            return False

        torso_left, torso_right = torso_x_range(landmarks)
        margin = shoulder_width(landmarks) * UCHIMIZU_X_MARGIN
        within_torso = torso_left - margin <= landmarks[self.wrist_index].x <= torso_right + margin
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
            start_time, start_height = max(
                (
                    (t, h)
                    for t, h in self.history
                    if h >= UCHIMIZU_LOW_HEIGHT and h - height >= UCHIMIZU_MIN_RAISE
                ),
                key=lambda item: item[1],
            )
            self._preparation_scores = (
                minimum(start_height, UCHIMIZU_LOW_HEIGHT),
                minimum(start_height - height, UCHIMIZU_MIN_RAISE),
                maximum(now - start_time, UCHIMIZU_RAISE_WINDOW_SECONDS),
                float(within_torso),
                float(away_from_face),
            )
            self.state = Phase.READY
            self.setup_started_at = now
            self.ready_at = now
            self.peak = height
            self.history.clear()
        else:
            self.history.append((now, height))
        return False


class AnchoredUchimizuAnalyzer(UchimizuAnalyzer):
    """Also require wrist rise/drop in image coordinates at a fixed torso scale."""

    def reset(self) -> None:
        super().reset()
        self.low_positions: deque[tuple[float, float, float]] = deque()
        self.anchor_scale: float | None = None
        self.absolute_peak = 0.0
        self.peak_time = 0.0

    def update(self, landmarks: Landmarks, now: float) -> bool:
        if len(landmarks) < 25:
            self.reset()
            return False
        needed = [landmarks[i] for i in (NOSE, *TORSO, self.wrist_index)]
        if any(
            getattr(p, "visibility", 1.0) <= 0.5 or not math.isfinite(p.x) or not math.isfinite(p.y)
            for p in needed
        ):
            self.reset()
            return False
        shoulder_y = shoulder_center_y(landmarks)
        scale = hip_center_y(landmarks) - shoulder_y
        if scale <= 1e-6:
            self.reset()
            return False
        if self.last_time is not None and not 0 < now - self.last_time <= UCHIMIZU_MAX_FRAME_GAP:
            self.reset()
        wrist = landmarks[self.wrist_index]
        height = (wrist.y - shoulder_y) / scale
        margin = shoulder_width(landmarks) * UCHIMIZU_X_MARGIN
        torso_left, torso_right = torso_x_range(landmarks)
        central = torso_left - margin <= wrist.x <= torso_right + margin
        away = (
            normalized_wrist_distances(landmarks, self.wrist_index)[0]
            >= READY_FACE_EXCLUSION_DISTANCE
        )
        while self.low_positions and now - self.low_positions[0][0] > UCHIMIZU_RAISE_WINDOW_SECONDS:
            self.low_positions.popleft()
        before, previous_completed = self.state, self.completed_at
        history_before = list(self.history)
        if before == Phase.READY and wrist.y < self.absolute_peak:
            self.absolute_peak, self.peak_time = wrist.y, now
        detected = super().update(landmarks, now)
        if self.state == Phase.READY and before != Phase.READY:
            candidates = [
                (t, y, s)
                for t, y, s in self.low_positions
                if (y - wrist.y) / s >= UCHIMIZU_MIN_RAISE
                and now - t >= MULTICAM_SCOOP_MIN_MOTION_SECONDS
            ]
            if not candidates:
                self.state = Phase.IDLE
                self.setup_started_at = None
                self.history.extend(history_before)
                return False
            _, _, self.anchor_scale = max(candidates, key=lambda v: (v[1] - wrist.y) / v[2])
            self.absolute_peak, self.peak_time = wrist.y, now
        if detected and self.completed_at != previous_completed:
            if (
                self.anchor_scale is None
                or (wrist.y - self.absolute_peak) / self.anchor_scale < UCHIMIZU_MIN_DROP
                or now - self.peak_time < MULTICAM_SCOOP_MIN_MOTION_SECONDS
            ):
                self.reset()
                return False
        if self.state == Phase.IDLE and self.completed_at is None:
            if central and away:
                if height >= UCHIMIZU_LOW_HEIGHT:
                    self.low_positions.append((now, wrist.y, scale))
            else:
                self.low_positions.clear()
        return detected
