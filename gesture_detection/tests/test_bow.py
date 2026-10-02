import numpy as np
import pytest

from gesture_detection.app import GestureApplication
from gesture_detection.bow import BowAnalyzer
from gesture_detection.recognition import RecognitionCoordinator
from gesture_detection.recognition_types import GestureSample
from gesture_detection.rendering import draw_bow_meter
from test_relaxing import body


def bent(angle=30):
    points = body()
    # With a 0.3-tall torso, this is roughly 30 degrees at aspect ratio 1.
    offset = 0.173 if angle == 30 else 0.08
    for index in (0, 11, 12, 13, 14, 15, 16):
        points[index].x += offset
    points[0].x += offset / 2
    return points


def test_held_waist_bow_takes_priority_over_stillness_and_releases():
    coordinator = RecognitionCoordinator()
    points = bent()
    result = coordinator.process(points, 0.0, 0, aspect_ratio=1.0)
    for frame in range(1, 32):
        result = coordinator.process(points, frame / 30, frame, aspect_ratio=1.0)
    assert result.get("current", {}).get("gesture") == "BOW"
    assert result.get("bow_state") and result["relaxing_state"]
    assert result.get("bow_angle") == pytest.approx(30, abs=1)
    assert result.get("bow_hold_seconds", 0) >= 0.25
    assert GestureApplication._primary_action(result) == "BOW"
    image = np.zeros((480, 640, 3), dtype=np.uint8)
    draw_bow_meter(image, result)
    assert image[240, 160].any()  # target angle band
    assert image[262, 160].any()  # held-time progress bar
    assert GestureSample.from_result(result, 2.0).gesture == "BOW"
    result = coordinator.process(body(), 32 / 30, 32, aspect_ratio=1.0)
    assert not result.get("bow_state")
    assert result.get("bow_hold_seconds") == 0
    assert result.get("bow_angle") == pytest.approx(0)
    assert result.get("current", {}).get("gesture") != "BOW"
    lost = coordinator.process([], 33 / 30, 33, aspect_ratio=1.0)
    assert not lost.get("bow_state")
    assert lost.get("bow_angle") is None


def test_nod_or_shallow_lean_is_not_a_bow():
    for points in (body(), bent(angle=15)):
        analyzer = BowAnalyzer()
        for frame in range(20):
            assert not analyzer.update(points, frame / 30, 1.0)
    points = bent()
    points[0].x -= 0.173 * 1.5
    analyzer = BowAnalyzer()
    for frame in range(20):
        assert not analyzer.update(points, frame / 30, 1.0)
    assert analyzer.torso_angle == pytest.approx(30, abs=1)
    assert not analyzer.head_aligned
    assert analyzer.hold_seconds == 0


def test_bow_requires_visible_torso_and_continuous_time():
    analyzer = BowAnalyzer()
    points = bent()
    for frame in range(10):
        analyzer.update(points, frame / 30, 1.0)
    assert analyzer.state
    assert not analyzer.update(points, 2.0, 1.0)
    assert not analyzer.update(points, 2.1, 1.0)
    points[23].visibility = 0.1
    assert not analyzer.update(points, 2.2, 1.0)
