from unity_bridge.gesture_probe import GestureReceiver


def decision(receiver, message, now, accept):
    ack = receiver.receive(message, now, accept)
    assert ack is not None
    return ack["status"]


def event(session="one", event_id=1):
    return {
        "version": 1,
        "type": "event",
        "session_id": session,
        "event_id": event_id,
        "gesture": "RAMUNE",
        "occurred_at": 10.0,
        "expires_at": 11.0,
    }


def state(session="one", sequence=1):
    return {
        "version": 1,
        "type": "state",
        "session_id": session,
        "sequence": sequence,
        "gesture": "FANNING",
        "tracking": True,
        "fresh": True,
        "observed_at": 10.0,
        "stale_timeout": 0.5,
    }


def test_scene_decision_ack_and_duplicate_survive_reconnection():
    receiver = GestureReceiver()
    adopted = []

    def accept(kind):
        adopted.append(kind)
        return True

    assert decision(receiver, event(), 10.1, accept) == "accepted"
    receiver.disconnected()
    assert decision(receiver, event(), 10.2, accept) == "duplicate"
    assert adopted == ["RAMUNE"]
    assert decision(receiver, event(), 11.0, accept) == "expired"
    assert decision(receiver, event("new"), 10.3, accept) == "accepted"


def test_ignored_event_is_acknowledged_and_not_reconsidered():
    receiver = GestureReceiver()
    assert decision(receiver, event(), 10.1, lambda _: False) == "ignored"
    assert decision(receiver, event(), 10.2, lambda _: True) == "duplicate"


def test_state_ages_from_capture_time_and_clears_on_session_change():
    receiver = GestureReceiver()
    receiver.receive(state(), 10.4, lambda _: True)
    assert receiver.gesture == "FANNING"
    receiver.poll(10.5)
    assert receiver.gesture == "NONE"
    receiver.receive(state(sequence=2), 10.6, lambda _: True)
    assert receiver.gesture == "NONE"
    receiver.receive(event("two"), 10.7, lambda _: True)
    assert not receiver.fresh


def test_old_state_cannot_overwrite_newer_state():
    receiver = GestureReceiver()
    newer = state(sequence=2)
    newer["gesture"] = "RELAXING"
    receiver.receive(newer, 10.1, lambda _: True)
    receiver.receive(state(), 10.2, lambda _: True)
    assert receiver.gesture == "RELAXING"
