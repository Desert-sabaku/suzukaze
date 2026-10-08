"""Independent live capture and deterministic paired-recording input."""

import json
import math
import multiprocessing as mp
import queue
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import numpy.typing as npt

from . import config
from .frame_rotation import rotate_frame
from .ipc import get_latest, put_latest
from .pose_worker import PoseAnalyzer
from .recognition_types import PoseResult

type Frame = npt.NDArray[np.uint8]
type Preview = tuple[Frame, PoseResult]


@dataclass(frozen=True)
class RecordedView:
    camera_index: int
    path: Path
    frames: int
    width: int
    height: int
    duration: float

    @property
    def fps(self) -> float:
        return self.frames / self.duration


def load_session(path: Path, camera_indices: tuple[int, ...]) -> tuple[RecordedView, RecordedView]:
    """Recorder frame counts supply a uniform-capture approximation, not true PTS."""
    data = json.loads(path.read_text(encoding="utf-8"))
    duration = float(data["duration_seconds"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Session duration must be positive and finite")
    if len(camera_indices) != 2 or len(set(camera_indices)) != 2:
        raise ValueError("A session requires two distinct camera IDs")
    cameras = data["cameras"]
    result = []
    for camera in camera_indices:
        matches = [c for c in cameras if c["camera_index"] == camera]
        if len(matches) != 1:
            raise ValueError(f"Session must contain exactly one camera {camera}")
        item = matches[0]
        if any(
            type(item[k]) is not int or item[k] <= 0 for k in ("frames_written", "width", "height")
        ):
            raise ValueError("Session frame counts and dimensions must be positive integers")
        source = (path.parent / item["file"]).resolve()
        if not source.is_relative_to(path.parent.resolve()) or not source.is_file():
            raise ValueError(f"Invalid session video: {source}")
        result.append(
            RecordedView(
                camera, source, item["frames_written"], item["width"], item["height"], duration
            )
        )
    return result[0], result[1]


class RecordedInput:
    def __init__(self, view: RecordedView, rotation: str = "none") -> None:
        self.view = view
        self.rotation = rotation
        self.capture = cv2.VideoCapture(str(view.path))
        self.index = 0
        try:
            if (
                not self.capture.isOpened()
                or self.capture.get(cv2.CAP_PROP_FRAME_COUNT) != view.frames
            ):
                raise ValueError(f"Unable to open matching session video: {view.path}")
        except BaseException:
            self.capture.release()
            raise

    def read(self) -> tuple[Frame, float, int] | None:
        ok, frame = self.capture.read()
        if self.index == self.view.frames:
            if ok:
                raise ValueError(f"Extra frames in {self.view.path}")
            return None
        if not ok:
            raise ValueError(f"Truncated video at frame {self.index}: {self.view.path}")
        if frame.shape[:2] != (self.view.height, self.view.width):
            raise ValueError(f"Video dimensions changed: {self.view.path}")
        if frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError(f"Expected a uint8 BGR video: {self.view.path}")
        index = self.index
        self.index += 1
        return (
            rotate_frame(np.asarray(frame, dtype=np.uint8), self.rotation),
            index / self.view.fps,
            index,
        )

    def close(self) -> None:
        self.capture.release()


def open_camera(index: int) -> cv2.VideoCapture:
    capture = cv2.VideoCapture(index, config.CAMERA_BACKEND)
    if not capture.isOpened() or not capture.set(
        cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*config.CAMERA_FOURCC)
    ):
        capture.release()
        capture = cv2.VideoCapture(index)
    if not capture.isOpened():
        capture.release()
        raise RuntimeError(f"Unable to open camera {index}")
    try:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, config.MULTICAM_WIDTH)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, config.MULTICAM_HEIGHT)
        capture.set(cv2.CAP_PROP_FPS, config.FPS)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        capture.release()
        raise
    return capture


def camera_worker(
    slot: int, index: int, select_subject: bool, results: Any, preview: Any, errors: Any, stop: Any
) -> None:
    """Each camera owns capture and inference. Only previews are lossy."""
    capture, analyzer = None, None
    try:
        capture = open_camera(index)
        fps = capture.get(cv2.CAP_PROP_FPS)
        if not math.isfinite(fps) or fps <= 0:
            fps = float(config.FPS)
        analyzer = PoseAnalyzer(
            running_mode="VIDEO",
            select_subject=select_subject,
            ramune_detector="rules",
            source_fps=fps,
            recognition_profile="multicam",
        )
        frame_id = 0
        while not stop.is_set():
            ok, frame = capture.read()
            timestamp = time.monotonic()
            if not ok:
                raise RuntimeError(f"Camera {index} stopped providing frames")
            frame = rotate_frame(frame, config.MULTICAM_ROTATION[slot])
            result = analyzer.process(frame, timestamp, frame_id)
            while not stop.is_set():
                try:
                    results.put((slot, result), timeout=0.05)
                    break
                except queue.Full:
                    pass
            if stop.is_set():
                break
            put_latest(preview, (frame, result))
            frame_id += 1
    except Exception as error:
        errors.put((index, f"{type(error).__name__}: {error}"))
    finally:
        if capture is not None:
            capture.release()
        if analyzer is not None:
            analyzer.close()
        # Preview feeder threads must not block child shutdown on unread images.
        preview.cancel_join_thread()
        results.cancel_join_thread()


class LiveInputs:
    """Spawned workers isolate a slow/blocking camera from the other camera and UI."""

    def __init__(self, indices: tuple[int, ...], select_subject: tuple[bool, bool]) -> None:
        if len(indices) != 2 or len(set(indices)) != 2:
            raise ValueError("Expected two distinct camera IDs")
        context = mp.get_context("spawn")
        self.results = context.Queue(maxsize=64)
        self.errors = context.Queue(maxsize=2)
        self.previews = [context.Queue(maxsize=1) for _ in indices]
        self.stop = context.Event()
        self.processes = [
            context.Process(
                target=camera_worker,
                name=f"pose-camera-{index}",
                args=(
                    slot,
                    index,
                    select_subject[slot],
                    self.results,
                    self.previews[slot],
                    self.errors,
                    self.stop,
                ),
            )
            for slot, index in enumerate(indices)
        ]

    def start(self) -> None:
        try:
            PoseAnalyzer.ensure_model()
            for process in self.processes:
                process.start()
        except BaseException:
            self.close()
            raise

    def poll(self) -> list[tuple[int, PoseResult]]:
        try:
            camera, message = self.errors.get_nowait()
        except queue.Empty:
            pass
        else:
            raise RuntimeError(f"Camera {camera}: {message}")
        for process in self.processes:
            if process.exitcode is not None:
                raise RuntimeError(f"{process.name} exited unexpectedly ({process.exitcode})")
        output = []
        for _ in range(64):
            try:
                output.append(self.results.get_nowait())
            except queue.Empty:
                break
        return output

    def latest_previews(self, previous: dict[int, Preview]) -> dict[int, Preview]:
        for slot, channel in enumerate(self.previews):
            result = get_latest(channel, None)
            if result is not None:
                previous[slot] = result
        return previous

    def close(self) -> None:
        self.stop.set()
        for process in self.processes:
            if process.pid is not None:
                process.join(timeout=2)
                if process.is_alive():
                    process.terminate()
                    process.join()
        for channel in [self.results, self.errors, *self.previews]:
            channel.close()
            channel.cancel_join_thread()
