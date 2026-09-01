import multiprocessing as mp
import queue
import time
import urllib.request
from collections import deque

import cv2
import mediapipe as mp_core
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from .config import (
    BUFFER_SIZE,
    FPS,
    POSE_MODEL_PATH,
    POSE_MODEL_URL,
    TARGET_LANDMARKS,
)


class PoseAnalyzer:
    """Owns MediaPipe pose inference and all temporal gesture state."""

    def __init__(self):
        self.landmarker = self._create_landmarker()
        self.wrist_y_history = deque(maxlen=BUFFER_SIZE)
        self.wrist_t_history = deque(maxlen=BUFFER_SIZE)
        self.wrist_dy_history = deque(maxlen=max(3, int(FPS * 0.3)))
        self.motion_history = deque(maxlen=FPS)
        self.previous_landmarks = None

        self.relaxing_state = False
        self.relaxing_low_count = 0
        self.uchimizu_state = "IDLE"
        self.uchimizu_cooldown = 0
        self.uchimizu_ready_frames = 0
        self.selected_action = "NONE"
        self.action_hold_count = 0
        self.uchimizu_score = 0.0
        self.fanning_score = 0.0

    @staticmethod
    def _create_landmarker():
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
            output_segmentation_masks=False,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        return vision.PoseLandmarker.create_from_options(options)

    def close(self):
        self.landmarker.close()

    def process(self, frame):
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp_core.Image(
            image_format=mp_core.ImageFormat.SRGB,
            data=rgb_frame,
        )
        detection_result = self.landmarker.detect(mp_image)
        result = {"landmarks": [], "messages": []}

        if detection_result.pose_landmarks:
            landmarks = detection_result.pose_landmarks[0]
            result["landmarks"] = [
                (landmark.x, landmark.y, landmark.visibility) for landmark in landmarks
            ]
            self._update_motion(landmarks)
            if landmarks[16].visibility > 0.5:
                self._update_gesture_scores(landmarks)
            else:
                self._reset_gesture_state()
            self._update_relaxing_state()
        else:
            self._reset_tracking_state()

        result["selected_action"] = self.selected_action
        result["relaxing_state"] = self.relaxing_state
        result["fanning_score"] = self.fanning_score
        result["uchimizu_score"] = self.uchimizu_score
        result["uchimizu_state"] = self.uchimizu_state
        self._append_status_messages(result)
        return result

    def _update_motion(self, landmarks):
        current = np.array(
            [[landmarks[index].x, landmarks[index].y] for index in TARGET_LANDMARKS]
        )
        if self.previous_landmarks is not None:
            motion = np.linalg.norm(current - self.previous_landmarks, axis=1)
            self.motion_history.append(float(np.mean(motion)))
        self.previous_landmarks = current

    def _reset_gesture_state(self):
        self.wrist_y_history.clear()
        self.wrist_t_history.clear()
        self.wrist_dy_history.clear()
        self.uchimizu_state = "IDLE"
        self.uchimizu_cooldown = 0
        self.uchimizu_ready_frames = 0
        self.uchimizu_score = 0.0
        self.fanning_score = 0.0
        self.selected_action = "NONE"
        self.action_hold_count = 0

    def _reset_tracking_state(self):
        self._reset_gesture_state()
        self.wrist_y_history.clear()
        self.wrist_t_history.clear()
        self.wrist_dy_history.clear()
        self.motion_history.clear()
        self.previous_landmarks = None
        self.relaxing_state = False
        self.relaxing_low_count = 0

    def _update_gesture_scores(self, landmarks):
        wrist = landmarks[16]
        previous_y = self.wrist_y_history[-1] if self.wrist_y_history else None
        self.wrist_y_history.append(wrist.y)
        self.wrist_t_history.append(time.monotonic())
        if previous_y is not None:
            self.wrist_dy_history.append(abs(wrist.y - previous_y))

        self.uchimizu_score = 0.0
        raise_motion = drop_motion = recent_speed = 0.0
        face_proximity = 0.0
        if len(self.wrist_y_history) >= 5:
            recent_y = np.asarray(list(self.wrist_y_history)[-8:], dtype=np.float32)
            recent_t = np.asarray(list(self.wrist_t_history)[-8:], dtype=np.float64)
            raise_motion = max(0.0, float(np.max(recent_y) - recent_y[-1]))
            drop_motion = max(0.0, float(recent_y[-1] - np.min(recent_y)))
            intervals = np.diff(recent_t)
            valid_intervals = intervals[intervals > 0]
            average_dt = (
                float(np.mean(valid_intervals)) if len(valid_intervals) else 1.0 / FPS
            )
            recent_speed = float(
                np.mean(np.abs(np.diff(recent_y))) / max(average_dt, 1e-6)
            )
            wave_score = min(
                1.0,
                (raise_motion / 0.08) * 0.45
                + (drop_motion / 0.08) * 0.55
                + min(recent_speed / 0.02, 1.0) * 0.20,
            )
            self._advance_uchimizu_state(raise_motion, drop_motion, recent_speed)

            face_distance = float(
                np.linalg.norm(
                    np.array(
                        [wrist.x - landmarks[0].x, wrist.y - landmarks[0].y],
                        dtype=np.float32,
                    )
                )
            )
            face_proximity = max(0.0, 1.0 - face_distance / 0.35)
            if self.uchimizu_state == "READY":
                self.uchimizu_score = max(0.62, wave_score)
            elif self.uchimizu_state == "SWING":
                self.uchimizu_score = max(0.90, wave_score)
            if raise_motion <= 0.05 or drop_motion <= 0.07 or recent_speed <= 0.02:
                self.uchimizu_score *= 0.5
            self.uchimizu_score = min(1.0, self.uchimizu_score + face_proximity * 0.10)
        raw_fanning_score = self._calculate_fanning_score()
        smoothing = 0.35 if raw_fanning_score > self.fanning_score else 0.55
        self.fanning_score += smoothing * (raw_fanning_score - self.fanning_score)
        self.fanning_score = max(0.0, self.fanning_score - face_proximity * 0.04)
        self._select_action(raise_motion, drop_motion, recent_speed)

    def _advance_uchimizu_state(self, raise_motion, drop_motion, recent_speed):
        if self.uchimizu_cooldown > 0:
            self.uchimizu_cooldown -= 1
            if self.uchimizu_cooldown == 0:
                self.uchimizu_state = "IDLE"
                self.uchimizu_ready_frames = 0
            return
        if self.uchimizu_state == "IDLE":
            if raise_motion > 0.04 and recent_speed > 0.012:
                self.uchimizu_state = "READY"
                self.uchimizu_ready_frames = 1
        elif self.uchimizu_state == "READY":
            if drop_motion > 0.06 and recent_speed > 0.015:
                self.uchimizu_state = "SWING"
                self.uchimizu_cooldown = int(FPS * 1.5)
                self.uchimizu_ready_frames = 0
            else:
                self.uchimizu_ready_frames += 1
                if self.uchimizu_ready_frames > max(2, int(FPS * 0.2)):
                    self.uchimizu_state = "IDLE"
                    self.uchimizu_ready_frames = 0

    def _calculate_fanning_score(self):
        if len(self.wrist_y_history) < 8:
            return 0.0

        signal = np.asarray(self.wrist_y_history, dtype=np.float32)
        timestamps = np.asarray(self.wrist_t_history, dtype=np.float64)
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
        recent = timestamps >= timestamps[-1] - 0.3
        recent_y = np.asarray(self.wrist_y_history, dtype=np.float32)[recent]
        recent_t = timestamps[recent]
        if len(recent_y) < 2 or recent_t[-1] - recent_t[0] <= 1e-6:
            return 0.0
        recent_speed = float(
            np.sum(np.abs(np.diff(recent_y))) / (recent_t[-1] - recent_t[0])
        )

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

    def _select_action(self, raise_motion, drop_motion, recent_speed):
        if (self.uchimizu_state == "SWING" and self.uchimizu_score > 0.75) or (
            raise_motion > 0.05
            and drop_motion > 0.07
            and recent_speed > 0.02
            and self.uchimizu_state != "IDLE"
            and self.uchimizu_score > 0.6
        ):
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

    def _update_relaxing_state(self):
        if not self.motion_history:
            return
        average_motion = np.mean(self.motion_history)
        if not self.relaxing_state:
            if average_motion < 0.0200:
                self.relaxing_low_count += 1
            else:
                self.relaxing_low_count = 0
            if self.relaxing_low_count >= max(1, int(FPS * 0.4)):
                self.relaxing_state = True
        elif average_motion > 0.0240:
            self.relaxing_state = False
            self.relaxing_low_count = 0

    def _append_status_messages(self, result):
        if self.motion_history:
            average_motion = np.mean(self.motion_history)
            result["messages"].append(
                (f"Motion: {average_motion:.4f}", (10, 55), (255, 200, 0), 0.7)
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
        if not self.motion_history:
            return
        result["messages"].append(
            (
                "Relaxing: ON"
                if self.relaxing_state
                else f"Relaxing: OFF (warmup {max(0, int(FPS * 0.4) - self.relaxing_low_count)})",
                (10, 155),
                (255, 255, 180),
                0.65,
            )
        )


def pose_worker(frame_queue: mp.Queue, result_queue: mp.Queue):
    analyzer = PoseAnalyzer()
    try:
        while True:
            frame = frame_queue.get()
            if frame is None:
                break
            result = analyzer.process(frame)
            while not result_queue.empty():
                try:
                    result_queue.get_nowait()
                except queue.Empty:
                    break
            result_queue.put(result)
    finally:
        analyzer.close()
