from dataclasses import dataclass

import pytest

from gesture_detection.subject_selection import SubjectSelector


@dataclass
class Point:
    x: float
    y: float
    visibility: float = 1.0


def pose(x=0.55, y=0.50, size=1.0):
    points = [Point(x=x, y=y, visibility=1.0) for _ in range(33)]
    for index, dx, dy in [(11, -0.1, -0.15), (12, 0.1, -0.15), (23, -0.07, 0.15), (24, 0.07, 0.15)]:
        points[index].x, points[index].y = x + dx * size, y + dy * size
    return points


def acquire(selector, points, start=0.0):
    assert selector.select([points], start, 1.0) == []
    return selector.select([points], start + 0.21, 1.0)


def test_rejects_background_even_when_only_person():
    selector = SubjectSelector()
    for t in [0.0, 0.3, 0.6, 0.9]:
        assert selector.select([pose(0.3, size=0.3), pose(0.55, size=0.3)], t, 1.0) == []


def test_selects_foreground_independent_of_result_order_and_keeps_arms():
    selector = SubjectSelector()
    person = pose()
    person[15].x = 0.05
    person[16].x = 0.95
    background = pose(0.3, size=0.3)
    assert selector.select([background, person], 0.0, 1.0) == []
    assert selector.select([person, background], 0.21, 1.0) is person
    assert selector.select([background, person], 0.24, 1.0) is person
    assert person[15].x == 0.05


def test_missing_person_never_outputs_cached_pose_or_background():
    selector = SubjectSelector()
    person = pose()
    assert acquire(selector, person) is person
    for t in [0.25, 0.5, 0.8, 1.0]:
        assert selector.select([pose(0.3, size=0.3)], t, 1.0) == []
    assert selector.state == "SEARCHING"
    assert acquire(selector, person, 1.1) is person


def test_reappearance_within_hold_matches_original_only():
    selector = SubjectSelector()
    person = pose(0.4, size=0.7)
    assert acquire(selector, person) is person
    stranger = pose(0.73, size=0.7)
    assert selector.select([stranger], 0.25, 1.0) == []
    assert selector.select([stranger, person], 0.3, 1.0) is person


def test_ambiguous_acquisition_and_crossing_abstain():
    selector = SubjectSelector()
    a, b = pose(0.5), pose(0.6)
    assert selector.select([a, b], 0.0, 1.0) == []
    assert acquire(selector, a, 0.1) is a
    assert selector.select([a, b], 0.4, 1.0) == []
    assert selector.state == "LOST"


def test_long_gap_and_time_reversal_require_new_acquisition():
    selector = SubjectSelector()
    person = pose()
    assert acquire(selector, person) is person
    assert selector.select([person], 1.0, 1.0) == []
    assert selector.select([person], 0.5, 1.0) == []
    assert selector.select([person], 0.71, 1.0) is person


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_torso_is_not_a_candidate(value):
    points = pose()
    points[11].x = value
    assert SubjectSelector.candidate(points, 1.0) is None


def test_visibility_loss_and_area_exit_drop_immediately():
    selector = SubjectSelector()
    person = pose()
    assert acquire(selector, person) is person
    person[11].visibility = 0.2
    assert selector.select([person], 0.25, 1.0) == []
    assert selector.select([pose(0.9)], 0.3, 1.0) == []


def test_moving_candidate_must_be_continuous_during_acquisition():
    selector = SubjectSelector()
    assert selector.select([pose(0.4, size=0.7)], 0.0, 1.0) == []
    assert selector.select([pose(0.73, size=0.7)], 0.21, 1.0) == []
    assert selector.state == "ACQUIRING"


def test_nonfinite_visibility_is_rejected():
    points = pose()
    points[11].visibility = float("nan")
    assert SubjectSelector.candidate(points, 1.0) is None
