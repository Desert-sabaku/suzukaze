import pytest
from gesture_detection.recognition_types import (
    ContinuousGesture,
    GestureSample,
    OccurrenceGesture,
)

from unity_bridge.gesture_delivery import DeliveryOutbox


def result(
    gesture: ContinuousGesture = "FANNING",
    *events: OccurrenceGesture,
    observed_at: float = 10.0,
    tracking: bool = True,
) -> GestureSample:
    return GestureSample(
        gesture, tracking, observed_at, tuple((e, observed_at) for e in events), 3, 10.0
    )


def test_events_survive_state_replacement_and_retry_with_original_expiry():
    outbox = DeliveryOutbox()
    outbox.publish(result("NONE", "RAMUNE"), now=10.1)
    outbox.publish(result(observed_at=10.2), now=10.2)
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
    outbox.publish(result("NONE", "UCHIMIZU"), now=10.0)
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
    outbox.publish(result(), now=10.4)
    assert outbox.state(10.49)["gesture"] == "FANNING"
    stale = outbox.state(10.5)
    assert stale["gesture"] == "NONE"
    assert not stale["fresh"]
    assert not stale["tracking"]
    assert outbox.state(11.0)["sequence"] > stale["sequence"]
    outbox.publish(result("NONE", "RAMUNE"), now=11.1)
    assert outbox.events(11.1) == []


def test_lost_pose_is_fresh_but_not_tracking():
    outbox = DeliveryOutbox()
    outbox.publish(result("NONE", tracking=False), now=10.0)
    state = outbox.state(10.1)
    assert state["fresh"] and not state["tracking"]


def test_phase_updates_independently_of_action_and_clears_on_stale_or_lost_pose():
    outbox = DeliveryOutbox()
    for now, phase in ((10.0, "FORMING"), (10.1, "READY")):
        outbox.publish(
            GestureSample("NONE", True, now, (), phase_action="RAMUNE", phase=phase),
            now=now,
        )
        state = outbox.state(now)
        assert state["gesture"] == "NONE"
        assert (state["phase_action"], state["phase"]) == ("RAMUNE", phase)
        assert outbox.events(now) == []
    assert "phase" not in outbox.state(10.6)
    outbox.publish(
        GestureSample("NONE", False, 10.7, (), phase_action="RAMUNE", phase="READY"),
        now=10.7,
    )
    assert "phase_action" not in outbox.state(10.7)


def test_capacity_fails_explicitly_and_expired_events_release_capacity():
    outbox = DeliveryOutbox(max_pending=1)
    outbox.publish(result("NONE", "RAMUNE"), now=10.0)
    with pytest.raises(RuntimeError, match="capacity"):
        outbox.publish(result("NONE", "RAMUNE", observed_at=10.1), now=10.1)
    outbox.publish(result("NONE", "RAMUNE", observed_at=11.0), now=11.0)
    assert len(outbox.events(11.0)) == 1
    assert DeliveryOutbox().session_id != outbox.session_id


@pytest.mark.parametrize(
    "ack", [None, [], {}, {"event_id": []}, {"version": 1, "type": "ack", "status": []}]
)
def test_malformed_ack_does_not_crash(ack):
    assert not DeliveryOutbox().acknowledge(ack)
