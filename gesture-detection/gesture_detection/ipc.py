import queue
from typing import Any


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
