import pickle

import pytest

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


def test_unknown_occurrence_is_rejected():
    with pytest.raises(ValueError, match="Unknown occurrence"):
        GestureSample.from_result(result(occurrences=("FANNING",)), observed_at=1.0)
