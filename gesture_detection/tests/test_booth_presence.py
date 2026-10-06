from dataclasses import dataclass

import pytest

from gesture_detection.booth_presence import BoothPresence


@dataclass
class Point:
    x: float
    y: float
    visibility: float = 1.0


def pose(x: float = 0.55, size: float = 1.0) -> list[Point]:
    points = [Point(x, 0.5) for _ in range(33)]
    for index, dx, dy in ((11, -0.1, -0.15), (12, 0.1, -0.15), (23, -0.07, 0.15), (24, 0.07, 0.15)):
        points[index] = Point(x + dx * size, 0.5 + dy * size)
    return points


def arrive(detector: BoothPresence) -> None:
    for t in (0.0, 0.25, 0.5, 0.75):
        assert not detector.update(pose(), t, 1.0)
    assert detector.update(pose(), 1.0, 1.0)


def test_continuous_dwell_and_departure_then_rearrival():
    detector = BoothPresence()
    arrive(detector)
    assert detector.update([], 1.25, 1.0)
    assert detector.update(pose(), 1.4, 1.0)
    assert detector.update([], 1.65, 1.0)
    assert not detector.update([], 1.9, 1.0)
    for t in (2.0, 2.25, 2.5, 2.75):
        assert not detector.update(pose(), t, 1.0)
    assert detector.update(pose(), 3.0, 1.0)


@pytest.mark.parametrize("points", [[], pose(0.9), pose(size=0.3)])
def test_missing_outside_roi_and_background_do_not_accumulate_dwell(points):
    detector = BoothPresence()
    assert not detector.update(pose(), 0.0, 1.0)
    assert not detector.update(pose(), 0.4, 1.0)
    assert not detector.update(points, 0.5, 1.0)
    for t in (0.6, 1.0, 1.4):
        assert not detector.update(pose(), t, 1.0)
    assert detector.update(pose(), 1.6, 1.0)


def test_person_switch_does_not_combine_dwell():
    detector = BoothPresence()
    for t in (0.0, 0.4, 0.8):
        assert not detector.update(pose(0.4, 0.7), t, 1.0)
    assert not detector.update(pose(0.73, 0.7), 1.0, 1.0)
    assert not detector.update(pose(0.73, 0.7), 1.4, 1.0)
    assert not detector.update(pose(0.73, 0.7), 1.8, 1.0)
    assert detector.update(pose(0.73, 0.7), 2.0, 1.0)


def test_long_gap_and_clock_reset_require_new_dwell():
    detector = BoothPresence()
    arrive(detector)
    assert not detector.update(pose(), 2.0, 1.0)
    assert not detector.update(pose(), 0.0, 1.0)


def test_short_release_duration_does_not_reset_continuously_visible_person():
    detector = BoothPresence(release_seconds=0.1)
    arrive(detector)
    assert not detector.update([], 1.25, 1.0)


@pytest.mark.parametrize("duration", [0, -1, float("nan"), float("inf")])
def test_invalid_durations(duration):
    with pytest.raises(ValueError):
        BoothPresence(dwell_seconds=duration)
    with pytest.raises(ValueError):
        BoothPresence(release_seconds=duration)
