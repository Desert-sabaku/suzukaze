import math

from .config import FANNING_MAX_TORSO_HEIGHT, READY_FACE_EXCLUSION_DISTANCE
from .pose_landmarks import (
    LEFT_HIP,
    LEFT_SHOULDER,
    NOSE,
    RIGHT_HIP,
    RIGHT_SHOULDER,
    RIGHT_WRIST,
    Landmarks,
    hip_center_y,
    shoulder_center_y,
    torso_x_range,
)

type Point = tuple[float, float]


def is_fanning_position(landmarks: Landmarks, wrist_index: int) -> bool:
    """Allow hands beside the chest or face, but exclude a lowered arm."""
    shoulder_y = shoulder_center_y(landmarks)
    torso_height = hip_center_y(landmarks) - shoulder_y
    return (
        torso_height > 1e-6
        and landmarks[wrist_index].y <= shoulder_y + FANNING_MAX_TORSO_HEIGHT * torso_height
    )


def normalized_wrist_distances(
    landmarks: Landmarks, wrist_index: int = RIGHT_WRIST
) -> tuple[float, float]:
    """Wrist distances to the nose and to the torso axis, in shoulder widths."""

    def point(index: int) -> Point:
        return (landmarks[index].x, landmarks[index].y)

    wrist = point(wrist_index)
    nose = point(NOSE)
    left_shoulder = point(LEFT_SHOULDER)
    right_shoulder = point(RIGHT_SHOULDER)
    left_hip = point(LEFT_HIP)
    right_hip = point(RIGHT_HIP)

    shoulder_width = max(math.dist(left_shoulder, right_shoulder), 1e-6)
    shoulder_center = _midpoint(left_shoulder, right_shoulder)
    hip_center = _midpoint(left_hip, right_hip)
    nearest_torso_point = _nearest_point_on_segment(
        wrist,
        shoulder_center,
        hip_center,
    )

    return (
        math.dist(wrist, nose) / shoulder_width,
        math.dist(wrist, nearest_torso_point) / shoulder_width,
    )


def is_wrist_within_torso_x(landmarks: Landmarks, wrist_index: int = RIGHT_WRIST) -> bool:
    left, right = torso_x_range(landmarks)
    return left <= landmarks[wrist_index].x <= right


def is_uchimizu_ready_motion(
    raise_motion: float,
    recent_speed: float,
    face_distance: float,
    wrist_within_torso_x: bool,
) -> bool:
    return (
        raise_motion > 0.04
        and recent_speed > 0.012
        and face_distance >= READY_FACE_EXCLUSION_DISTANCE
        and wrist_within_torso_x
    )


def _midpoint(first: Point, second: Point) -> Point:
    return ((first[0] + second[0]) * 0.5, (first[1] + second[1]) * 0.5)


def _nearest_point_on_segment(point: Point, start: Point, end: Point) -> Point:
    axis = (end[0] - start[0], end[1] - start[1])
    length_squared = axis[0] ** 2 + axis[1] ** 2
    if length_squared <= 1e-12:
        return start

    offset = (point[0] - start[0], point[1] - start[1])
    projection = (offset[0] * axis[0] + offset[1] * axis[1]) / length_squared
    projection = min(1.0, max(0.0, projection))
    return (
        start[0] + projection * axis[0],
        start[1] + projection * axis[1],
    )
