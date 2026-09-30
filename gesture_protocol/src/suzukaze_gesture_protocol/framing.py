"""Four-byte unsigned big-endian length followed by a protobuf payload."""

MAX_MESSAGE_BYTES = 8192


def _check_size(size: int) -> None:
    if not 1 <= size <= MAX_MESSAGE_BYTES:
        raise ValueError(f"Message length must be 1..{MAX_MESSAGE_BYTES}")


def frame_message(payload: bytes) -> bytes:
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    _check_size(len(payload))
    return len(payload).to_bytes(4, "big") + payload


class FrameDecoder:
    """Incremental decoder. Invalid length/partial EOF poisons this instance.

    Create a new decoder for each connection. Call eof() on socket EOF to
    distinguish a clean boundary from a truncated frame.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._length: int | None = None
        self._closed = False

    def feed(self, data: bytes) -> list[bytes]:
        if self._closed:
            raise ValueError("Decoder is closed")
        if not isinstance(data, bytes):
            raise TypeError("data must be bytes")
        frames = []
        offset = 0
        while offset < len(data):
            target = 4 if self._length is None else self._length
            count = min(target - len(self._buffer), len(data) - offset)
            self._buffer.extend(data[offset:offset + count])
            offset += count
            if len(self._buffer) != target:
                continue
            if self._length is None:
                self._length = int.from_bytes(self._buffer, "big")
                self._buffer.clear()
                try:
                    _check_size(self._length)
                except ValueError:
                    self._closed = True
                    raise
            else:
                frames.append(bytes(self._buffer))
                self._buffer.clear()
                self._length = None
        return frames

    def eof(self) -> None:
        if self._closed:
            raise ValueError("Decoder is closed")
        self._closed = True
        if self._buffer or self._length is not None:
            raise ValueError("Truncated frame at EOF")
