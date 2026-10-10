import json
from pathlib import Path
from typing import cast

import pytest
from bridge.v1 import bridge_pb2 as bridge_pb
from gesture.v1 import gesture_pb2 as pb
from gesture_detection.gesture_types import Gesture, Phase

from unity_bridge.gesture_codec import decode_message, encode_message


def _open(wire: bytes) -> pb.GestureEnvelope:
    return bridge_pb.BridgeEnvelope.FromString(wire).gesture


def _wire(envelope: pb.GestureEnvelope) -> bytes:
    return bridge_pb.BridgeEnvelope(gesture=envelope).SerializeToString(
        deterministic=True
    )


FIXTURES = json.loads((Path(__file__).parent / "fixtures/messages.json").read_text())


@pytest.mark.parametrize("fixture", FIXTURES)
def test_cross_language_fixture(fixture):
    raw = bytes.fromhex(fixture["protobuf_hex"])
    # BridgeEnvelope.gesture(field 1)で包む。長さは最大8192なので varint は2byteまで。
    n = len(raw)
    length = bytes([n]) if n < 128 else bytes([n & 0x7F | 0x80, n >> 7])
    wire = b"\x0a" + length + raw
    assert encode_message(fixture["message"]) == wire
    assert decode_message(wire) == fixture["message"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", True),
        ("version", 2),
        ("session_id", ""),
        ("sequence", 0),
        ("sequence", -1),
        ("sequence", 2**64),
        ("sequence", True),
        ("frame_id", -1),
        ("frame_id", 1.5),
        ("sent_at", float("nan")),
        ("sent_at", float("inf")),
        ("sent_at", 10**1000),
        ("stale_timeout", 0),
        ("source_timestamp", float("-inf")),
        ("observed_at", True),
        ("fresh", 1),
        ("tracking", None),
        ("gesture", "UNSPECIFIED"),
        ("gesture", "RAMUNE"),
        ("extra", 1),
        ("type", []),
    ],
)
def test_invalid_state(field, value):
    with pytest.raises(ValueError):
        encode_message({**FIXTURES[0]["message"], field: value})


def test_optional_presence():
    message = dict(FIXTURES[0]["message"])
    for field in ("observed_at", "frame_id", "source_timestamp"):
        del message[field]
    assert decode_message(encode_message(message)) == FIXTURES[0]["message"]
    envelope = _open(encode_message(FIXTURES[1]["message"]))
    assert envelope.state.HasField("frame_id")
    assert envelope.state.HasField("observed_at")
    assert envelope.state.HasField("source_timestamp")


def test_bow_state_round_trips():
    message = {**FIXTURES[0]["message"], "gesture": "BOW"}
    wire = encode_message(message)
    assert _open(wire).state.gesture == pb.CONTINUOUS_GESTURE_BOW
    assert decode_message(wire) == message


def test_preparation_phase_round_trips_with_none_action():
    message = {
        **FIXTURES[1]["message"],
        "gesture": "NONE",
        "fresh": True,
        "tracking": True,
        "action": Gesture.RAMUNE,
        "phase": Phase.READY,
    }
    wire = encode_message(message)
    assert decode_message(wire) == message
    assert _open(wire).state.HasField("phase")


@pytest.mark.parametrize(
    "extra",
    [
        {"action": "RAMUNE"},
        {"phase": "READY"},
        {"action": "UNKNOWN", "phase": "READY"},
        {"action": "RAMUNE", "phase": ""},
        {"action": "RAMUNE", "phase": 1},
        {"action": "RAMUNE", "phase": "READY", "fresh": False},
        {"action": "RAMUNE", "phase": "READY", "tracking": False},
    ],
)
def test_invalid_phase_is_rejected(extra):
    with pytest.raises(ValueError):
        encode_message(
            {**FIXTURES[1]["message"], "fresh": True, "tracking": True, **extra}
        )


@pytest.mark.parametrize(
    "action,phase",
    [
        ("RAMUNE", "NONE"),
        ("RAMUNE", "IDLE"),
        ("RAMUNE", "ACTIVE"),
        ("UCHIMIZU", "OPENED"),
        ("FANNING", "READY"),
        ("RELAXING", "HOLD"),
        ("BOW", "READY"),
        ("RAMUNE", "UNKNOWN"),
        (Gesture.NONE, Phase.READY),
        (Gesture.FANNING, Phase.POSITION),
        (Gesture.RELAXING, Phase.DWELL),
        (Gesture.BOW, Phase.BENDING),
        (Gesture.BOW, Phase.RETURNING),
    ],
)
def test_invalid_action_phase_pair_is_rejected_on_encode_and_decode(action, phase):
    message = {**FIXTURES[1]["message"], "fresh": True, "tracking": True}
    with pytest.raises(ValueError, match="valid action/phase pair"):
        encode_message({**message, "action": action, "phase": phase})
    # Bypass the encoder to exercise validation of a remote sender's payload.
    envelope = _open(encode_message(message))
    envelope.state.action = cast(pb.Action, pb.Action.Value(f"ACTION_{action}"))
    envelope.state.phase = cast(
        pb.Phase, dict(pb.Phase.items()).get(f"PHASE_{phase}", 99)
    )
    with pytest.raises(ValueError):
        decode_message(_wire(envelope))


