from dataclasses import dataclass

import pytest
from modules.ramune import RamuneAnalyzer


@dataclass
class Point:
    x: float = 0.5
    y: float = 0.5
    visibility: float = 1.0


def points(base_index=15):
    result = [Point() for _ in range(33)]
    result[11].x, result[12].x = 0.3, 0.7
    result[11].y = result[12].y = 0.3
    result[23].y = result[24].y = 0.85
    result[base_index].y = 0.65
    result[31 - base_index].y = 0.45
    return result


def prepare(analyzer, landmarks):
    for now in (0.0, 0.1, 0.3):
        assert not analyzer.update(landmarks, now)
    assert analyzer.state == "READY"


@pytest.mark.parametrize("base_index", [15, 16])
def test_press_with_either_hand_and_require_release(base_index):
    analyzer = RamuneAnalyzer()
    landmarks = points(base_index)
    prepare(analyzer, landmarks)
    landmarks[31 - base_index].y = 0.61
    assert analyzer.update(landmarks, 0.4)
    for now in (0.7, 1.0):
        assert analyzer.update(landmarks, now)
    for now in (1.3, 1.6):
        assert not analyzer.update(landmarks, now)
    landmarks[31 - base_index].y = 0.45
    for now in (1.7, 1.8, 2.1):
        assert not analyzer.update(landmarks, now)
    landmarks[31 - base_index].y = 0.61
    assert analyzer.update(landmarks, 2.2)


@pytest.mark.parametrize("failure", ["both_down", "sideways", "lost", "gap", "up", "timeout"])
def test_invalid_press(failure):
    analyzer = RamuneAnalyzer()
    landmarks = points()
    prepare(analyzer, landmarks)
    now = 0.4
    landmarks[16].y = 0.61
    if failure == "both_down":
        landmarks[15].y += 0.16
    elif failure == "sideways":
        landmarks[16].x += 0.3
    elif failure == "lost":
        landmarks[15].visibility = 0.0
    elif failure == "gap":
        now = 1.0
    elif failure == "up":
        landmarks[16].y = 0.3
    elif failure == "timeout":
        landmarks[16].y = 0.45
        for t in (0.7, 1.1, 1.5, 1.9):
            assert not analyzer.update(landmarks, t)
        landmarks[16].y = 0.61
        now = 2.0
    assert not analyzer.update(landmarks, now)
    assert analyzer.state == "IDLE"


def test_contact_without_preparation_does_not_open():
    analyzer = RamuneAnalyzer()
    landmarks = points()
    landmarks[16].y = 0.64
    for now in (0.0, 0.1, 0.4):
        assert not analyzer.update(landmarks, now)


def test_press_before_dwell_does_not_open():
    analyzer = RamuneAnalyzer()
    landmarks = points()
    analyzer.update(landmarks, 0.0)
    landmarks[16].y = 0.61
    assert not analyzer.update(landmarks, 0.1)


def test_missing_pose_resets_preparation():
    analyzer = RamuneAnalyzer()
    prepare(analyzer, points())
    assert not analyzer.update([], 0.4)
    assert analyzer.state == "IDLE"


@pytest.mark.parametrize("base_index", [15, 16])
@pytest.mark.parametrize("drift_during_preparation", [False, True])
def test_hand_landmark_drift_and_offset_contact_are_allowed(base_index, drift_during_preparation):
    analyzer = RamuneAnalyzer()
    landmarks = points(base_index)
    upper_index = 31 - base_index
    assert not analyzer.update(landmarks, 0.0)
    if drift_during_preparation:
        landmarks[base_index].x += 0.14
        landmarks[base_index].y += 0.08
        landmarks[upper_index].x -= 0.04
    for now in (0.1, 0.3):
        assert not analyzer.update(landmarks, now)
    assert analyzer.state == "READY"
    landmarks[base_index].x = 0.64
    landmarks[base_index].y = 0.73
    landmarks[upper_index].x = 0.46
    # Hands need not coincide: the final vertical offset is 0.25 shoulder widths.
    landmarks[upper_index].y = 0.63 if drift_during_preparation else 0.66
    assert analyzer.update(landmarks, 0.4)


@pytest.mark.parametrize("base_index", [15, 16])
def test_nearly_shared_downward_motion_does_not_count_as_press(base_index):
    analyzer = RamuneAnalyzer()
    landmarks = points(base_index)
    upper_index = 31 - base_index
    landmarks[upper_index].y = 0.526
    prepare(analyzer, landmarks)
    # Both move within the relaxed base tolerance and finish near each other.
    # The upper hand descends far enough, but hardly closes the relative gap.
    landmarks[base_index].y += 0.104
    landmarks[upper_index].y += 0.124
    assert not analyzer.update(landmarks, 0.4)
    assert analyzer.state == "READY"


def test_lower_hand_rising_without_upper_hand_press_does_not_open():
    analyzer = RamuneAnalyzer()
    landmarks = points()
    prepare(analyzer, landmarks)
    landmarks[15].y -= 0.11
    assert not analyzer.update(landmarks, 0.4)
    assert analyzer.state == "READY"
