import math
import multiprocessing as mp
import queue
import time
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Event
from pathlib import Path
from typing import Any

import cv2
import numpy.typing as npt

from .config import (
    CAMERA_BACKEND,
    CAMERA_FOURCC,
    CAMERA_ROTATION,
    FPS,
    MULTICAM_ENABLED,
    POSE_CONNECTIONS,
    RECORD_LIVE_VIDEO,
    VIDEO_OUTPUT_BUFFER_FRAMES,
    VIDEO_OUTPUT_PATH,
    VIDEO_SOURCE,
    WINDOW_TITLE,
)
from .frame_rotation import rotate_frame
from .gesture_types import Gesture, Phase
from .ipc import SharedLatestFrame, get_latest
from .pose_worker import pose_worker
from .recognition_types import GestureSample, PoseResult
from .rendering import (
    draw_bow_meter,
    draw_landmarks,
    draw_messages,
    draw_ramune_guide,
    draw_subject_area,
    status_messages,
)
from .video_output import AsyncVideoWriter

type Frame = npt.NDArray[Any]


class FrameClock:
    """Timestamp decoded frames in source seconds, or camera capture time."""

    def __init__(self, is_video: bool) -> None:
        self.is_video = is_video
        self.previous: float | None = None

    def timestamp(self, capture: cv2.VideoCapture) -> float:
        if not self.is_video:
            return time.monotonic()
        timestamp = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        if (
            not math.isfinite(timestamp)
            or timestamp < 0
            or (self.previous is not None and timestamp <= self.previous)
        ):
            fps = capture.get(cv2.CAP_PROP_FPS)
            if not math.isfinite(fps) or fps <= 0:
                fps = FPS
            timestamp = 0.0 if self.previous is None else self.previous + 1.0 / fps
        self.previous = timestamp
        return timestamp


