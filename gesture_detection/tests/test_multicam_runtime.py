from dataclasses import dataclass

import pytest

from gesture_detection.event_rearm import EventRearmGate
from gesture_detection.multicam_fusion import MultiCameraFusion
from gesture_detection.ramune import FollowingRamuneAnalyzer
from gesture_detection.recognition import RecognitionCoordinator
from gesture_detection.recognition_types import GestureSample, Landmark, PoseResult
from gesture_detection.uchimizu import AnchoredUchimizuAnalyzer


@dataclass
class Point:
    x: float = 0.5
    y: float = 0.5
    visibility: float = 1.0


def points(height: float = 0.5) -> list[Landmark]:
    result = [(0.5, 0.5, 1.0)] * 33
    for i, x, y in (
        (0, 0.5, 0.1),
        (11, 0.4, 0.4),
        (12, 0.6, 0.4),
        (23, 0.43, 0.7),
        (24, 0.57, 0.7),
        (15, 0.5, height),
        (16, 0.5, height),
    ):
        result[i] = x, y, 1.0
    return result


def sample(
    t: float, gesture: str = "NONE", *, pulse: bool = False, height: float = 0.5, setup: float = 0.0
) -> PoseResult:
    return {
        "landmarks": points(height),
        "current": {"gesture": gesture, "tracking": True},
        "selected_action": gesture,
        "relaxing_state": gesture == "RELAXING",
        "timestamp": t,
        "frame_id": round(t * 1000),
        "occurrences": (gesture,) if pulse else (),
        "occurrence_evidence": {gesture: {"wrist_index": 16, "setup_timestamp": setup}}
        if pulse
        else {},
    }


def test_multicam_profile_survives_tracking_resets():
    coordinator = RecognitionCoordinator(ramune_detector="rules", profile="multicam")
    assert isinstance(coordinator.ramune, FollowingRamuneAnalyzer)
    for t in (0.0, 0.1):
        coordinator.process([], t, round(t * 10), aspect_ratio=1.0)
        assert all(
            isinstance(hand.uchimizu, AnchoredUchimizuAnalyzer) for hand in coordinator.hands
        )


def test_booth_presence_uses_only_fresh_first_camera_and_reaches_ipc():
    fusion = MultiCameraFusion()
    second = sample(1.0)
    second["booth_present"] = True
    fusion.submit(1, second)
    assert fusion.advance(1.0).get("booth_present") is False
    first = sample(1.1)
    first["booth_present"] = True
    fusion.submit(0, first)
    result = fusion.advance(1.1)
    assert GestureSample.from_result(result, 1.1).booth_present
    fusion.submit(1, sample(1.4))
    assert fusion.advance(1.4).get("booth_present") is False


@pytest.mark.parametrize("profile, detector", [("bad", "rules"), ("multicam", "learned")])
def test_incompatible_profiles_are_rejected(profile, detector):
    with pytest.raises(ValueError, match="multicam"):
        RecognitionCoordinator(profile=profile, ramune_detector=detector)


@pytest.mark.parametrize("fps", [10, 30])
def test_profile_emits_scoop_evidence_at_both_camera_rates(fps):
    detector = AnchoredUchimizuAnalyzer(16)
    events = []
    for i in range(int(1.2 * fps)):
        now = i / fps
        height = (
            0.75 - 0.2 * min(now / 0.3, 1) if now < 0.6 else 0.55 + 0.2 * min((now - 0.6) / 0.3, 1)
        )
        before = detector.completed_at
        result = detector.update([Point(*p) for p in points(height)], now)
        if result and detector.completed_at != before:
            assert detector.setup_started_at is not None
            assert detector.setup_started_at < now
            events.append(now)
    assert len(events) == 1


def current_gesture(result: PoseResult) -> str:
    assert "current" in result
    return result["current"]["gesture"]


def test_two_camera_pulses_are_merged_and_keep_capture_time():
    fusion = MultiCameraFusion()
    fusion.submit(1, sample(0.2, "UCHIMIZU", pulse=True))
    fusion.submit(0, sample(0.3, "UCHIMIZU", pulse=True))
    result = fusion.advance(0.3)
    assert result.get("occurrences") == ("UCHIMIZU",)
    assert result.get("occurrence_timestamps") == {"UCHIMIZU": 0.2}
    assert GestureSample.from_result(result, 0.3).occurrences == (("UCHIMIZU", 0.2),)


