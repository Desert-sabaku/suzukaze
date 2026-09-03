import math

from .config import READY_FACE_EXCLUSION_DISTANCE


def normalized_wrist_distances(landmarks):
    wrist = (landmarks[16].x, landmarks[16].y)
    nose = (landmarks[0].x, landmarks[0].y)
    left_shoulder = (landmarks[11].x, landmarks[11].y)
    right_shoulder = (landmarks[12].x, landmarks[12].y)
    left_hip = (landmarks[23].x, landmarks[23].y)
    right_hip = (landmarks[24].x, landmarks[24].y)

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


def is_wrist_within_torso_x(landmarks):
    wrist_x = landmarks[16].x
    torso_x_coordinates = (
        landmarks[11].x,
        landmarks[12].x,
        landmarks[23].x,
        landmarks[24].x,
    )
    return min(torso_x_coordinates) <= wrist_x <= max(torso_x_coordinates)


def is_uchimizu_ready_motion(
    raise_motion,
    recent_speed,
    face_distance,
    wrist_within_torso_x,
):
    return (
        raise_motion > 0.04
        and recent_speed > 0.012
        and face_distance >= READY_FACE_EXCLUSION_DISTANCE
        and wrist_within_torso_x
    )


def _midpoint(first, second):
    return ((first[0] + second[0]) * 0.5, (first[1] + second[1]) * 0.5)


def _nearest_point_on_segment(point, start, end):
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
