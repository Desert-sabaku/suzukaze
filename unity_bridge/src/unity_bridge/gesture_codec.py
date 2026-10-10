"""Validated conversion between flat delivery dictionaries and protobuf."""

import math
from typing import Any

from gesture_detection.gesture_types import Gesture, Phase, valid_action_phase
from google.protobuf.message import DecodeError

from .gen.bridge.v1 import bridge_pb2 as bridge_pb
from .gen.gesture.v1 import gesture_pb2 as pb

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 8192

_ENUMS = {
    "state": (
        "gesture",
        {
            Gesture(name.removeprefix("CONTINUOUS_GESTURE_")): number
            for name, number in pb.ContinuousGesture.items()
            if number != pb.CONTINUOUS_GESTURE_UNSPECIFIED
        },
    ),
    "event": (
        "gesture",
        {
            Gesture(name.removeprefix("OCCURRENCE_GESTURE_")): number
            for name, number in pb.OccurrenceGesture.items()
            if number != pb.OCCURRENCE_GESTURE_UNSPECIFIED
        },
    ),
    "ack": (
        "status",
        {
            name.removeprefix("ACK_STATUS_").lower(): number
            for name, number in pb.AckStatus.items()
            if number != pb.ACK_STATUS_UNSPECIFIED
        },
    ),
}
_PROGRESS_ENUMS = {
    "action": {
        Gesture(name.removeprefix("ACTION_")): number
        for name, number in pb.Action.items()
        if number != pb.ACTION_UNSPECIFIED
    },
    "phase": {
        Phase(name.removeprefix("PHASE_")): number
        for name, number in pb.Phase.items()
        if number != pb.PHASE_UNSPECIFIED
    },
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
        "action",
        "phase",
        "booth_present",
        "action_accuracy",
    ),
    "event": (
        "event_id",
        "gesture",
        "occurred_at",
        "expires_at",
        "action_accuracy",
        "frame_id",
        "source_timestamp",
    ),
    "ack": ("event_id", "status"),
}
_OPTIONAL = {
    "action_accuracy",
    "observed_at",
    "frame_id",
    "source_timestamp",
    "action",
    "phase",
    "booth_present",
}
# Optional fields that decode to a missing key rather than None when unset.
_OMITTED_WHEN_UNSET = {"action", "phase", "booth_present", "action_accuracy"}
# Integer fields and their minimum; all must also fit in uint64.
_INTEGER_MINIMUMS = {"sequence": 1, "event_id": 1, "frame_id": 0}
_BOOLS = {"fresh", "tracking", "booth_present"}
_NAMES = {"action", "phase"}
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


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _is_finite_number(value: Any) -> bool:
    try:
        return _is_number(value) and math.isfinite(value)
    except OverflowError:
        return False


def _validate(message: dict) -> str:
    """Check a flat message completely and return its type."""
    kind = _validate_header(message)
    for field in _FIELDS[kind]:
        value = message.get(field)
        if field in _OPTIONAL and value is None:
            continue
        _validate_field(field, value)
    if kind == "state":
        _validate_state(message)
    elif kind == "event":
        _validate_event(message)
    return kind


def _validate_header(message: dict) -> str:
    """Check type, version, session and the field set; return the type."""
    if not isinstance(message, dict):
        raise ValueError("Message must be a dictionary")  # noqa: TRY004
    kind = message.get("type")
    if not isinstance(kind, str) or kind not in _FIELDS:
        raise ValueError("Unknown message type")
    if (
        type(message.get("version")) is not int
        or message["version"] != PROTOCOL_VERSION
    ):
        raise ValueError("Unsupported protocol version")
    if not isinstance(message.get("session_id"), str) or not message["session_id"]:
        raise ValueError("session_id must be a nonempty string")
    if set(message) - {"type", "version", "session_id", *_FIELDS[kind]}:
        raise ValueError("Unknown message fields")
    enum_field, values = _ENUMS[kind]
    value = message.get(enum_field)
    if not isinstance(value, str) or value not in values:
        raise ValueError(f"Unknown {enum_field}")
    return kind


