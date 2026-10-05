"""Validated conversion between flat delivery dictionaries and protobuf."""

import math

from google.protobuf.message import DecodeError

from .gen.gesture.v1 import gesture_pb2 as pb

MAX_MESSAGE_BYTES = 8192

_ENUMS = {
    "state": ("gesture", {"NONE": 1, "FANNING": 2, "RELAXING": 3, "BOW": 4}),
    "event": ("gesture", {"RAMUNE": 1, "UCHIMIZU": 2}),
    "ack": ("status", {"accepted": 1, "ignored": 2, "expired": 3, "duplicate": 4}),
}
_FIELDS = {
    "state": (
        "sequence",
        "sent_at",
        "stale_timeout",
        "fresh",
        "gesture",
        "tracking",
        "observed_at",
        "frame_id",
        "source_timestamp",
    ),
    "event": (
        "event_id",
        "gesture",
        "occurred_at",
        "expires_at",
        "frame_id",
        "source_timestamp",
    ),
    "ack": ("event_id", "status"),
}
_OPTIONAL = {"observed_at", "frame_id", "source_timestamp"}
_TIMES = {
    "sent_at",
    "stale_timeout",
    "observed_at",
    "source_timestamp",
    "occurred_at",
    "expires_at",
}


def _check_size(size: int) -> None:
    if not 1 <= size <= MAX_MESSAGE_BYTES:
        raise ValueError(f"Message length must be 1..{MAX_MESSAGE_BYTES}")


def _validate(message: dict) -> str:
    if not isinstance(message, dict):
        raise ValueError("Message must be a dictionary")  # noqa: TRY004
    kind = message.get("type")
    if not isinstance(kind, str) or kind not in _FIELDS:
        raise ValueError("Unknown message type")
    if type(message.get("version")) is not int or message["version"] != 1:
        raise ValueError("Unsupported protocol version")
    if not isinstance(message.get("session_id"), str) or not message["session_id"]:
        raise ValueError("session_id must be a nonempty string")
    if set(message) - {"type", "version", "session_id", *_FIELDS[kind]}:
        raise ValueError("Unknown message fields")
    enum_field, values = _ENUMS[kind]
    value = message.get(enum_field)
    if not isinstance(value, str) or value not in values:
        raise ValueError(f"Unknown {enum_field}")
    for field in _FIELDS[kind]:
        value = message.get(field)
        if field in _OPTIONAL and value is None:
            continue
        if field in {"sequence", "event_id", "frame_id"}:
            minimum = 0 if field == "frame_id" else 1
            if type(value) is not int or not minimum <= value < 2**64:
                raise ValueError(f"Invalid {field}")
        elif field in _TIMES:
            try:
                valid = (
                    isinstance(value, int | float)
                    and not isinstance(value, bool)
                    and math.isfinite(value)
                )
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError(f"{field} must be finite")
        elif field in {"fresh", "tracking"} and type(value) is not bool:
            raise ValueError(f"{field} must be bool")
    if kind == "state" and message["stale_timeout"] <= 0:
        raise ValueError("stale_timeout must be positive")
    if kind == "event" and message["expires_at"] <= message["occurred_at"]:
        raise ValueError("expires_at must follow occurred_at")
    return kind


def encode_message(message: dict) -> bytes:
    """Encode a validated flat v1 dictionary; omitted metadata means None."""
    kind = _validate(message)
    envelope = pb.GestureEnvelope(version=1, session_id=message["session_id"])
    payload = getattr(envelope, kind)
    enum_field, values = _ENUMS[kind]
    try:
        for field in _FIELDS[kind]:
            value = message.get(field)
            if value is not None:
                setattr(payload, field, values[value] if field == enum_field else value)
        data = envelope.SerializeToString(deterministic=True)
    except (UnicodeError, TypeError, OverflowError) as exc:
        raise ValueError("Invalid protobuf value") from exc
    _check_size(len(data))
    return data


def decode_message(data: bytes) -> dict:
    """Decode and validate; absent optional metadata is returned as None.

    Unknown protobuf fields are tolerated for forward compatibility.
    """
    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    _check_size(len(data))
    envelope = pb.GestureEnvelope()
    try:
        envelope.ParseFromString(data)
    except DecodeError as exc:
        raise ValueError("Malformed protobuf") from exc
    kind = envelope.WhichOneof("payload")
    if kind is None:
        raise ValueError("Missing payload")
    message = {
        "version": envelope.version,
        "session_id": envelope.session_id,
        "type": kind,
    }
    payload = getattr(envelope, kind)
    enum_field, values = _ENUMS[kind]
    reverse = {number: name for name, number in values.items()}
    for field in _FIELDS[kind]:
        if field in _OPTIONAL and not payload.HasField(field):
            message[field] = None
            continue
        value = getattr(payload, field)
        message[field] = reverse.get(value) if field == enum_field else value
    _validate(message)
    return message
