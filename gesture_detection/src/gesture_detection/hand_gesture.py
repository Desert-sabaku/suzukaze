"""Per-hand temporal classification and fanning/uchimizu disambiguation."""

from collections import deque

import numpy as np

from .config import (
    BUFFER_SIZE,
    FANNING_EXIT_TORSO_HEIGHT,
    FANNING_FACE_DISTANCE,
    FANNING_MIN_REVERSALS,
    FANNING_POSITION_DWELL_SECONDS,
    FANNING_POSITION_GRACE_SECONDS,
    FANNING_REVERSAL_DISTANCE,
    FANNING_UCHIMIZU_GRACE_SECONDS,
    FPS,
    WINDOW_SECONDS,
)
from .gesture_position import is_fanning_position, normalized_wrist_distances
from .signal_processing import resample_time_window
from .uchimizu import UchimizuAnalyzer


class HandGestureAnalyzer:
    """Track one wrist without mixing motion or cooldowns with the other hand."""

    def __init__(self, wrist_index: int):
        self.wrist_index = wrist_index
        self.wrist_y_history = deque(maxlen=BUFFER_SIZE)
        self.wrist_t_history = deque(maxlen=BUFFER_SIZE)
        self.wrist_dy_history = deque(maxlen=max(3, int(FPS * 0.3)))
        self.relaxing_state = False
        self._reset_gesture_state()

    def _reset_gesture_state(self):
        self.wrist_y_history.clear()
        self.wrist_t_history.clear()
        self.wrist_dy_history.clear()
        self.uchimizu_state = "IDLE"
        self.uchimizu = UchimizuAnalyzer(self.wrist_index)
        self.uchimizu_score = 0.0
        self.fanning_score = 0.0
        self.fanning_suppressed_until = 0.0
        self.fanning_position_since: float | None = None
        self.fanning_position_last_seen: float | None = None
        self.fanning_height_history: deque[tuple[float, float]] = deque()
        self.selected_action = "NONE"
        self.action_hold_count = 0

    def _update_gesture_scores(self, landmarks, timestamp: float) -> None:
        wrist = landmarks[self.wrist_index]
        previous_y = self.wrist_y_history[-1] if self.wrist_y_history else None
        self.wrist_y_history.append(wrist.y)
        now = timestamp
        self.wrist_t_history.append(now)
        if previous_y is not None:
            self.wrist_dy_history.append(abs(wrist.y - previous_y))

        detected = self.uchimizu.update(landmarks, now)
        self.uchimizu_state = self.uchimizu.state
        self.uchimizu_score = 0.9 if detected else 0.0
        face_distance, _ = normalized_wrist_distances(landmarks, self.wrist_index)
        face_proximity = max(0.0, 1.0 - face_distance / FANNING_FACE_DISTANCE)
        raw_fanning_score = self._calculate_fanning_score()
        smoothing = 0.35 if raw_fanning_score > self.fanning_score else 0.55
        self.fanning_score += smoothing * (raw_fanning_score - self.fanning_score)
        self.fanning_score = min(1.0, self.fanning_score + face_proximity * 0.08)
        shoulder_y = (landmarks[11].y + landmarks[12].y) / 2
        torso_height = (landmarks[23].y + landmarks[24].y) / 2 - shoulder_y
        height = (wrist.y - shoulder_y) / torso_height if torso_height > 1e-6 else float("inf")
        if is_fanning_position(landmarks, self.wrist_index):
            if self.fanning_position_since is None:
                self.fanning_position_since = now
            self.fanning_position_last_seen = now
        elif (
            height > FANNING_EXIT_TORSO_HEIGHT
            or self.fanning_position_last_seen is None
            or now - self.fanning_position_last_seen > FANNING_POSITION_GRACE_SECONDS
        ):
            self.fanning_position_since = None
            self.fanning_position_last_seen = None
            self.fanning_height_history.clear()
        if self.fanning_position_since is not None:
            self.fanning_height_history.append((now, height))
        while (
            self.fanning_height_history and now - self.fanning_height_history[0][0] > WINDOW_SECONDS
        ):
            self.fanning_height_history.popleft()
        fanning_allowed = (
            self.fanning_position_since is not None
            and now - self.fanning_position_since >= FANNING_POSITION_DWELL_SECONDS
        )
        if not fanning_allowed:
            self.fanning_score = 0.0
        repeated_fanning = (
            fanning_allowed and self.fanning_score > 0.45 and self._has_repeated_fanning()
        )
        if repeated_fanning:
            self.fanning_suppressed_until = 0.0
            self.uchimizu.reset()
            self.uchimizu_state = "IDLE"
            self.uchimizu_score = 0.0
        elif self.uchimizu.completed_at is not None:
            self.fanning_suppressed_until = (
                self.uchimizu.completed_at + FANNING_UCHIMIZU_GRACE_SECONDS
            )
        self._select_action()
        # Reserve preparation and the post-release window for the scoop sequence.
        # Only confirmed repeated fanning may override it; a residual FFT score
        # must not do so, including through action hysteresis.
        fanning_blocked = (
            not fanning_allowed
            or self.uchimizu_state == "READY"
            or now < self.fanning_suppressed_until
        )
        if fanning_blocked and self.selected_action == "FANNING":
            self.selected_action = "NONE"

    def _has_repeated_fanning(self) -> bool:
        """Require several substantial reversals, not a single scoop/release."""
        if not self.fanning_height_history:
            return False
        extreme = self.fanning_height_history[0][1]
        direction = 0
        reversals = 0
        for _, height in self.fanning_height_history:
            delta = height - extreme
            if direction == 0:
                if abs(delta) >= FANNING_REVERSAL_DISTANCE:
                    direction = 1 if delta > 0 else -1
                    extreme = height
            elif delta * direction >= 0:
                extreme = height
            elif abs(delta) >= FANNING_REVERSAL_DISTANCE:
                reversals += 1
                direction *= -1
                extreme = height
        return reversals >= FANNING_MIN_REVERSALS

    def _calculate_fanning_score(self):
        if len(self.wrist_y_history) < 8:
            return 0.0

        history_signal = np.asarray(self.wrist_y_history, dtype=np.float32)
        history_timestamps = np.asarray(self.wrist_t_history, dtype=np.float64)
        signal, timestamps = resample_time_window(
            history_signal,
            history_timestamps,
            WINDOW_SECONDS,
        )
        if len(signal) < 8:
            return 0.0
        duration = timestamps[-1] - timestamps[0]
        if duration < 0.6:
            return 0.0

        signal = signal - np.mean(signal)
        sample_count = len(signal)
        x_axis = np.arange(sample_count, dtype=np.float32)
        slope, intercept = np.polyfit(x_axis, signal, 1)
        signal -= slope * x_axis + intercept

        dt = duration / max(sample_count - 1, 1)
        effective_fps = 1.0 / dt if dt > 1e-6 else float(FPS)
        window = np.hanning(sample_count).astype(np.float32)
        window_gain = np.sum(window) / sample_count
        spectrum = np.abs(np.fft.rfft(signal * window))
        spectrum = 2.0 / (sample_count * max(window_gain, 1e-6)) * spectrum
        frequencies = np.fft.rfftfreq(sample_count, d=1.0 / effective_fps)
        target = (frequencies >= 1.0) & (frequencies <= 3.0)
        band = (frequencies >= 0.5) & (frequencies <= 5.0)
        max_amplitude = float(np.max(spectrum[target])) if np.any(target) else 0.0
        target_energy = float(np.sum(spectrum[target] ** 2)) if np.any(target) else 0.0
        band_energy = float(np.sum(spectrum[band] ** 2)) if np.any(band) else 1e-9
        band_ratio = target_energy / max(band_energy, 1e-9)
        recent = history_timestamps >= history_timestamps[-1] - 0.3
        recent_y = history_signal[recent]
        recent_t = history_timestamps[recent]
        if len(recent_y) < 2 or recent_t[-1] - recent_t[0] <= 1e-6:
            return 0.0
        recent_speed = float(np.sum(np.abs(np.diff(recent_y))) / (recent_t[-1] - recent_t[0]))

        speed_excess = max(0.0, recent_speed - 0.02)
        amplitude_excess = max(0.0, max_amplitude - 0.004)
        frequency_excess = max(0.0, band_ratio - 0.15)
        speed_score = speed_excess / (speed_excess + 0.12)
        amplitude_score = amplitude_excess / (amplitude_excess + 0.012)
        frequency_score = frequency_excess / (frequency_excess + 0.35)
        activity_gate = min(1.0, recent_speed / 0.08)
        return activity_gate * (
            speed_score * 0.35 + amplitude_score * 0.35 + frequency_score * 0.30
        )

    def _select_action(self):
        if self.uchimizu_state == "SWING":
            candidate = "UCHIMIZU"
        elif (self.fanning_score > 0.55 and self.uchimizu_score < 0.5) or (
            self.fanning_score > 0.45 and self.uchimizu_score < 0.35
        ):
            candidate = "FANNING"
        elif self.fanning_score < 0.25 and self.uchimizu_score < 0.25:
            candidate = "NONE"
        else:
            candidate = self.selected_action

        if candidate == "NONE" and self.relaxing_state:
            candidate = "RELAXING"
        if candidate == "NONE":
            if self.selected_action == "FANNING" and self.fanning_score > 0.38:
                candidate = "FANNING"
            elif self.selected_action == "UCHIMIZU" and self.uchimizu_score > 0.42:
                candidate = "UCHIMIZU"

        if (
            candidate in ("FANNING", "UCHIMIZU")
            and self.selected_action in ("FANNING", "UCHIMIZU")
            and candidate != self.selected_action
            and abs(self.fanning_score - self.uchimizu_score) < 0.08
        ):
            candidate = self.selected_action
        self.selected_action = candidate