def _validate_field(field: str, value: Any) -> None:
    """Check one present field's type and range."""
    if field == "action_accuracy":
        if not _is_number(value) or not 0 <= value <= 1:
            raise ValueError("action_accuracy must be finite and in [0, 1]")
    elif field in _INTEGER_MINIMUMS:
        if type(value) is not int or not _INTEGER_MINIMUMS[field] <= value < 2**64:
            raise ValueError(f"Invalid {field}")
    elif field in _TIMES:
        if not _is_finite_number(value):
            raise ValueError(f"{field} must be finite")
    elif field in _BOOLS:
        if type(value) is not bool:
            raise ValueError(f"{field} must be bool")
    elif field in _NAMES and (not isinstance(value, str) or not value):
        raise ValueError(f"{field} must be a nonempty string")


def _validate_state(message: dict) -> None:
    """Accuracy and progress are only meaningful for a fresh, tracked person."""
    tracked = message["fresh"] and message["tracking"]
    if message.get("action_accuracy") is not None and (
        not tracked or message["gesture"] == Gesture.NONE
    ):
        raise ValueError("State accuracy requires a fresh tracked gesture")
    action, phase = message.get("action"), message.get("phase")
    if (action is None) != (phase is None):
        raise ValueError("action and phase must be present together")
    if action is not None and (not valid_action_phase(action, phase) or not tracked):
        raise ValueError("Phase requires a valid action/phase pair and fresh tracking")
    if message["stale_timeout"] <= 0:
        raise ValueError("stale_timeout must be positive")


def _validate_event(message: dict) -> None:
    if message["expires_at"] <= message["occurred_at"]:
        raise ValueError("expires_at must follow occurred_at")


def _enum_mapping(kind: str, field: str) -> dict | None:
    """The name-to-number mapping for an enum field, or None for plain fields."""
    enum_field, values = _ENUMS[kind]
    return values if field == enum_field else _PROGRESS_ENUMS.get(field)


def encode_message(message: dict) -> bytes:
    """Encode a validated flat v1 dictionary; omitted metadata means None."""
    kind = _validate(message)
    envelope = pb.GestureEnvelope(
        version=PROTOCOL_VERSION, session_id=message["session_id"]
    )
    payload = getattr(envelope, kind)
    try:
        for field in _FIELDS[kind]:
            value = message.get(field)
            if value is None:
                continue
            mapping = _enum_mapping(kind, field)
            setattr(payload, field, mapping[value] if mapping is not None else value)
        return _wrap(envelope)
    except (UnicodeError, TypeError, OverflowError) as exc:
        raise ValueError("Invalid protobuf value") from exc


def _wrap(envelope: pb.GestureEnvelope) -> bytes:
    data = bridge_pb.BridgeEnvelope(gesture=envelope).SerializeToString(
        deterministic=True
    )
    _check_size(len(data))
    return data


def decode_bridge(data: bytes) -> bridge_pb.BridgeEnvelope:
    """Parse one WebSocket message; the caller dispatches on its payload."""
    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    _check_size(len(data))
    envelope = bridge_pb.BridgeEnvelope()
    try:
        envelope.ParseFromString(data)
    except DecodeError as exc:
        raise ValueError("Malformed protobuf") from exc
    return envelope


def decode_message(data: bytes) -> dict:
    """Decode and validate a gesture message; absent optional metadata is None.

    Unknown protobuf fields are tolerated for forward compatibility.
    """
    bridge = decode_bridge(data)
    if bridge.WhichOneof("payload") != "gesture":
        raise ValueError("Expected a gesture message")
    return decode_gesture(bridge.gesture)


def decode_gesture(envelope: pb.GestureEnvelope) -> dict:
    kind = envelope.WhichOneof("payload")
    if kind is None:
        raise ValueError("Missing payload")
    message = {
        "version": envelope.version,
        "session_id": envelope.session_id,
        "type": kind,
    }
    payload = getattr(envelope, kind)
    for field in _FIELDS[kind]:
        if field in _OPTIONAL and not payload.HasField(field):
            if field not in _OMITTED_WHEN_UNSET:
                message[field] = None
            continue
        value = getattr(payload, field)
        mapping = _enum_mapping(kind, field)
        if mapping is None:
            message[field] = value
            continue
        name = next((name for name, number in mapping.items() if number == value), None)
        if name is None:
            raise ValueError(f"Unknown {field}")
        message[field] = name
    _validate(message)
    return message