@pytest.mark.parametrize(
    "action,phase",
    [
        (Gesture.RAMUNE, Phase.FORMING),
        (Gesture.RAMUNE, Phase.READY),
        (Gesture.RAMUNE, Phase.OPENED),
        (Gesture.RAMUNE, Phase.WAIT_RELEASE),
        (Gesture.UCHIMIZU, Phase.READY),
        (Gesture.UCHIMIZU, Phase.SWING),
        (Gesture.FANNING, Phase.ACTIVE),
        (Gesture.RELAXING, Phase.ACTIVE),
        (Gesture.BOW, Phase.HOLD),
    ],
)
def test_valid_action_phase_pairs_round_trip(action, phase):
    message = {
        **FIXTURES[1]["message"],
        "fresh": True,
        "tracking": True,
        "action": action,
        "phase": phase,
    }
    assert decode_message(encode_message(message)) == message


def test_python_vocabulary_matches_generated_protocol_enums():
    assert {member.value for member in Gesture} == {
        name.removeprefix("ACTION_")
        for name, _ in pb.Action.items()
        if name != "ACTION_UNSPECIFIED"
    }
    assert {member.value for member in Phase} == {
        name.removeprefix("PHASE_")
        for name, _ in pb.Phase.items()
        if name != "PHASE_UNSPECIFIED"
    }


@pytest.mark.parametrize(
    "field,value", [("action", 0), ("action", 99), ("phase", 0), ("phase", 99)]
)
def test_unknown_progress_enum_numbers_are_rejected(field, value):
    message = {
        **FIXTURES[1]["message"],
        "fresh": True,
        "tracking": True,
        "action": Gesture.RAMUNE,
        "phase": Phase.READY,
    }
    envelope = _open(encode_message(message))
    setattr(envelope.state, field, value)
    with pytest.raises(ValueError, match=f"Unknown {field}"):
        decode_message(_wire(envelope))


@pytest.mark.parametrize("kind", ["state", "event"])
@pytest.mark.parametrize("score", [0.0, 0.5, 1.0])
def test_action_accuracy_schema_preserves_presence_and_existing_message_semantics(
    kind, score
):
    message = next(f["message"] for f in FIXTURES if f["message"]["type"] == kind)
    if kind == "state":
        message = {**message, "gesture": "BOW", "fresh": True, "tracking": True}
    envelope = _open(encode_message(message))
    payload = getattr(envelope, kind)
    assert not payload.HasField("action_accuracy")

    payload.action_accuracy = score
    wire = _wire(envelope)
    restored = _open(wire)
    assert getattr(restored, kind).HasField("action_accuracy")
    assert getattr(restored, kind).action_accuracy == score
    assert decode_message(wire) == {**message, "action_accuracy": score}
    assert encode_message({**message, "action_accuracy": score}) == wire

    getattr(restored, kind).ClearField("action_accuracy")
    assert _wire(restored) == encode_message(message)


@pytest.mark.parametrize("wire", [b"", b"\xff", b"x" * 8193, b"\x08\x01"])
def test_bad_wire(wire):
    with pytest.raises(ValueError):
        decode_message(wire)


@pytest.mark.parametrize(
    "kind,field,value",
    [
        ("state", "gesture", 0),
        ("state", "gesture", 99),
        ("state", "sent_at", float("nan")),
        ("state", "sequence", 0),
        ("event", "gesture", 0),
        ("event", "expires_at", 1.0),
        ("ack", "status", 0),
        ("ack", "status", 99),
        ("ack", "event_id", 0),
    ],
)
def test_decode_semantics(kind, field, value):
    message = next(f["message"] for f in FIXTURES if f["message"]["type"] == kind)
    envelope = _open(encode_message(message))
    setattr(getattr(envelope, kind), field, value)
    with pytest.raises(ValueError):
        decode_message(_wire(envelope))


def test_envelope_validation_and_unknown_fields():
    wire = encode_message(FIXTURES[0]["message"])
    assert decode_message(wire + b"\xa0\x06\x01") == FIXTURES[0]["message"]
    for field, value in [("version", 0), ("version", 2), ("session_id", "")]:
        envelope = _open(wire)
        setattr(envelope, field, value)
        with pytest.raises(ValueError):
            decode_message(_wire(envelope))
    with pytest.raises(ValueError):
        encode_message({**FIXTURES[0]["message"], "session_id": "x" * 8192})
    with pytest.raises(ValueError):
        encode_message({**FIXTURES[3]["message"], "expires_at": 10.0})
    for field in ("sequence", "sent_at", "fresh", "tracking", "gesture"):
        message = dict(FIXTURES[0]["message"])
        del message[field]
        with pytest.raises(ValueError):
            encode_message(message)
