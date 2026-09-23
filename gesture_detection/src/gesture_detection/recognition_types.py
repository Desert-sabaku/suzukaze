"""Recognition snapshots and diagnostic data; no scene or device state."""

from typing import NotRequired, TypedDict

type Landmark = tuple[float, float, float]


class RecognitionState(TypedDict):
    """Public current value. NONE with tracking=False means no usable pose."""

    gesture: str
    tracking: bool


class PoseResult(TypedDict):
    """Internal frame result, including diagnostics for local tools.

    External consumers should use current, frame_id and timestamp. The other
    fields retain the existing evaluation interface, not an external protocol.
    Optional fields support the application's initial empty snapshot.
    """

    landmarks: list[Landmark]
    display_landmarks: NotRequired[list[Landmark]]
    selected_action: str
    relaxing_state: bool
    current: NotRequired[RecognitionState]
    # Per-input occurrence pulses; consume before the latest-value IPC queue.
    occurrences: NotRequired[tuple[str, ...]]
    frame_id: NotRequired[int]
    timestamp: NotRequired[float]
    ramune_state: NotRequired[str]
    uchimizu_state: NotRequired[str]
    fanning_score: NotRequired[float]
    uchimizu_score: NotRequired[float]
    motion_speed: NotRequired[float | None]
    still_seconds: NotRequired[float]
