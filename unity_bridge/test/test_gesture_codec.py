import json
from pathlib import Path

import pytest

from unity_bridge.gen.gesture.v1 import gesture_pb2 as pb
from unity_bridge.gesture_codec import decode_message, encode_message

FIXTURES = json.loads((Path(__file__).parent / "fixtures/messages.json").read_text())


@pytest.mark.parametrize("fixture", FIXTURES)
def test_cross_language_fixture(fixture):
    wire = bytes.fromhex(fixture["protobuf_hex"])
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
    envelope = pb.GestureEnvelope.FromString(encode_message(FIXTURES[1]["message"]))
    assert envelope.state.HasField("frame_id")
    assert envelope.state.HasField("observed_at")
    assert envelope.state.HasField("source_timestamp")


def test_bow_state_round_trips():
    message = {**FIXTURES[0]["message"], "gesture": "BOW"}
    wire = encode_message(message)
    assert (
        pb.GestureEnvelope.FromString(wire).state.gesture == pb.CONTINUOUS_GESTURE_BOW
    )
    assert decode_message(wire) == message


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
    envelope = pb.GestureEnvelope.FromString(encode_message(message))
    setattr(getattr(envelope, kind), field, value)
    with pytest.raises(ValueError):
        decode_message(envelope.SerializeToString())


def test_envelope_validation_and_unknown_fields():
    wire = encode_message(FIXTURES[0]["message"])
    assert decode_message(wire + b"\xa0\x06\x01") == FIXTURES[0]["message"]
    for field, value in [("version", 0), ("version", 2), ("session_id", "")]:
        envelope = pb.GestureEnvelope.FromString(wire)
        setattr(envelope, field, value)
        with pytest.raises(ValueError):
            decode_message(envelope.SerializeToString())
    with pytest.raises(ValueError):
        encode_message({**FIXTURES[0]["message"], "session_id": "x" * 8192})
    with pytest.raises(ValueError):
        encode_message({**FIXTURES[3]["message"], "expires_at": 10.0})
    for field in ("sequence", "sent_at", "fresh", "tracking", "gesture"):
        message = dict(FIXTURES[0]["message"])
        del message[field]
        with pytest.raises(ValueError):
            encode_message(message)
