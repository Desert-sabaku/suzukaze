import cv2
import numpy as np
import numpy.typing as npt

from .config import (
    BOW_DWELL_SECONDS,
    BOW_MAX_ANGLE_DEGREES,
    BOW_MAX_HEAD_DEVIATION_DEGREES,
    BOW_MIN_ANGLE_DEGREES,
    RELAXING_DWELL_SECONDS,
    SUBJECT_AREA,
)
from .gesture_types import Phase
from .recognition_types import PoseResult

type Landmark = tuple[float, float, float]
type PixelPoint = tuple[int, int]
type Message = tuple[str, PixelPoint, tuple[int, int, int], float]


def escape_or_closed(window: str, window_created: bool) -> bool:
    """Return true for Escape or a HighGUI window the user has closed."""
    if cv2.waitKey(1) & 0xFF == 27:
        return True
    if not window_created:
        return False
    try:
        return cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1
    except cv2.error:
        # Some HighGUI backends remove the native window before reporting
        # its visibility. Treat the missing-window error as a close event.
        return True


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


def draw_messages(
    image: npt.NDArray[np.uint8],
    messages: list[Message],
) -> None:
    for text, position, color, scale in messages:
        cv2.putText(
            image,
            text,
            position,
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            max(1, int(scale * 2)),
        )


def draw_bow_meter(image: npt.NDArray[np.uint8], result: PoseResult) -> None:
    """Show the measured torso angle, target band and continuous hold progress."""
    height, width = image.shape[:2]
    if height < 270 or width < 220:
        return
    angle = result.get("bow_angle")
    held = result.get("bow_hold_seconds", 0.0)
    valid = (
        angle is not None
        and BOW_MIN_ANGLE_DEGREES <= angle <= BOW_MAX_ANGLE_DEGREES
        and result.get("bow_head_aligned", False)
    )
    color = (0, 220, 0) if valid else (0, 180, 255)
    if angle is None:
        text = "Bow: -- (face, shoulders and hips needed)"
    elif BOW_MIN_ANGLE_DEGREES <= angle <= BOW_MAX_ANGLE_DEGREES and not result.get(
        "bow_head_aligned", False
    ):
        deviation = result.get("bow_head_deviation")
        text = (
            f"Bow: {angle:.0f} deg | head axis {deviation:.0f} deg (max {BOW_MAX_HEAD_DEVIATION_DEGREES:.0f})"
            if deviation is not None
            else f"Bow: {angle:.0f} deg | face forward"
        )
    else:
        text = (
            f"Bow: {angle:.0f} deg (target {BOW_MIN_ANGLE_DEGREES:.0f}-{BOW_MAX_ANGLE_DEGREES:.0f})"
            f" | hold {held:.2f}/{BOW_DWELL_SECONDS:.2f}s"
        )
    cv2.putText(image, text, (10, 225), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
    left, right = 10, min(width - 10, 310)
    span = right - left

    def position(degrees: float) -> int:
        return left + round(span * min(max(degrees, 0), 90) / 90)

    cv2.rectangle(image, (left, 237), (right, 252), (80, 80, 80), 1)
    cv2.rectangle(
        image,
        (position(BOW_MIN_ANGLE_DEGREES), 238),
        (position(BOW_MAX_ANGLE_DEGREES), 251),
        (60, 110, 60),
        -1,
    )
    if angle is not None:
        x = position(angle)
        cv2.line(image, (x, 234), (x, 255), color, 3)
    # The second bar fills only while the bow angle and forward head are held.
    cv2.rectangle(image, (left, 259), (right, 266), (80, 80, 80), 1)
    if valid and held > 0:
        cv2.rectangle(
            image,
            (left, 260),
            (left + round(span * min(held / BOW_DWELL_SECONDS, 1)), 265),
            (0, 220, 0),
            -1,
        )


def draw_ramune_guide(
    image: npt.NDArray[np.uint8],
    state: str,
    *,
    release_message: str = "Ramune: lift the upper hand to try again",
) -> None:
    """Show the next physical action in a compact bottom panel."""
    messages: dict[str, str] = {
        Phase.IDLE: "Ramune: make a ring; place the other hand above",
        Phase.FORMING: "Ramune: hold the lower hand still...",
        Phase.READY: "Ramune: press DOWN with the upper hand!",
        Phase.OPENED: "POP! Ramune opened!",
        Phase.WAIT_RELEASE: release_message,
    }
    height, width = image.shape[:2]
    text = messages.get(state, messages[Phase.IDLE])
    color = (0, 255, 255) if state == Phase.OPENED else (255, 255, 255)
    scale = min(0.6, max(0.1, (width - 20) / 1000))
    cv2.rectangle(image, (0, max(0, height - 44)), (width, height), (35, 35, 35), -1)
    cv2.putText(image, text, (10, height - 16), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1)


def status_messages(result: PoseResult) -> list[Message]:
    """Format diagnostics locally; recognition never constructs overlay text."""
    messages: list[Message] = []
    motion_speed = result.get("motion_speed")
    if motion_speed is not None:
        messages.append((f"Body speed: {motion_speed:.3f}/s", (10, 55), (255, 200, 0), 0.7))
    messages.extend(
        [
            (
                f"Fanning score: {result.get('fanning_score', 0.0):.3f}",
                (10, 80),
                (0, 165, 255),
                0.65,
            ),
            (
                f"Uchimizu score: {result.get('uchimizu_score', 0.0):.3f}",
                (10, 105),
                (255, 100, 100),
                0.65,
            ),
            (
                f"Uchimizu state: {result.get('uchimizu_state', 'IDLE')}",
                (10, 130),
                (255, 100, 100),
                0.65,
            ),
        ]
    )
    messages.append(
        (
            (
                "Relaxing: ON"
                if result.get("relaxing_state", False)
                else f"Relaxing: OFF (still {result.get('still_seconds', 0.0):.1f}/{RELAXING_DWELL_SECONDS:.1f}s)"
            ),
            (10, 155),
            (255, 255, 180),
            0.65,
        )
    )
    return messages


def draw_subject_area(image: npt.NDArray[np.uint8], state: str, *, show_label: bool = True) -> None:
    """Guide torso placement; limbs can extend outside the selection area."""
    height, width = image.shape[:2]
    left, top, right, bottom = SUBJECT_AREA
    color = (80, 180, 80) if state == "TRACKING" else (0, 180, 255)
    cv2.rectangle(
        image,
        (int(left * width), int(top * height)),
        (int(right * width), int(bottom * height)),
        color,
        1,
    )
    if not show_label:
        return
    label = {
        "TRACKING": "Participant tracked",
        "ACQUIRING": "Hold position...",
        "LOST": "Tracking lost",
        "SEARCHING": "Stand in area (torso)",
    }.get(state, "Stand in area (torso)")
    cv2.putText(
        image,
        label,
        (int(left * width), max(20, int(top * height) - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        color,
        1,
    )
