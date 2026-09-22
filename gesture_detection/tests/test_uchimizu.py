from dataclasses import dataclass

import pytest

from gesture_detection.uchimizu import UchimizuAnalyzer


@dataclass
class Point:
    x: float = 0.5
    y: float = 0.5
    visibility: float = 1.0


def points(height: float, x: float = 0.5, scale: float = 1.0) -> list[Point]:
    result = [Point() for _ in range(33)]
    for index, px, py in (
        (0, 0.5, 0.2),
        (11, 0.4, 0.4),
        (12, 0.6, 0.4),
        (23, 0.43, 0.7),
        (24, 0.57, 0.7),
        (15, x, height),
        (16, x, height),
    ):
        result[index].x = 0.1 + px * scale
        result[index].y = 0.1 + py * scale
    return result


@pytest.mark.parametrize("wrist", [15, 16])
@pytest.mark.parametrize("fps", [10, 30, 60])
@pytest.mark.parametrize("scale", [0.5, 1.0, 1.5])
def test_scoop_pause_and_outward_release(wrist, fps, scale):
    detector = UchimizuAnalyzer(wrist)
    detected = []
    for frame in range(int(1.5 * fps)):
        now = frame / fps
        if now < 0.3:
            y = 0.75 - 0.2 * now / 0.3
        elif now < 0.6:
            y = 0.55
        elif now < 0.9:
            y = 0.55 + 0.2 * (now - 0.6) / 0.3
        else:
            y = 0.75
        detected.append(detector.update(points(y, 0.75 if now >= 0.6 else 0.5, scale), now))
    assert not any(detected[: int(0.6 * fps)])
    assert any(detected)
    assert not detected[-1]


@pytest.mark.parametrize(
    "trajectory",
    [
        [0.75, 0.7, 0.65, 0.6, 0.55],  # Raising alone.
        [0.55, 0.6, 0.65, 0.7, 0.75],  # Lowering without scooping.
        [0.50, 0.46, 0.42, 0.46, 0.50] * 8,  # Chest-level fanning.
        [0.25, 0.21, 0.17, 0.21, 0.25] * 8,  # Face-level fanning.
        [0.75, 0.74, 0.75, 0.76] * 8,  # Low wrist jitter.
    ],
)
def test_incomplete_or_fanning_motion_is_not_sprinkling(trajectory):
    detector = UchimizuAnalyzer(16)
    assert not any(detector.update(points(y), i / 30) for i, y in enumerate(trajectory))


def test_expired_preparation_does_not_accept_late_drop():
    detector = UchimizuAnalyzer(16)
    for now, y in [(0.0, 0.75), (0.2, 0.55), (0.7, 0.55), (1.3, 0.55), (1.8, 0.55), (1.9, 0.75)]:
        assert not detector.update(points(y), now)


@pytest.mark.parametrize("missing_index", [0, 11, 12, 23, 24, 16])
def test_tracking_loss_cancels_preparation(missing_index):
    detector = UchimizuAnalyzer(16)
    detector.update(points(0.75), 0.0)
    detector.update(points(0.55), 0.2)
    hidden = points(0.55)
    hidden[missing_index].visibility = 0
    assert not detector.update(hidden, 0.3)
    assert not detector.update(points(0.75), 0.4)


def test_whole_body_translation_is_not_a_scoop():
    detector = UchimizuAnalyzer(16)
    for i, offset in enumerate([0, -0.1, -0.2, -0.1, 0]):
        landmarks = points(0.75)
        for point in landmarks:
            point.y += offset
        assert not detector.update(landmarks, i / 10)


def test_new_scoop_required_after_completion():
    detector = UchimizuAnalyzer(16)
    detector.update(points(0.75), 0.0)
    detector.update(points(0.55), 0.2)
    assert detector.update(points(0.75), 0.4)
    assert detector.update(points(0.75), 0.5)
    for now in (0.8, 1.1, 1.3):
        assert not detector.update(points(0.75), now)
    assert not detector.update(points(0.55), 1.5)
    assert detector.update(points(0.75), 1.7)


@pytest.mark.parametrize("now", [0.1, 1.2])
def test_clock_reversal_or_long_gap_cancels_preparation(now):
    detector = UchimizuAnalyzer(16)
    detector.update(points(0.75), 0.0)
    detector.update(points(0.55), 0.2)
    assert not detector.update(points(0.75), now)


def test_scooping_outside_torso_does_not_prepare():
    detector = UchimizuAnalyzer(16)
    for now, y in [(0.0, 0.75), (0.2, 0.55), (0.4, 0.75)]:
        assert not detector.update(points(y, x=0.8), now)


def test_entering_face_area_cancels_preparation():
    detector = UchimizuAnalyzer(16)
    for now, y in [(0.0, 0.75), (0.2, 0.55), (0.3, 0.25), (0.4, 0.75)]:
        assert not detector.update(points(y), now)


@pytest.mark.parametrize("wrist", [15, 16])
@pytest.mark.parametrize("scale", [0.5, 1.0, 1.5])
def test_small_scoop_near_torso_edge_and_shallow_release(wrist, scale):
    detector = UchimizuAnalyzer(wrist)
    assert not detector.update(points(0.57, x=0.63, scale=scale), 0.0)
    assert not detector.update(points(0.535, x=0.63, scale=scale), 0.4)
    assert detector.state == "READY"
    assert detector.update(points(0.585, x=0.70, scale=scale), 0.7)
    assert detector.state == "SWING"


def test_release_window_follows_end_of_slow_raise():
    detector = UchimizuAnalyzer(16)
    for now, y in [(0.0, 0.7), (0.4, 0.66), (0.8, 0.62), (1.2, 0.58), (1.6, 0.54), (2.0, 0.54)]:
        assert not detector.update(points(y), now)
    assert detector.update(points(0.60), 2.3)