class GestureApplication:
    def __init__(
        self,
        camera_index: int | None = None,
        samples: Queue[GestureSample] | None = None,
        stop: Event | None = None,
    ) -> None:
        self.camera_index = 0 if camera_index is None else camera_index
        self.samples = samples
        self.stop = stop
        self.pose_frame_queue: SharedLatestFrame | None = None
        self.pose_result_queue = mp.Queue(maxsize=1)
        self.pose_process = None
        self._window_created = False
        self.source_fps = float(FPS)

    def run(self) -> None:
        capture = self._open_capture()
        output: AsyncVideoWriter | None = None

        latest_pose: PoseResult = {
            "landmarks": [],
            "selected_action": Gesture.NONE,
            "relaxing_state": False,
        }
        previous_time = time.monotonic()
        frame_clock = FrameClock(is_video=VIDEO_SOURCE is not None)
        try:
            success, frame = capture.read()
            if not success:
                return
            frame = rotate_frame(frame, CAMERA_ROTATION)
            timestamp = frame_clock.timestamp(capture)
            frame_id = 0
            self.pose_frame_queue = SharedLatestFrame(frame.shape)
            source_fps = capture.get(cv2.CAP_PROP_FPS)
            if (
                isinstance(source_fps, (int, float))
                and math.isfinite(source_fps)
                and source_fps > 0
            ):
                self.source_fps = float(source_fps)
            self._start_workers()
            assert self.pose_process is not None
            writer = self._open_output(capture, frame)
            if writer is not None:
                try:
                    output = AsyncVideoWriter(writer, VIDEO_OUTPUT_BUFFER_FRAMES)
                except Exception:
                    writer.release()
                    raise
            while success:
                if not self.pose_process.is_alive():
                    raise RuntimeError("Pose worker process has exited unexpectedly")
                if frame_clock.is_video:
                    result = self._process_video_frame(frame, timestamp, frame_id)
                    if result is None:
                        break
                    latest_pose = result
                else:
                    self.pose_frame_queue.publish(frame, timestamp, frame_id)
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
                self._window_created = True
                if self._exit_requested():
                    break
                success, frame = capture.read()
                if success:
                    frame = rotate_frame(frame, CAMERA_ROTATION)
                    frame_id += 1
                    timestamp = frame_clock.timestamp(capture)
        finally:
            capture.release()
            cv2.destroyAllWindows()
            try:
                self._stop_workers()
            finally:
                if output is not None:
                    output.release()

    def _process_video_frame(
        self, frame: Frame, timestamp: float, frame_id: int
    ) -> PoseResult | None:
        """Keep exactly one frame in flight; its result precedes the next read."""
        assert self.pose_frame_queue is not None
        assert self.pose_process is not None
        published = False
        while True:
            if not self.pose_process.is_alive():
                raise RuntimeError("Pose worker process has exited unexpectedly")
            if not published:
                published = self.pose_frame_queue.publish(frame, timestamp, frame_id)
            if published:
                try:
                    result = self.pose_result_queue.get(timeout=0.05)
                    if result["frame_id"] != frame_id or result["timestamp"] != timestamp:
                        raise RuntimeError("Pose result does not match the pending video frame")
                    return result
                except queue.Empty:
                    pass
            else:
                # A reader briefly holding the mailbox lock must not drop a frame.
                time.sleep(0.001)
            if self._exit_requested():
                return None

    def _exit_requested(self) -> bool:
        """Return true for Escape, a stop request, or a closed HighGUI window."""
        if self.stop is not None and self.stop.is_set():
            return True
        if cv2.waitKey(1) & 0xFF == 27:
            return True
        if not self._window_created:
            return False
        try:
            return cv2.getWindowProperty(WINDOW_TITLE, cv2.WND_PROP_VISIBLE) < 1
        except cv2.error:
            # Some HighGUI backends remove the native window before reporting
            # its visibility. Treat the missing-window error as a close event.
            return True

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
    def _open_output(
        capture: cv2.VideoCapture, frame: Frame | None = None
    ) -> cv2.VideoWriter | None:
        if VIDEO_SOURCE is None and not RECORD_LIVE_VIDEO:
            return None

        width = frame.shape[1] if frame is not None else int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = (
            frame.shape[0] if frame is not None else int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        )
        fps = capture.get(cv2.CAP_PROP_FPS)
        if not math.isfinite(fps) or fps <= 0:
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
            args=(
                self.pose_frame_queue,
                self.pose_result_queue,
                # Video timestamps are source time, not host monotonic time.
                self.samples if VIDEO_SOURCE is None else None,
                self.source_fps,
            ),
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
        draw_landmarks(
            image,
            pose_result.get("display_landmarks", pose_result.get("landmarks", [])),
            POSE_CONNECTIONS,
        )
        if "subject_state" in pose_result:
            draw_subject_area(image, pose_result["subject_state"])
        draw_messages(image, status_messages(pose_result))
        draw_ramune_guide(image, pose_result.get("ramune_state", Phase.IDLE))
        GestureApplication._draw_action(image, GestureApplication._primary_action(pose_result))
        draw_bow_meter(image, pose_result)
        return image

    @staticmethod
    def _primary_action(pose_result: PoseResult) -> str:
        current = pose_result.get("current")
        if current is not None:
            gesture = current["gesture"]
            return "SPRINKLING" if gesture == Gesture.UCHIMIZU else gesture
        selected = pose_result.get("selected_action", Gesture.NONE)
        actions: dict[str, str] = {
            Gesture.RAMUNE: Gesture.RAMUNE,
            Gesture.UCHIMIZU: "SPRINKLING",
            Gesture.FANNING: Gesture.FANNING,
        }
        return actions.get(
            selected, Gesture.RELAXING if pose_result.get("relaxing_state") else Gesture.NONE
        )

    @staticmethod
    def _draw_action(image: Frame, action: str) -> None:
        labels = {
            Gesture.FANNING: ("Action: Fanning!", (0, 165, 255)),
            "SPRINKLING": ("Action: Sprinkling Water!", (255, 100, 100)),
            Gesture.RAMUNE: ("Action: Opening Ramune!", (0, 255, 255)),
            Gesture.RELAXING: ("Action: Relaxing...", (0, 255, 255)),
            Gesture.BOW: ("Action: Bowing", (0, 255, 255)),
        }
        if action not in labels:
            return
        text, color = labels[action]
        cv2.putText(image, text, (10, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3)


def main(samples: Queue[GestureSample] | None = None, stop: Event | None = None) -> None:
    """Run recognition; when samples is given, send each live result to it."""
    from . import config

    indices = config.CAMERA_INDICES
    live = config.MULTICAM_VIDEO_SESSION is None if MULTICAM_ENABLED else VIDEO_SOURCE is None
    if live and indices is None:
        if MULTICAM_ENABLED and config.MULTICAM_HEADLESS:
            raise ValueError("Set camera.indices for headless live recognition")
        from .camera_selection import select_camera_indices

        indices = select_camera_indices(2 if MULTICAM_ENABLED else 1, stop)
        if indices is None:
            return
    if MULTICAM_ENABLED:
        from .multicam_app import MultiCameraApplication

        MultiCameraApplication(samples, stop, indices).run()
    else:
        GestureApplication(
            camera_index=indices[0] if indices else None, samples=samples, stop=stop
        ).run()


if __name__ == "__main__":
    main()