def test_fusion_keeps_preparation_phase_and_expires_it():
    fusion = MultiCameraFusion(max_age=0.5)
    ready = sample(0.1)
    ready["ramune_state"] = "READY"
    fusion.submit(0, ready)
    fusion.submit(1, sample(0.2))
    delivered = GestureSample.from_result(fusion.advance(0.2), 0.2)
    assert delivered.gesture == "NONE"
    assert (delivered.action, delivered.phase) == ("RAMUNE", "READY")
    stale = GestureSample.from_result(fusion.advance(0.8), 0.8)
    assert (stale.action, stale.phase) == (None, None)


def test_fusion_phase_does_not_alternate_between_camera_progress():
    fusion = MultiCameraFusion()
    phases = []
    for tick, (ready_time, forming_time) in enumerate([(0.10, 0.12), (0.14, 0.13)]):
        ready, forming = sample(ready_time), sample(forming_time)
        ready["ramune_state"], forming["ramune_state"] = "READY", "FORMING"
        fusion.submit(0, ready)
        fusion.submit(1, forming)
        phases.append(fusion.advance(0.15 + tick * 0.01).get("phase"))
    assert phases == ["READY", "READY"]


def test_ramune_preparation_in_one_view_suppresses_fanning_in_the_other():
    fusion = MultiCameraFusion()
    ready = sample(0.1)
    ready["ramune_state"] = "READY"
    fusion.submit(0, ready)
    fusion.submit(1, sample(0.12, "FANNING"))
    result = fusion.advance(0.15)
    assert current_gesture(result) == "NONE"
    assert (result.get("action"), result.get("phase")) == ("RAMUNE", "READY")
    fusion.submit(0, sample(0.2))
    fusion.submit(1, sample(0.22, "FANNING"))
    assert current_gesture(fusion.advance(0.25)) == "FANNING"


def test_stillness_in_the_other_view_does_not_take_the_ramune_action():
    fusion = MultiCameraFusion()
    released = sample(0.1)
    released["ramune_state"] = "WAIT_RELEASE"
    fusion.submit(0, released)
    fusion.submit(1, sample(0.12, "RELAXING"))
    result = fusion.advance(0.15)
    assert current_gesture(result) == "RELAXING"
    assert (result.get("action"), result.get("phase")) == ("RAMUNE", "WAIT_RELEASE")


def test_fusion_prefers_phase_from_camera_with_selected_action():
    fusion = MultiCameraFusion()
    released = sample(0.2)
    released["ramune_state"] = "WAIT_RELEASE"
    fusion.submit(0, released)
    fusion.submit(1, sample(0.1, "FANNING"))
    delivered = GestureSample.from_result(fusion.advance(0.2), 0.2)
    assert (delivered.action, delivered.phase) == ("FANNING", "ACTIVE")


def test_late_event_is_not_renewed_by_a_newer_other_camera_frame():
    fusion = MultiCameraFusion(event_ttl=1.0)
    fusion.submit(0, sample(0.2, "RAMUNE", pulse=True))
    fusion.submit(1, sample(1.4, "FANNING"))
    result = fusion.advance(1.4)
    assert result.get("occurrences") == ()
    assert current_gesture(result) == "FANNING"
    result["occurrences"] = ("RAMUNE",)
    result["occurrence_timestamps"] = {"RAMUNE": 0.2}
    # The original occurrence time is kept, so unity_bridge treats it as expired.
    assert GestureSample.from_result(result, 1.4).occurrences == (("RAMUNE", 0.2),)


def test_release_from_other_view_requires_a_fresh_setup():
    fusion = MultiCameraFusion()
    fusion.submit(1, sample(0.5, "UCHIMIZU", pulse=True))
    assert fusion.advance(0.5).get("occurrences") == ("UCHIMIZU",)
    for t in (1.0, 1.1, 1.2, 1.3):
        fusion.submit(0, sample(t, height=0.75))
        fusion.advance(t)
    fusion.submit(1, sample(1.4, "UCHIMIZU", pulse=True, setup=0.1))
    assert fusion.advance(1.4).get("occurrences") == ()
    fusion.submit(1, sample(2.1, "UCHIMIZU", pulse=True, setup=1.7))
    assert fusion.advance(2.1).get("occurrences") == ("UCHIMIZU",)


