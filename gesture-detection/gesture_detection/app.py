import multiprocessing as mp
import time
from typing import Any, TypedDict

import cv2
import numpy as np
import numpy.typing as npt

from .config import (
    CAMERA_BACKEND,
    CAMERA_FOURCC,
    POSE_CONNECTIONS,
    WINDOW_TITLE,
    YOLO_EMA_ALPHA,
    YOLO_TTL_SECONDS,
)
from .ipc import get_latest, put_latest
from .pose_worker import pose_worker
from .rendering import draw_landmarks, draw_messages, right_wrist_pixel
from .yolo_worker import yolo_worker


type Landmark = tuple[float, float, float]
type PixelPoint = tuple[int, int]
type PixelBox = tuple[int, int, int, int]
type ScoredPixelBox = tuple[int, int, int, int, float]


class PoseResult(TypedDict):
    landmarks: list[Landmark]
    messages: list[tuple[str, PixelPoint, tuple[int, int, int], float]]
    selected_action: str
    relaxing_state: bool


class BottleResult(TypedDict):
    boxes: list[ScoredPixelBox]


class BottleState(TypedDict):
    box: npt.NDArray[np.float32] | None
    confidence: float
    last_seen: float


class GestureApplication:
    def __init__(self, camera_index: int = 0) -> None:
        self.camera_index = camera_index
        self.pose_frame_queue = mp.Queue(maxsize=1)
        self.pose_result_queue = mp.Queue(maxsize=1)
        self.yolo_frame_queue = mp.Queue(maxsize=1)
        self.yolo_result_queue = mp.Queue(maxsize=1)
        self.pose_process = None
        self.yolo_process = None

    def run(self) -> None:
        capture = self._open_capture()

        latest_pose: PoseResult = {
            "landmarks": [],
            "messages": [],
            "selected_action": "NONE",
            "relaxing_state": False,
        }
        bottle_state: BottleState = {"box": None, "confidence": 0.0, "last_seen": 0.0}
        previous_time = time.monotonic()
        self._start_workers()
        assert self.pose_process is not None
        assert self.yolo_process is not None
        try:
            while capture.isOpened():
                success, frame = capture.read()
                if not success:
                    break
                if not self.pose_process.is_alive():
                    raise RuntimeError("Pose worker process has exited unexpectedly")
                if not self.yolo_process.is_alive():
                    raise RuntimeError("YOLO worker process has exited unexpectedly")
                put_latest(self.pose_frame_queue, frame.copy())
                put_latest(self.yolo_frame_queue, frame.copy())
                latest_pose = get_latest(self.pose_result_queue, latest_pose)
                bottle_result: BottleResult | None = get_latest(self.yolo_result_queue, None)
                if bottle_result is not None:
                    self._update_bottle_state(bottle_state, bottle_result)

                annotated = self._annotate_frame(frame, latest_pose, bottle_state)
                current_time = time.monotonic()
                frame_rate = 1.0 / max(current_time - previous_time, 1e-6)
                previous_time = current_time
                cv2.putText(
                    annotated,
                    f"Main FPS: {frame_rate:.1f}",
                    (450, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (200, 200, 200),
                    2,
                )
                cv2.imshow(WINDOW_TITLE, annotated)
                if cv2.waitKey(1) & 0xFF == 27:
                    break
        finally:
            capture.release()
            cv2.destroyAllWindows()
            self._stop_workers()

    def _open_capture(self) -> cv2.VideoCapture:
        capture = cv2.VideoCapture(self.camera_index, CAMERA_BACKEND)
        fourcc = cv2.VideoWriter.fourcc(*CAMERA_FOURCC)
        if capture.isOpened() and capture.set(cv2.CAP_PROP_FOURCC, fourcc):
            return capture
        capture.release()

        capture = cv2.VideoCapture(self.camera_index)
        if capture.isOpened():
            return capture
        capture.release()
        raise RuntimeError(
            f"Unable to open camera {self.camera_index} with either the configured "
            "or default settings"
        )

    def _start_workers(self) -> None:
        self.pose_process = mp.Process(
            target=pose_worker,
            args=(self.pose_frame_queue, self.pose_result_queue),
            name="pose-worker",
        )
        self.yolo_process = mp.Process(
            target=yolo_worker,
            args=(self.yolo_frame_queue, self.yolo_result_queue),
            name="yolo-worker",
        )
        self.pose_process.start()
        self.yolo_process.start()

    def _stop_workers(self) -> None:
        put_latest(self.pose_frame_queue, None)
        put_latest(self.yolo_frame_queue, None)
        for process in (self.pose_process, self.yolo_process):
            if process is None:
                continue
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()
                process.join()

    @staticmethod
    def _update_bottle_state(state: BottleState, result: BottleResult) -> None:
        boxes = result.get("boxes", [])
        if not boxes:
            return
        best_box = max(boxes, key=lambda box: box[4])
        current_box = np.asarray(best_box[:4], dtype=np.float32)
        now = time.monotonic()
        if state["box"] is None or now - state["last_seen"] > YOLO_TTL_SECONDS:
            state["box"] = current_box
        else:
            state["box"] = YOLO_EMA_ALPHA * current_box + (1 - YOLO_EMA_ALPHA) * state["box"]
        state["confidence"] = best_box[4]
        state["last_seen"] = now

    @staticmethod
    def _annotate_frame(
        frame: npt.NDArray[np.uint8],
        pose_result: PoseResult,
        bottle_state: BottleState,
    ) -> npt.NDArray[np.uint8]:
        image = frame.copy()
        height, width, _ = image.shape
        landmarks = pose_result.get("landmarks", [])
        wrist = right_wrist_pixel(landmarks, width, height)
        bottle_box = GestureApplication._active_bottle_box(bottle_state)
        action = GestureApplication._primary_action(pose_result, bottle_box, wrist)
        draw_landmarks(image, landmarks, POSE_CONNECTIONS)
        draw_messages(image, pose_result.get("messages", []))
        GestureApplication._draw_bottle(image, bottle_box, bottle_state, wrist)
        GestureApplication._draw_action(image, action)
        return image

    @staticmethod
    def _active_bottle_box(state: BottleState) -> PixelBox | None:
        if state["box"] is None or time.monotonic() - state["last_seen"] >= YOLO_TTL_SECONDS:
            return None
        return tuple(map(int, state["box"]))

    @staticmethod
    def _primary_action(
        pose_result: PoseResult,
        bottle_box: PixelBox | None,
        wrist: PixelPoint | None,
    ) -> str:
        if bottle_box and wrist and GestureApplication._contains(bottle_box, wrist):
            return "RAMUNE"
        selected = pose_result.get("selected_action", "NONE")
        return {"UCHIMIZU": "SPRINKLING", "FANNING": "FANNING"}.get(
            selected, "RELAXING" if pose_result.get("relaxing_state") else "NONE"
        )

    @staticmethod
    def _contains(box: PixelBox, point: PixelPoint) -> bool:
        x1, y1, x2, y2 = box
        x, y = point
        return x1 <= x <= x2 and y1 <= y <= y2

    @staticmethod
    def _draw_bottle(
        image: npt.NDArray[np.uint8],
        box: PixelBox | None,
        state: BottleState,
        wrist: PixelPoint | None,
    ) -> None:
        if box is None:
            return
        highlighted = wrist and GestureApplication._contains(box, wrist)
        color = (0, 255, 255) if highlighted else (0, 165, 255)
        x1, y1, x2, y2 = box
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 5 if highlighted else 2)
        cv2.putText(
            image,
            f"Ramune Bottle: {state['confidence']:.2f}",
            (x1, y1 - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2,
        )

    @staticmethod
    def _draw_action(image: npt.NDArray[np.uint8], action: str) -> None:
        labels = {
            "FANNING": ("Action: Fanning!", (0, 165, 255)),
            "SPRINKLING": ("Action: Sprinkling Water!", (255, 100, 100)),
            "RAMUNE": ("Action: Opening Ramune!", (0, 255, 255)),
            "RELAXING": ("Action: Relaxing...", (0, 255, 255)),
        }
        if action not in labels:
            return
        text, color = labels[action]
        cv2.putText(image, text, (10, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3)


def main() -> None:
    GestureApplication().run()
