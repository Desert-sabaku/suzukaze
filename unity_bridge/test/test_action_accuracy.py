import math

import pytest
from bridge.v1 import bridge_pb2 as bridge_pb
from gesture_detection.recognition_types import GestureSample

from unity_bridge.gesture_codec import decode_message, encode_message
from unity_bridge.gesture_delivery import DeliveryOutbox


@pytest.mark.parametrize("score", [None, 0.0, 0.5, 1.0])
def test_accuracy_presence_retry_and_staleness(score):
    outbox = DeliveryOutbox()
    sample = GestureSample(
        "BOW",
        True,
        1,
        (("RAMUNE", 1),),
        action_accuracy=score,
        occurrence_accuracies=(score,),
    )
    outbox.publish(sample, now=1)
    state, event = outbox.state(1), outbox.events(1)[0]
    for message, kind in ((state, "state"), (event, "event")):
        wire = encode_message(message)
        envelope = bridge_pb.BridgeEnvelope.FromString(wire)
        assert envelope.WhichOneof("payload") == "gesture"
        payload = getattr(envelope.gesture, kind)
        assert payload.HasField("action_accuracy") == (score is not None)
        assert decode_message(wire).get("action_accuracy") == score
    outbox.publish(GestureSample("NONE", False, 1.1, ()), now=1.1)
    assert "action_accuracy" not in outbox.state(1.1)
    assert outbox.events(1.2) == [event]
    assert outbox.events(1.3, reconnect=True) == [event]
    outbox.publish(sample, now=1.4)
    assert "action_accuracy" not in outbox.state(1.5)


@pytest.mark.parametrize(
    "value", [-0.1, 1.1, math.nan, math.inf, -math.inf, True, "0.5", 10**1000]
)
@pytest.mark.parametrize("kind", ["state", "event"])
def test_codec_rejects_invalid_accuracy(value, kind):
    outbox = DeliveryOutbox()
    outbox.publish(GestureSample("BOW", True, 1, (("RAMUNE", 1),)), now=1)
    message = outbox.state(1) if kind == "state" else outbox.events(1)[0]
    with pytest.raises(ValueError):
        encode_message({**message, "action_accuracy": value})
    if type(value) is float:
        envelope = bridge_pb.BridgeEnvelope.FromString(encode_message(message))
        getattr(envelope.gesture, kind).action_accuracy = value
        with pytest.raises(ValueError):
            decode_message(envelope.SerializeToString())


@pytest.mark.parametrize(
    "extra", [{"gesture": "NONE"}, {"tracking": False}, {"fresh": False}]
)
def test_codec_rejects_accuracy_without_current_gesture(extra):
    outbox = DeliveryOutbox()
    outbox.publish(GestureSample("BOW", True, 1, (), action_accuracy=0), now=1)
    with pytest.raises(ValueError):
        encode_message({**outbox.state(1), **extra})
