import queue


def put_latest(channel, value):
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


def get_latest(channel, default):
    try:
        value = default
        while True:
            value = channel.get_nowait()
    except queue.Empty:
        return value
