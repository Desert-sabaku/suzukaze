"""Version 1 gesture wire protocol; no camera or transport dependencies."""

from .codec import decode_message, encode_message
from .framing import MAX_MESSAGE_BYTES, FrameDecoder, frame_message

__all__ = [
    "MAX_MESSAGE_BYTES", "FrameDecoder", "decode_message", "encode_message",
    "frame_message",
]
