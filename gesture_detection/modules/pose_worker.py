import math
import multiprocessing as mp
import queue
import urllib.request

import cv2
import mediapipe as mp_core
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from .config import (
    POSE_MODEL_PATH,
    POSE_MODEL_URL,
    POSE_RUNNING_MODE,
    SUPPRESS_MEDIAPIPE_STARTUP_LOGS,
)
from .ipc import SharedLatestFrame
from .native_logging import suppress_native_stderr
from .recognition import RecognitionCoordinator
from .recognition_types import PoseResult


class PoseAnalyzer:
    """Adapt MediaPipe inference to the independent recognition coordinator."""

    def __init__(
        self,
        running_mode: str = POSE_RUNNING_MODE,
        *,
        detection_confidence: float = 0.5,
        presence_confidence: float = 0.5,
        tracking_confidence: float = 0.5,
    ):
        if running_mode not in {"IMAGE", "VIDEO"}:
            raise ValueError("running_mode must be IMAGE or VIDEO")
        confidences = (detection_confidence, presence_confidence, tracking_confidence)
        if any(not 0.0 <= confidence <= 1.0 for confidence in confidences):
            raise ValueError("pose confidence thresholds must be between 0 and 1")
        self.running_mode = running_mode
        self._last_source_timestamp: float | None = None
        self._last_video_timestamp_ms = -1
        with suppress_native_stderr(SUPPRESS_MEDIAPIPE_STARTUP_LOGS):
            self.landmarker = self._create_landmarker(
                running_mode,
                detection_confidence,
                presence_confidence,
                tracking_confidence,
            )
        self.recognition = RecognitionCoordinator()

    @staticmethod
    def _create_landmarker(
        running_mode: str,
        detection_confidence: float = 0.5,
        presence_confidence: float = 0.5,
        tracking_confidence: float = 0.5,
    ):
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
            min_pose_detection_confidence=detection_confidence,
            min_pose_presence_confidence=presence_confidence,
            min_tracking_confidence=tracking_confidence,
        )
        return vision.PoseLandmarker.create_from_options(options)

    def close(self):
        self.landmarker.close()

    def process(self, frame, timestamp: float, frame_id: int) -> PoseResult:
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
        landmarks = detection_result.pose_landmarks[0] if detection_result.pose_landmarks else []
        return self.recognition.process(
            landmarks, timestamp, frame_id, aspect_ratio=frame.shape[1] / frame.shape[0]
        )

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
