import pickle

import pytest

from gesture_detection.gesture_types import Gesture, Phase
from gesture_detection.recognition_types import GestureSample, PoseResult


def result(**extra) -> PoseResult:
    base: PoseResult = {"landmarks": [], "selected_action": "NONE", "relaxing_state": False}
    base.update(extra)  # type: ignore[typeddict-item]
    return base


def test_sample_keeps_only_delivered_gestures_and_occurrence_times():
    sample = GestureSample.from_result(
        result(
            current={"gesture": "UCHIMIZU", "tracking": True},
            occurrences=("RAMUNE", "UCHIMIZU"),
            occurrence_timestamps={"RAMUNE": 9.5},
            frame_id=7,
            timestamp=3.0,
        ),
        observed_at=10.0,
    )
    assert sample == GestureSample(
        "NONE", True, 10.0, (("RAMUNE", 9.5), ("UCHIMIZU", 10.0)), 7, 3.0
    )
    assert pickle.loads(pickle.dumps(sample)) == sample


def test_empty_result_is_not_tracking():
    sample = GestureSample.from_result(result(), observed_at=1.0)
    assert (sample.gesture, sample.tracking, sample.occurrences) == ("NONE", False, ())
    assert sample.frame_id is None


def test_ipc_sample_normalizes_strings_to_shared_enums():
    sample = GestureSample("NONE", True, 1.0, (("RAMUNE", 1.0),), action="RAMUNE", phase="READY")
    assert sample.gesture is Gesture.NONE
    assert sample.occurrences[0][0] is Gesture.RAMUNE
    assert sample.action is Gesture.RAMUNE
    assert sample.phase is Phase.READY
    restored = pickle.loads(pickle.dumps(sample))
    assert restored.action is Gesture.RAMUNE
    assert restored.phase is Phase.READY


def test_bow_is_delivered_as_continuous_state():
    sample = GestureSample.from_result(
        result(current={"gesture": "BOW", "tracking": True}), observed_at=1.0
    )
    assert sample.gesture == "BOW"


def test_unknown_occurrence_is_rejected():
    with pytest.raises(ValueError, match="Unknown occurrence"):
        GestureSample.from_result(result(occurrences=("FANNING",)), observed_at=1.0)


@pytest.mark.parametrize(
    "action,diagnostics,expected",
    [
        ("NONE", {"ramune_state": "FORMING"}, ("RAMUNE", "FORMING")),
        ("NONE", {"ramune_state": "READY"}, ("RAMUNE", "READY")),
        ("RAMUNE", {"ramune_state": "OPENED"}, ("RAMUNE", "OPENED")),
        ("NONE", {"ramune_state": "WAIT_RELEASE"}, ("RAMUNE", "WAIT_RELEASE")),
        ("NONE", {"uchimizu_state": "READY"}, ("UCHIMIZU", "READY")),
        ("UCHIMIZU", {"uchimizu_state": "SWING"}, ("UCHIMIZU", "SWING")),
        ("FANNING", {"ramune_state": "WAIT_RELEASE"}, ("FANNING", "ACTIVE")),
        ("RELAXING", {}, ("RELAXING", "ACTIVE")),
        ("RELAXING", {"ramune_state": "WAIT_RELEASE"}, ("RAMUNE", "WAIT_RELEASE")),
        ("BOW", {"ramune_state": "WAIT_RELEASE"}, ("BOW", "HOLD")),
        ("BOW", {}, ("BOW", "HOLD")),
        ("NONE", {"ramune_state": "IDLE", "uchimizu_state": "IDLE"}, (None, None)),
    ],
)
def test_sample_exposes_progress_without_turning_preparation_into_an_event(
    action, diagnostics, expected
):
    sample = GestureSample.from_result(
        result(current={"gesture": action, "tracking": True}, **diagnostics), 1.0
    )
    assert (sample.action, sample.phase) == expected
    assert sample.occurrences == ()
    assert pickle.loads(pickle.dumps(sample)) == sample


def test_no_tracking_discards_detector_progress():
    sample = GestureSample.from_result(
        result(current={"gesture": "NONE", "tracking": False}, ramune_state="READY"), 1.0
    )
    assert sample.action is None and sample.phase is None
