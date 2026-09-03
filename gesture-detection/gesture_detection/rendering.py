import cv2
import numpy as np
import numpy.typing as npt

from .config import RIGHT_WRIST_INDEX


type Landmark = tuple[float, float, float]
type PixelPoint = tuple[int, int]
type Message = tuple[str, PixelPoint, tuple[int, int, int], float]


def draw_landmarks(
    image: npt.NDArray[np.uint8],
    landmarks: list[Landmark],
    connections: tuple[tuple[int, int], ...],
) -> None:
    height, width, _ = image.shape
    for start_index, end_index in connections:
        if start_index >= len(landmarks) or end_index >= len(landmarks):
            continue
        start_x, start_y, start_visibility = landmarks[start_index]
        end_x, end_y, end_visibility = landmarks[end_index]
        if start_visibility > 0.5 and end_visibility > 0.5:
            cv2.line(
                image,
                (int(start_x * width), int(start_y * height)),
                (int(end_x * width), int(end_y * height)),
                (255, 255, 255),
                2,
            )

    for x, y, visibility in landmarks:
        if visibility > 0.5:
            cv2.circle(image, (int(x * width), int(y * height)), 3, (0, 0, 255), -1)


def right_wrist_pixel(
    landmarks: list[Landmark],
    width: int,
    height: int,
) -> PixelPoint | None:
    if len(landmarks) <= RIGHT_WRIST_INDEX:
        return None
    x, y, visibility = landmarks[RIGHT_WRIST_INDEX]
    if visibility <= 0.5:
        return None
    return int(x * width), int(y * height)


def draw_messages(
    image: npt.NDArray[np.uint8],
    messages: list[Message],
) -> None:
    for text, position, color, scale in messages:
        if text.startswith("Action: "):
            continue
        cv2.putText(
            image,
            text,
            position,
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            max(1, int(scale * 2)),
        )
