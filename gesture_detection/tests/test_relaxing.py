from dataclasses import dataclass

import pytest
from modules.config import RELAXING_DWELL_SECONDS, RELAXING_LANDMARKS
from modules.relaxing import RelaxingAnalyzer


@dataclass
class Landmark:
    x: float
    y: float
    visibility: float = 1.0


def body():
    points = [Landmark(x=0.5, y=0.5) for _ in range(33)]
    for index, x, y in (
        (0, 0.5, 0.15),
        (11, 0.4, 0.3),
        (12, 0.6, 0.3),
        (13, 0.35, 0.45),
        (14, 0.65, 0.45),
        (15, 0.35, 0.6),
        (16, 0.65, 0.6),
        (23, 0.43, 0.6),
        (24, 0.57, 0.6),
        (25, 0.43, 0.75),
        (26, 0.57, 0.75),
        (27, 0.43, 0.9),
        (28, 0.57, 0.9),
        (29, 0.43, 0.92),
        (30, 0.57, 0.92),
        (31, 0.4, 0.94),
        (32, 0.6, 0.94),
    ):
        points[index].x, points[index].y = x, y
    return points


def establish_stillness(analyzer, points, fps=30):
    now = 0.0
    for frame_id in range(int(RELAXING_DWELL_SECONDS * fps) + 2):
        now = frame_id / fps
        analyzer.update(points, now, 1.0)
    assert analyzer.state
    return now


@pytest.mark.parametrize("fps", [15, 30, 60])
def test_stillness_uses_source_seconds(fps):
    analyzer = RelaxingAnalyzer()
    points = body()
    for frame_id in range(int(RELAXING_DWELL_SECONDS * fps)):
        assert not analyzer.update(points, frame_id / fps, 1.0)
    assert analyzer.update(points, RELAXING_DWELL_SECONDS, 1.0)


@pytest.mark.parametrize("index", RELAXING_LANDMARKS)
def test_any_major_body_part_moving_clears_immediately(index):
    analyzer = RelaxingAnalyzer()
    points = body()
    now = establish_stillness(analyzer, points)
    points[index].x += 0.02
    assert not analyzer.update(points, now + 1 / 30, 1.0)
    assert analyzer.still_seconds == 0


@pytest.mark.parametrize("fps", [15, 30, 60])
def test_slow_whole_body_drift_never_qualifies_as_still(fps):
    analyzer = RelaxingAnalyzer()
    for frame_id in range(fps * 3):
        points = body()
        for point in points:
            point.x += 0.018 * frame_id / fps
        assert not analyzer.update(points, frame_id / fps, 1.0)


def test_whole_body_translation_and_approach_clear_immediately():
    for movement in ("translation", "scale"):
        analyzer = RelaxingAnalyzer()
        points = body()
        now = establish_stillness(analyzer, points)
        for point in points:
            if movement == "translation":
                point.x += 0.02
                point.y += 0.02
            else:
                point.x = 0.5 + (point.x - 0.5) * 1.05
                point.y = 0.5 + (point.y - 0.5) * 1.05
        assert not analyzer.update(points, now + 1 / 30, 1.0)


def test_small_landmark_jitter_is_tolerated():
    analyzer = RelaxingAnalyzer()
    for frame_id in range(61):
        points = body()
        for point in points:
            point.x += 0.0002 * (-1 if frame_id % 2 else 1)
        analyzer.update(points, frame_id / 30, 1.0)
    assert analyzer.state


def test_movement_requires_a_new_full_stillness_period():
    analyzer = RelaxingAnalyzer()
    points = body()
    now = establish_stillness(analyzer, points) + 1 / 30
    points[23].x += 0.02
    assert not analyzer.update(points, now, 1.0)
    for frame_id in range(1, 30):
        assert not analyzer.update(points, now + frame_id / 30, 1.0)
    assert analyzer.update(points, now + 1.01, 1.0)


@pytest.mark.parametrize("index", [11, 23, 25, 27])
def test_losing_tracked_body_parts_clears_immediately(index):
    analyzer = RelaxingAnalyzer()
    points = body()
    now = establish_stillness(analyzer, points)
    points[index].visibility = 0.1
    assert not analyzer.update(points, now + 1 / 30, 1.0)


def test_visible_upper_body_can_be_still_when_feet_are_out_of_frame():
    analyzer = RelaxingAnalyzer()
    points = body()
    for index in range(25, 33):
        points[index].y = 1.1
    establish_stillness(analyzer, points)


@pytest.mark.parametrize("next_time", [0.5, 1.0333333333333334, 2.0, float("nan")])
def test_time_discontinuity_clears_state(next_time):
    analyzer = RelaxingAnalyzer()
    points = body()
    establish_stillness(analyzer, points)
    assert not analyzer.update(points, next_time, 1.0)


def test_horizontal_and_vertical_speeds_use_same_pixel_units():
    speeds = []
    for axis in ("x", "y"):
        analyzer = RelaxingAnalyzer()
        points = body()
        analyzer.update(points, 0.0, 2.0)
        setattr(points[15], axis, getattr(points[15], axis) + (0.005 if axis == "x" else 0.01))
        analyzer.update(points, 1 / 30, 2.0)
        speeds.append(analyzer.motion_speed)
    assert speeds[0] == pytest.approx(speeds[1])
