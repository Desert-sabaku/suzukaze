"""Recent errors from the bridge and Unity, shown on the admin page."""

import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

MAX_ERRORS = 50


class ErrorLog:
    """Thread-safe ring buffer; the MCU worker thread also records here."""

    def __init__(
        self, limit: int = MAX_ERRORS, clock: Callable[[], float] = time.time
    ) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: deque[dict[str, Any]] = deque(maxlen=limit)
        self._next_id = 1

    def record(self, source: str, level: str, message: str, detail: str = "") -> None:
        with self._lock:
            self._entries.appendleft(
                {
                    "id": self._next_id,
                    # 画面で時刻を出すので、壁時計の UNIX 秒。
                    "at": self._clock(),
                    "source": source,
                    "level": level,
                    "message": message,
                    "detail": detail,
                }
            )
            self._next_id += 1

    def entries(self) -> list[dict[str, Any]]:
        """Newest first."""
        with self._lock:
            return list(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
