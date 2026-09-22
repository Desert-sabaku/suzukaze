import pytest

from gesture_detection.gesture_delivery import DeliveryOutbox
from gesture_detection.recognition_types import PoseResult


def result(gesture: str = "FANNING", *events: str) -> PoseResult:
    return {
        "landmarks": [],
        "selected_action": gesture,
        "relaxing_state": False,
        "current": {"gesture": gesture, "tracking": True},
        "frame_id": 3,
        "timestamp": 10.0,
        "occurrences": events,
    }


def test_events_survive_state_replacement_and_retry_with_original_expiry():
    outbox = DeliveryOutbox()
    outbox.publish(result("RAMUNE", "RAMUNE"), observed_at=10.0, now=10.1)
    outbox.publish(result(), observed_at=10.2, now=10.2)
    first = outbox.events(10.2)
    assert len(first) == 1
    assert first[0]["expires_at"] == 11.0
    assert outbox.events(10.21) == []
    assert outbox.events(10.4) == first
    assert outbox.events(10.41, reconnect=True) == first
    assert outbox.events(11.0) == []


@pytest.mark.parametrize("status", ["accepted", "ignored", "expired", "duplicate"])
def test_ack_removes_only_matching_session_and_event(status):
    outbox = DeliveryOutbox()
    outbox.publish(result("UCHIMIZU", "UCHIMIZU"), observed_at=10.0, now=10.0)
    ack = {
        "version": 1,
        "type": "ack",
        "event_id": 1,
        "status": status,
        "session_id": "previous-session",
    }
    assert not outbox.acknowledge(ack)
    assert len(outbox.events(10.1)) == 1
    ack["session_id"] = outbox.session_id
    assert outbox.acknowledge(ack)
    assert not outbox.acknowledge(ack)
    assert outbox.events(10.2) == []


def test_stale_capture_cannot_be_refreshed_by_network_or_inference():
    outbox = DeliveryOutbox()
    outbox.publish(result(), observed_at=10.0, now=10.4)
    assert outbox.state(10.49)["gesture"] == "FANNING"
    stale = outbox.state(10.5)
    assert stale["gesture"] == "NONE"
    assert not stale["fresh"]
    assert not stale["tracking"]
    assert outbox.state(11.0)["sequence"] > stale["sequence"]
    outbox.publish(result("RAMUNE", "RAMUNE"), observed_at=10.0, now=11.1)
    assert outbox.events(11.1) == []


def test_lost_pose_is_fresh_but_not_tracking():
    outbox = DeliveryOutbox()
    snapshot = result("NONE")
    snapshot["current"] = {"gesture": "NONE", "tracking": False}
    outbox.publish(snapshot, observed_at=10.0, now=10.0)
    state = outbox.state(10.1)
    assert state["fresh"] and not state["tracking"]


def test_capacity_fails_explicitly_and_expired_events_release_capacity():
    outbox = DeliveryOutbox(max_pending=1)
    outbox.publish(result("RAMUNE", "RAMUNE"), observed_at=10.0, now=10.0)
    with pytest.raises(RuntimeError, match="capacity"):
        outbox.publish(result("RAMUNE", "RAMUNE"), observed_at=10.1, now=10.1)
    outbox.publish(result("RAMUNE", "RAMUNE"), observed_at=11.0, now=11.0)
    assert len(outbox.events(11.0)) == 1
    assert DeliveryOutbox().session_id != outbox.session_id


@pytest.mark.parametrize(
    "ack", [None, [], {}, {"event_id": []}, {"version": 1, "type": "ack", "status": []}]
)
def test_malformed_ack_does_not_crash(ack):
    assert not DeliveryOutbox().acknowledge(ack)
