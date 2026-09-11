import multiprocessing as mp
import queue
from typing import Any

import numpy as np
import numpy.typing as npt


def put_latest(channel: Any, value: Any) -> None:
    """Keep a bounded IPC queue focused on the newest frame or sentinel."""
    try:
        channel.put_nowait(value)
        return
    except queue.Full:
        pass

    try:
        channel.get_nowait()
    except queue.Empty:
        pass

    try:
        channel.put_nowait(value)
    except queue.Full:
        pass


def get_latest(channel: Any, default: Any) -> Any:
    value = default
    try:
        while True:
            value = channel.get_nowait()
    except queue.Empty:
        return value


class SharedLatestFrame:
    """Single-producer/single-consumer mailbox with a shared uint8 image.

    A busy reader may cause a publication to be skipped. Readers always copy
    under the lock so inference never sees a partially overwritten frame.
    """

    def __init__(self, shape: tuple[int, ...]) -> None:
        self.shape = shape
        self._buffer = mp.RawArray("B", int(np.prod(shape)))
        self._lock = mp.Lock()
        self._ready = mp.Event()
        self._closed = mp.Event()

    def publish(self, frame: npt.NDArray[Any]) -> bool:
        if frame.shape != self.shape or frame.dtype != np.uint8:
            raise ValueError("Frame shape or dtype does not match shared buffer")
        if self._closed.is_set() or not self._lock.acquire(False):
            return False
        try:
            np.copyto(np.frombuffer(self._buffer, dtype=np.uint8).reshape(self.shape), frame)
            self._ready.set()
            return True
        finally:
            self._lock.release()

    def get(self) -> npt.NDArray[np.uint8] | None:
        if self._closed.is_set():
            return None
        self._ready.wait()
        with self._lock:
            if self._closed.is_set():
                return None
            frame = np.frombuffer(self._buffer, dtype=np.uint8).reshape(self.shape).copy()
            self._ready.clear()
            return frame

    def close(self) -> None:
        self._closed.set()
        self._ready.set()
