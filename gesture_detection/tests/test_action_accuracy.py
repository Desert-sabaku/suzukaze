import math

import pytest

from gesture_detection.action_accuracy import bow_accuracy, fanning_accuracy, relaxing_accuracy
from gesture_detection.multicam_fusion import MultiCameraFusion
from gesture_detection.ramune import RamuneAnalyzer
from gesture_detection.recognition import RecognitionCoordinator
from gesture_detection.recognition_types import GestureSample
from gesture_detection.uchimizu import UchimizuAnalyzer
from test_multicam_runtime import sample
from test_ramune import points as ramune_points
from test_ramune import prepare
from test_uchimizu import points as water_points


def test_bow_and_stillness_measured_criteria():
    assert bow_accuracy(20, 35, True, 0.25) == 1
    assert bow_accuracy(75, 0, True, 1) == 1
    assert bow_accuracy(10, 0, True, 0.125) == 0.75
    assert bow_accuracy(None, 0, True, 1) is None
    assert bow_accuracy(float("nan"), 0, True, 1) is None
    assert relaxing_accuracy(0.4, 0.055, 1) == 1
    assert relaxing_accuracy(0.8, 0.11, 0) == 0
    assert relaxing_accuracy(None, 0, 1) is None


def test_fanning_scores_trajectory_not_classifier_confidence():
    history = [(i / 60, 0.2 + 0.1 * math.sin(4 * math.pi * i / 60)) for i in range(61)]
    assert fanning_accuracy(history) == 1
    low = [(t, h + 0.6) for t, h in history]
    assert fanning_accuracy(low) == 0.75
    assert fanning_accuracy(history[:10]) is None
    assert fanning_accuracy(history[:10] + history[40:]) is None
    assert fanning_accuracy([(0, 0), (0.5, math.nan), (1, 0)]) is None


def test_event_scores_require_preparation_and_reset_on_loss():
    ramune = RamuneAnalyzer()
    points = ramune_points()
    assert ramune.action_accuracy is None
    prepare(ramune, points)
    assert ramune.action_accuracy is None
    points[16].y = 0.61
    assert ramune.update(points, 0.4)
    assert ramune.action_accuracy == 1
    ramune.update([], 0.5)
    assert ramune.action_accuracy is None
    water = UchimizuAnalyzer(16)
    water.update(water_points(0.75), 0)
    water.update(water_points(0.55), 0.2)
    assert water.action_accuracy is None
    assert water.update(water_points(0.75), 0.4)
    assert water.action_accuracy == 1
    water.reset()
    assert water.action_accuracy is None


def test_recognition_event_score_reaches_sample_only_on_pulse():
    coordinator = RecognitionCoordinator(ramune_detector="rules")
    points = ramune_points()
    for frame, now in enumerate((0, 0.1, 0.3, 0.4, 0.5)):
        if now >= 0.4:
            points[16].y = 0.61
        result = coordinator.process(points, now, frame, aspect_ratio=1)
        output = GestureSample.from_result(result, now)
        assert output.action_accuracy is None
        assert output.occurrence_accuracies == ((1.0,) if now == 0.4 else ())


def test_fusion_keeps_score_with_selected_observation_and_original_event():
    fusion = MultiCameraFusion()
    first, second = sample(1, "BOW"), sample(1.1, "BOW")
    first["action_accuracy"], second["action_accuracy"] = 0.9, 0.0
    fusion.submit(0, first)
    fusion.submit(1, second)
    assert GestureSample.from_result(fusion.advance(1.1), 1.1).action_accuracy == 0
    event = sample(1.2, "RAMUNE", pulse=True)
    event["occurrence_accuracies"] = {"RAMUNE": 0.0}
    duplicate = sample(1.21, "RAMUNE", pulse=True)
    duplicate["occurrence_accuracies"] = {"RAMUNE": 1.0}
    fusion.submit(0, event)
    fusion.submit(1, duplicate)
    output = GestureSample.from_result(fusion.advance(1.21), 1.21)
    assert output.action_accuracy is None
    assert output.occurrence_accuracies == (0.0,)
    assert GestureSample.from_result(fusion.advance(2), 2).action_accuracy is None


@pytest.mark.parametrize("value", [True, -0.1, 1.1, math.nan, math.inf])
def test_sample_rejects_invalid_scores(value):
    with pytest.raises(ValueError):
        GestureSample("BOW", True, 1, (), action_accuracy=value)
    with pytest.raises(ValueError):
        GestureSample("NONE", True, 1, (("RAMUNE", 1),), occurrence_accuracies=(value,))


def test_sample_requires_score_alignment_and_tracked_state():
    with pytest.raises(ValueError):
        GestureSample("BOW", True, 1, (), occurrence_accuracies=(0.5,))
    with pytest.raises(ValueError):
        GestureSample("NONE", True, 1, (), action_accuracy=0)
    with pytest.raises(ValueError):
        GestureSample("BOW", False, 1, (), action_accuracy=0)