def test_missing_input_cannot_rearm_and_stale_poses_do_not_track():
    fusion = MultiCameraFusion()
    fusion.submit(0, sample(0.1, "RAMUNE", pulse=True))
    fusion.advance(0.1)
    missing = fusion.advance(1.5)
    assert missing.get("current") == {"gesture": "NONE", "tracking": False}
    fusion.submit(1, sample(1.6, "RAMUNE", pulse=True, setup=1.2))
    assert fusion.advance(1.6).get("occurrences") == ()


@pytest.mark.parametrize("gesture", ["FANNING", "RELAXING", "BOW"])
def test_state_gestures_can_reappear(gesture):
    fusion = MultiCameraFusion()
    for t, label in ((0.0, gesture), (0.1, "NONE"), (0.2, gesture)):
        fusion.submit(0, sample(t, label))
        assert current_gesture(fusion.advance(t)) == label


def test_future_observation_is_not_used_early():
    fusion = MultiCameraFusion()
    fusion.submit(0, sample(0.2, "FANNING"))
    assert current_gesture(fusion.advance(0.1)) == "NONE"
    assert current_gesture(fusion.advance(0.2)) == "FANNING"
    with pytest.raises(ValueError, match="increase"):
        fusion.advance(0.2)


def test_camera_order_is_validated_and_capacity_does_not_drop_events():
    fusion = MultiCameraFusion(max_pending=1)
    fusion.submit(0, sample(0.2))
    with pytest.raises(ValueError, match="increase"):
        fusion.submit(0, sample(0.2))
    with pytest.raises(RuntimeError, match="capacity"):
        fusion.submit(1, sample(0.3))


def test_large_backlog_cannot_silently_discard_distinct_events():
    fusion = MultiCameraFusion()
    fusion.submit(0, sample(0.1, "UCHIMIZU", pulse=True))
    fusion.submit(0, sample(0.8, "UCHIMIZU", pulse=True, setup=0.6))
    with pytest.raises(RuntimeError, match="Multiple distinct events"):
        fusion.advance(0.8)


def test_invalid_evidence_and_nonfinite_release_are_not_accepted():
    gate = EventRearmGate()
    with pytest.raises(ValueError, match="evidence"):
        gate.update(
            "RAMUNE",
            ("RAMUNE",),
            0.5,
            [points()],
            {"RAMUNE": {"wrist_index": 16, "setup_timestamp": 1.0}},
        )
    fusion = MultiCameraFusion()
    result = sample(0.1)
    result["timestamp"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        fusion.submit(0, result)


@pytest.mark.parametrize("common_descent", [False, True])
def test_production_ramune_tracks_raise_but_rejects_common_descent(common_descent):
    detector = FollowingRamuneAnalyzer()

    def pose(upper, lower):
        frame = [Point(*p) for p in points()]
        frame[15].y, frame[16].y = upper, lower
        return frame

    for i in range(4):
        assert not detector.update(pose(0.45, 0.55), i / 10)
    assert detector.state == "READY"
    assert not detector.update(pose(0.40, 0.55), 0.4)
    assert detector.upper_y == 0.40
    assert detector.update(pose(0.45, 0.60) if common_descent else pose(0.53, 0.55), 0.7) == (
        not common_descent
    )


def test_nonfinite_visibility_cannot_release_an_event():
    gate = EventRearmGate()
    gate.update(
        "UCHIMIZU",
        ("UCHIMIZU",),
        0.5,
        [points()],
        {"UCHIMIZU": {"wrist_index": 16, "setup_timestamp": 0.0}},
    )
    bad = points(0.75)
    bad[16] = (0.5, 0.75, float("nan"))
    for t in (1.0, 1.1, 1.2, 1.3):
        gate.update("NONE", (), t, [bad], {})
    assert gate.release_pending == ("UCHIMIZU",)
