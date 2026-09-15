import multiprocessing as mp
import time
from pathlib import Path
from typing import Any, NotRequired, TypedDict

import cv2
import numpy.typing as npt

from .config import (
    CAMERA_BACKEND,
    CAMERA_FOURCC,
    CAMERA_INDEX,
    FPS,
    POSE_CONNECTIONS,
    VIDEO_OUTPUT_BUFFER_FRAMES,
    VIDEO_OUTPUT_PATH,
    VIDEO_SOURCE,
    WINDOW_TITLE,
)
from .ipc import SharedLatestFrame, get_latest
from .pose_worker import pose_worker
from .rendering import draw_landmarks, draw_messages, draw_ramune_guide
from .video_output import AsyncVideoWriter

type Landmark = tuple[float, float, float]
type PixelPoint = tuple[int, int]
type Frame = npt.NDArray[Any]


class PoseResult(TypedDict):
    landmarks: list[Landmark]
    messages: list[tuple[str, PixelPoint, tuple[int, int, int], float]]
    selected_action: str
    relaxing_state: bool

    ramune_state: NotRequired[str]


class GestureApplication:
    def __init__(self, camera_index: int = CAMERA_INDEX) -> None:
        self.camera_index = camera_index
        self.pose_frame_queue: SharedLatestFrame | None = None
        self.pose_result_queue = mp.Queue(maxsize=1)
        self.pose_process = None

    def run(self) -> None:
        capture = self._open_capture()
        output: AsyncVideoWriter | None = None

        latest_pose: PoseResult = {
            "landmarks": [],
            "messages": [],
            "selected_action": "NONE",
            "relaxing_state": False,
        }
        previous_time = time.monotonic()
        try:
            success, frame = capture.read()
            if not success:
                return
            self.pose_frame_queue = SharedLatestFrame(frame.shape)
            self._start_workers()
            assert self.pose_process is not None
            writer = self._open_output(capture)
            if writer is not None:
                try:
                    output = AsyncVideoWriter(writer, VIDEO_OUTPUT_BUFFER_FRAMES)
                except Exception:
                    writer.release()
                    raise
            while success:
                if not self.pose_process.is_alive():
                    raise RuntimeError("Pose worker process has exited unexpectedly")
                self.pose_frame_queue.publish(frame)
                latest_pose = get_latest(self.pose_result_queue, latest_pose)
                annotated = self._annotate_frame(frame, latest_pose)
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
                if output is not None:
                    output.write(annotated)
                cv2.imshow(WINDOW_TITLE, annotated)
                if cv2.waitKey(1) & 0xFF == 27:
                    break
                success, frame = capture.read()
        finally:
            capture.release()
            cv2.destroyAllWindows()
            try:
                self._stop_workers()
            finally:
                if output is not None:
                    output.release()

    def _open_capture(self) -> cv2.VideoCapture:
        if VIDEO_SOURCE is not None:
            capture = cv2.VideoCapture(str(VIDEO_SOURCE))
            if capture.isOpened():
                return capture
            capture.release()
            raise RuntimeError(f"Unable to open video file {VIDEO_SOURCE}")

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

    @staticmethod
    def _open_output(capture: cv2.VideoCapture) -> cv2.VideoWriter | None:
        if VIDEO_SOURCE is None:
            return None

        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = capture.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = FPS
        Path(VIDEO_OUTPUT_PATH).parent.mkdir(parents=True, exist_ok=True)
        output = cv2.VideoWriter(
            str(VIDEO_OUTPUT_PATH),
            cv2.VideoWriter.fourcc(*"mp4v"),
            fps,
            (width, height),
        )
        if output.isOpened():
            return output
        output.release()
        raise RuntimeError(f"Unable to open output video file {VIDEO_OUTPUT_PATH}")

    def _start_workers(self) -> None:
        self.pose_process = mp.Process(
            target=pose_worker,
            args=(self.pose_frame_queue, self.pose_result_queue),
            name="pose-worker",
        )
        self.pose_process.start()

    def _stop_workers(self) -> None:
        for channel in (self.pose_frame_queue,):
            if channel is not None:
                channel.close()
        for process in (self.pose_process,):
            if process is None or process.pid is None:
                continue
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()
                process.join()
        for channel in (self.pose_result_queue,):
            channel.close()
            channel.cancel_join_thread()

    @staticmethod
    def _annotate_frame(frame: Frame, pose_result: PoseResult) -> Frame:
        image = frame.copy()
        draw_landmarks(image, pose_result.get("landmarks", []), POSE_CONNECTIONS)
        draw_messages(image, pose_result.get("messages", []))
        draw_ramune_guide(image, pose_result.get("ramune_state", "IDLE"))
        GestureApplication._draw_action(image, GestureApplication._primary_action(pose_result))
        return image

    @staticmethod
    def _primary_action(pose_result: PoseResult) -> str:
        selected = pose_result.get("selected_action", "NONE")
        return {"RAMUNE": "RAMUNE", "UCHIMIZU": "SPRINKLING", "FANNING": "FANNING"}.get(
            selected, "RELAXING" if pose_result.get("relaxing_state") else "NONE"
        )

    @staticmethod
    def _draw_action(image: Frame, action: str) -> None:
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
