"""Bounded, ordered video encoding off the display thread."""

import math
import queue
import threading
from pathlib import Path
from typing import Any

import cv2


def usable_fps(value: object, fallback: float) -> float:
    """Return a reported frame rate, or fallback when it is missing or invalid."""
    if (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    ):
        return float(value)
    return fallback


def open_video_writer(path: Path, fps: float, size: tuple[int, int]) -> cv2.VideoWriter:
    """Open an MP4 writer, creating its directory; raise if it cannot be opened."""
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter.fourcc(*"mp4v"), fps, size)
    if writer.isOpened():
        return writer
    writer.release()
    raise RuntimeError(f"Unable to open output video file {path}")


class AsyncVideoWriter:
    """Own the writer and drain all accepted frames on release.

    The producer transfers ownership of each frame to this object. When the
    bounded buffer fills it waits: output frames must never be silently lost.
    """

    def __init__(self, writer: cv2.VideoWriter, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("Output buffer capacity must be positive")
        self._writer = writer
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=capacity)
        self._error: BaseException | None = None
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="video-writer")
        self._thread.start()

    def _check_error(self) -> None:
        if self._error is not None:
            raise RuntimeError("Video encoding failed") from self._error

    def _enqueue(self, frame: Any) -> None:
        while True:
            self._check_error()
            try:
                self._queue.put(frame, timeout=0.05)
                self._check_error()
                return
            except queue.Full:
                continue

    def write(self, frame: Any) -> None:
        if self._closed:
            raise RuntimeError("Video writer is closed")
        self._enqueue(frame)

    def _run(self) -> None:
        try:
            while True:
                frame = self._queue.get()
                if frame is None:
                    break
                self._writer.write(frame)
        except BaseException as error:
            self._error = error
        finally:
            try:
                self._writer.release()
            except BaseException as error:
                self._error = error

    def release(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                self._enqueue(None)
            finally:
                self._thread.join()
        self._check_error()
