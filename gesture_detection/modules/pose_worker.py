import math
import multiprocessing as mp
import queue
import urllib.request
from collections import deque
from typing import Any

import cv2
import mediapipe as mp_core
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

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
    POSE_MODEL_PATH,
    POSE_MODEL_URL,
    POSE_RUNNING_MODE,
    RELAXING_DWELL_SECONDS,
    SUPPRESS_MEDIAPIPE_STARTUP_LOGS,
    WINDOW_SECONDS,
)
from .gesture_position import (
    is_fanning_position,
    normalized_wrist_distances,
)
from .ipc import SharedLatestFrame
from .native_logging import suppress_native_stderr
from .ramune import RamuneAnalyzer
from .relaxing import RelaxingAnalyzer
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


class PoseAnalyzer:
    """Owns MediaPipe pose inference and all temporal gesture state."""

    def __init__(self, running_mode: str = POSE_RUNNING_MODE):
        if running_mode not in {"IMAGE", "VIDEO"}:
            raise ValueError("running_mode must be IMAGE or VIDEO")
        self.running_mode = running_mode
        self._last_source_timestamp: float | None = None
        self._last_video_timestamp_ms = -1
        with suppress_native_stderr(SUPPRESS_MEDIAPIPE_STARTUP_LOGS):
            self.landmarker = self._create_landmarker(running_mode)
        self.hands = [HandGestureAnalyzer(15), HandGestureAnalyzer(16)]
        self.ramune = RamuneAnalyzer()
        self.relaxing = RelaxingAnalyzer()

        self.relaxing_state = False
        self._reset_gesture_state()

    @staticmethod
    def _create_landmarker(running_mode: str):
        if not POSE_MODEL_PATH.exists():
            temp_path = POSE_MODEL_PATH.parent / f".{POSE_MODEL_PATH.name}.tmp"
            try:
                urllib.request.urlretrieve(POSE_MODEL_URL, temp_path)
                temp_path.rename(POSE_MODEL_PATH)
            except Exception:
                if temp_path.exists():
                    temp_path.unlink()
                raise

        options = vision.PoseLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(POSE_MODEL_PATH)),
            running_mode=vision.RunningMode[running_mode],
            output_segmentation_masks=False,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        return vision.PoseLandmarker.create_from_options(options)

    def close(self):
        self.landmarker.close()

    def process(self, frame, timestamp: float, frame_id: int):
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp_core.Image(
            image_format=mp_core.ImageFormat.SRGB,
            data=rgb_frame,
        )
        with suppress_native_stderr(SUPPRESS_MEDIAPIPE_STARTUP_LOGS):
            if self.running_mode == "VIDEO":
                timestamp_ms = self._video_timestamp_ms(timestamp)
                detection_result = self.landmarker.detect_for_video(mp_image, timestamp_ms)
            else:
                detection_result = self.landmarker.detect(mp_image)
        result: dict[str, Any] = {
            "landmarks": [],
            "messages": [],
            "frame_id": frame_id,
            "timestamp": timestamp,
        }

        if detection_result.pose_landmarks:
            landmarks = detection_result.pose_landmarks[0]
            result["landmarks"] = [
                (landmark.x, landmark.y, landmark.visibility) for landmark in landmarks
            ]
            self._update_gesture_scores(landmarks, timestamp)
            self.relaxing_state = self.relaxing.update(
                landmarks, timestamp, aspect_ratio=frame.shape[1] / frame.shape[0]
            )
        else:
            self._reset_tracking_state()

        result["ramune_state"] = self.ramune.state
        result["selected_action"] = self.selected_action
        result["relaxing_state"] = self.relaxing_state
        result["fanning_score"] = self.fanning_score
        result["uchimizu_score"] = self.uchimizu_score
        result["uchimizu_state"] = self.uchimizu_state
        self._append_status_messages(result)
        return result

    def _video_timestamp_ms(self, timestamp: float) -> int:
        """Adapt source seconds without changing gesture or result timestamps."""
        if not math.isfinite(timestamp) or timestamp < 0:
            raise ValueError("VIDEO timestamps must be finite and non-negative")
        if self._last_source_timestamp is not None and timestamp <= self._last_source_timestamp:
            raise ValueError("VIDEO source timestamps must strictly increase")
        # Distinct source times can truncate to the same integer millisecond.
        timestamp_ms = max(int(timestamp * 1000), self._last_video_timestamp_ms + 1)
        self._last_source_timestamp = timestamp
        self._last_video_timestamp_ms = timestamp_ms
        return timestamp_ms

    def _reset_gesture_state(self):
        self.ramune.reset()
        for hand in self.hands:
            hand._reset_gesture_state()
        self.selected_action = "NONE"
        self.uchimizu_state = "IDLE"
        self.uchimizu_score = 0.0
        self.fanning_score = 0.0

    def _update_gesture_scores(self, landmarks, timestamp: float) -> None:
        opened = self.ramune.update(landmarks, timestamp)
        if opened or self.ramune.state in ("FORMING", "READY"):
            # Keep the press from leaking into the single-hand classifiers.
            for hand in self.hands:
                hand._reset_gesture_state()
            self.selected_action = "RAMUNE" if opened else "NONE"
            self.fanning_score = self.uchimizu_score = 0.0
            self.uchimizu_state = "IDLE"
            return
        for hand in self.hands:
            if landmarks[hand.wrist_index].visibility > 0.5:
                hand._update_gesture_scores(landmarks, timestamp)
            else:
                hand._reset_gesture_state()
        # Preserve the existing priority when hands perform different gestures.
        priority = {"NONE": 0, "FANNING": 1, "UCHIMIZU": 2}
        selected = max(self.hands, key=lambda hand: priority[hand.selected_action])
        self.selected_action = selected.selected_action
        # The other hand can also produce a transient fanning score while one
        # hand prepares/releases water. Apply the same priority at pose level.
        preparing_or_recovering = any(
            hand.uchimizu_state == "READY" or timestamp < hand.fanning_suppressed_until
            for hand in self.hands
        )
        confirmed_fanning = any(
            hand.selected_action == "FANNING" and hand._has_repeated_fanning()
            for hand in self.hands
        )
        if self.selected_action == "FANNING" and preparing_or_recovering and not confirmed_fanning:
            self.selected_action = "NONE"
        self.fanning_score = max(hand.fanning_score for hand in self.hands)
        self.uchimizu_score = max(hand.uchimizu_score for hand in self.hands)
        self.uchimizu_state = max(
            self.hands,
            key=lambda hand: {"IDLE": 0, "READY": 1, "SWING": 2}[hand.uchimizu_state],
        ).uchimizu_state

    def _reset_tracking_state(self):
        self._reset_gesture_state()
        self.relaxing.reset()
        self.relaxing_state = False

    def _append_status_messages(self, result):
        if self.relaxing.motion_speed is not None:
            result["messages"].append(
                (f"Body speed: {self.relaxing.motion_speed:.3f}/s", (10, 55), (255, 200, 0), 0.7)
            )
        result["messages"].extend(
            [
                (
                    f"Fanning score: {self.fanning_score:.3f}",
                    (10, 80),
                    (0, 165, 255),
                    0.65,
                ),
                (
                    f"Uchimizu score: {self.uchimizu_score:.3f}",
                    (10, 105),
                    (255, 100, 100),
                    0.65,
                ),
                (
                    f"Uchimizu state: {self.uchimizu_state}",
                    (10, 130),
                    (255, 100, 100),
                    0.65,
                ),
            ]
        )
        result["messages"].append(
            (
                (
                    "Relaxing: ON"
                    if self.relaxing_state
                    else f"Relaxing: OFF (still {self.relaxing.still_seconds:.1f}/{RELAXING_DWELL_SECONDS:.1f}s)"
                ),
                (10, 155),
                (255, 255, 180),
                0.65,
            )
        )


def pose_worker(frame_queue: SharedLatestFrame, result_queue: mp.Queue) -> None:
    analyzer = PoseAnalyzer()
    try:
        while True:
            sample = frame_queue.get()
            if sample is None:
                break
            frame, timestamp, frame_id = sample
            result = analyzer.process(frame, timestamp, frame_id)
            while not result_queue.empty():
                try:
                    result_queue.get_nowait()
                except queue.Empty:
                    break
            result_queue.put(result)
    finally:
        analyzer.close()
