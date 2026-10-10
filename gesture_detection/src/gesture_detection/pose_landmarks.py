"""Named MediaPipe Pose landmark indices and the torso measures built from them.

Indices follow the 33-point MediaPipe Pose topology. "Left" and "right" are
the subject's, not the image's.
"""

from collections.abc import Sequence
from typing import Protocol

LANDMARK_COUNT = 33

NOSE = 0
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_WRIST = 15
RIGHT_WRIST = 16
LEFT_HIP = 23
RIGHT_HIP = 24

SHOULDERS = (LEFT_SHOULDER, RIGHT_SHOULDER)
WRISTS = (LEFT_WRIST, RIGHT_WRIST)
HIPS = (LEFT_HIP, RIGHT_HIP)
TORSO = (*SHOULDERS, *HIPS)


class LandmarkLike(Protocol):
    x: float
    y: float


type Landmarks = Sequence[LandmarkLike]


def other_wrist(wrist: int) -> int:
    """Return the index of the wrist that is not wrist."""
    return RIGHT_WRIST if wrist == LEFT_WRIST else LEFT_WRIST


def shoulder_center_x(landmarks: Landmarks) -> float:
    return (landmarks[LEFT_SHOULDER].x + landmarks[RIGHT_SHOULDER].x) / 2


def shoulder_center_y(landmarks: Landmarks) -> float:
    return (landmarks[LEFT_SHOULDER].y + landmarks[RIGHT_SHOULDER].y) / 2


def hip_center_x(landmarks: Landmarks) -> float:
    return (landmarks[LEFT_HIP].x + landmarks[RIGHT_HIP].x) / 2


def hip_center_y(landmarks: Landmarks) -> float:
    return (landmarks[LEFT_HIP].y + landmarks[RIGHT_HIP].y) / 2


def shoulder_width(landmarks: Landmarks) -> float:
    """Horizontal shoulder distance in normalized image-width units."""
    return abs(landmarks[LEFT_SHOULDER].x - landmarks[RIGHT_SHOULDER].x)


def torso_x_range(landmarks: Landmarks) -> tuple[float, float]:
    """Leftmost and rightmost x among the shoulders and hips."""
    xs = [landmarks[index].x for index in TORSO]
    return min(xs), max(xs)
