from dataclasses import dataclass

from gesture_detection.pose_landmarks import (
    LANDMARK_COUNT,
    LEFT_HIP,
    LEFT_SHOULDER,
    LEFT_WRIST,
    RIGHT_HIP,
    RIGHT_SHOULDER,
    RIGHT_WRIST,
    hip_center_y,
    other_wrist,
    shoulder_center_x,
    shoulder_center_y,
    shoulder_width,
    torso_x_range,
)


@dataclass
class Point:
    x: float
    y: float


def _pose(points: dict[int, tuple[float, float]]) -> list[Point]:
    landmarks = [Point(0.5, 0.5) for _ in range(LANDMARK_COUNT)]
    for index, (x, y) in points.items():
        landmarks[index] = Point(x, y)
    return landmarks


def test_other_wrist_swaps_left_and_right():
    assert other_wrist(LEFT_WRIST) == RIGHT_WRIST
    assert other_wrist(RIGHT_WRIST) == LEFT_WRIST


def test_torso_measures():
    landmarks = _pose(
        {
            LEFT_SHOULDER: (0.6, 0.3),
            RIGHT_SHOULDER: (0.4, 0.2),
            LEFT_HIP: (0.7, 0.7),
            RIGHT_HIP: (0.35, 0.8),
        }
    )

    assert shoulder_center_x(landmarks) == (0.6 + 0.4) / 2
    assert shoulder_center_y(landmarks) == (0.3 + 0.2) / 2
    assert hip_center_y(landmarks) == (0.7 + 0.8) / 2
    assert shoulder_width(landmarks) == abs(0.6 - 0.4)
    assert torso_x_range(landmarks) == (0.35, 0.7)
