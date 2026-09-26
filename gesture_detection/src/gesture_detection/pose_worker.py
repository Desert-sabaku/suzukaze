import math
import multiprocessing as mp
import queue
import time
import urllib.request

import cv2
import mediapipe as mp_core
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from .config import (
    FPS,
    GESTURE_DELIVERY_HOST,
    GESTURE_DELIVERY_PORT,
    GESTURE_EVENT_TTL,
    GESTURE_MAX_PENDING,
    GESTURE_RETRY_INTERVAL,
    GESTURE_STALE_TIMEOUT,
    GESTURE_STATE_INTERVAL,
    POSE_DISPLAY_SMOOTHING,
    POSE_MODEL_PATH,
    POSE_MODEL_URL,
    POSE_RUNNING_MODE,
    POSE_SELECT_SUBJECT,
    RAMUNE_DETECTOR,
    SUBJECT_AREA,
    SUPPRESS_MEDIAPIPE_STARTUP_LOGS,
)
from .gesture_delivery import DeliveryOutbox
from .gesture_server import GestureServer
from .ipc import SharedLatestFrame
from .landmark_smoothing import LandmarkSmoother
from .native_logging import suppress_native_stderr
from .recognition import RecognitionCoordinator
from .recognition_types import PoseResult
from .subject_selection import SubjectSelector


class PoseAnalyzer:
    """Adapt MediaPipe inference to the independent recognition coordinator."""

    def __init__(
        self,
        running_mode: str = POSE_RUNNING_MODE,
        *,
        detection_confidence: float = 0.5,
        presence_confidence: float = 0.5,
        tracking_confidence: float = 0.5,
        select_subject: bool = POSE_SELECT_SUBJECT,
        ramune_detector: str = RAMUNE_DETECTOR,
        source_fps: float = FPS,
    ):
        if running_mode not in {"IMAGE", "VIDEO"}:
            raise ValueError("running_mode must be IMAGE or VIDEO")
        confidences = (detection_confidence, presence_confidence, tracking_confidence)
        if any(not 0.0 <= confidence <= 1.0 for confidence in confidences):
            raise ValueError("pose confidence thresholds must be between 0 and 1")
        if ramune_detector == "learned" and running_mode != "VIDEO":
            raise ValueError("Learned Ramune requires POSE_RUNNING_MODE=VIDEO")
        self.recognition = RecognitionCoordinator(
            ramune_detector=ramune_detector, source_fps=source_fps
        )
        self.learned_profile = ramune_detector == "learned"
        self.subject_selector = (
            SubjectSelector()
            if select_subject and running_mode == "VIDEO" and not self.learned_profile
            else None
        )
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
        self.display_smoother = LandmarkSmoother()

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
        # Seed the single-person tracker centrally, then immediately restore the
        # complete frame. Seed frames never reach recognition or the overlay.
        seeded = self.subject_selector is not None and self.subject_selector.state in {
            "SEARCHING",
            "LOST",
        }
        inference_frame = frame
        if seeded or self.learned_profile:
            if self.learned_profile:
                assert self.recognition.learned_mask is not None
                left, right = self.recognition.learned_mask
            else:
                left, _, right, _ = SUBJECT_AREA
            width = frame.shape[1]
            inference_frame = np.full_like(frame, 127)
            start, end = round(left * width), round(right * width)
            inference_frame[:, start:end] = frame[:, start:end]
        rgb_frame = cv2.cvtColor(inference_frame, cv2.COLOR_BGR2RGB)
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
        if self.subject_selector is not None:
            landmarks = self.subject_selector.select(
                detection_result.pose_landmarks, timestamp, frame.shape[1] / frame.shape[0]
            )
        if seeded:
            landmarks = []
        result = self.recognition.process(
            landmarks, timestamp, frame_id, aspect_ratio=frame.shape[1] / frame.shape[0]
        )
        if self.subject_selector is not None:
            result["subject_state"] = (
                "ACQUIRING"
                if seeded and self.subject_selector.state == "TRACKING"
                else self.subject_selector.state
            )
        if POSE_DISPLAY_SMOOTHING and self.running_mode == "VIDEO":
            result["display_landmarks"] = self.display_smoother.update(
                result["landmarks"], timestamp
            )
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


def pose_worker(
    frame_queue: SharedLatestFrame,
    result_queue: mp.Queue,
    delivery_enabled: bool = False,
    source_fps: float = FPS,
) -> None:
    analyzer = PoseAnalyzer(source_fps=source_fps)
    outbox = (
        DeliveryOutbox(
            event_ttl=GESTURE_EVENT_TTL,
            stale_timeout=GESTURE_STALE_TIMEOUT,
            retry_interval=GESTURE_RETRY_INTERVAL,
            max_pending=GESTURE_MAX_PENDING,
        )
        if delivery_enabled
        else None
    )
    server = (
        GestureServer(
            outbox,
            host=GESTURE_DELIVERY_HOST,
            port=GESTURE_DELIVERY_PORT,
            state_interval=GESTURE_STATE_INTERVAL,
        )
        if outbox is not None
        else None
    )
    try:
        if server is not None:
            server.start()
        while True:
            sample = frame_queue.get()
            if sample is None:
                break
            frame, timestamp, frame_id = sample
            result = analyzer.process(frame, timestamp, frame_id)
            if outbox is not None:
                assert server is not None
                server.check()
                outbox.publish(result, observed_at=timestamp, now=time.monotonic())
            while not result_queue.empty():
                try:
                    result_queue.get_nowait()
                except queue.Empty:
                    break
            result_queue.put(result)
    finally:
        try:
            if server is not None:
                server.close()
        finally:
            analyzer.close()
