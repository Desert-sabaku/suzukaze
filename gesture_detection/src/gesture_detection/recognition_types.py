"""Recognition snapshots and diagnostic data; no scene or device state."""

from dataclasses import dataclass
from typing import Literal, NotRequired, Self, TypedDict

type Landmark = tuple[float, float, float]
type ContinuousGesture = Literal["NONE", "FANNING", "RELAXING"]
type OccurrenceGesture = Literal["RAMUNE", "UCHIMIZU"]

_CONTINUOUS: dict[str, ContinuousGesture] = {"FANNING": "FANNING", "RELAXING": "RELAXING"}
_OCCURRENCES: dict[str, OccurrenceGesture] = {"RAMUNE": "RAMUNE", "UCHIMIZU": "UCHIMIZU"}


class RecognitionState(TypedDict):
    """Public current value. NONE with tracking=False means no usable pose."""

    gesture: str
    tracking: bool


class OccurrenceEvidence(TypedDict):
    """Source-clock evidence used to identify a new physical preparation."""

    wrist_index: int
    setup_timestamp: float


class PoseResult(TypedDict):
    """Internal frame result, including diagnostics for local tools.

    External consumers should use current, frame_id and timestamp. The other
    fields retain the existing evaluation interface, not an external protocol.
    Optional fields support the application's initial empty snapshot.
    """

    landmarks: list[Landmark]
    display_landmarks: NotRequired[list[Landmark]]
    subject_state: NotRequired[str]
    selected_action: str
    relaxing_state: bool
    current: NotRequired[RecognitionState]
    # Per-input occurrence pulses; consume before the latest-value IPC queue.
    occurrences: NotRequired[tuple[str, ...]]
    occurrence_evidence: NotRequired[dict[str, OccurrenceEvidence]]
    occurrence_timestamps: NotRequired[dict[str, float]]
    observed_at: NotRequired[float]
    locked_events: NotRequired[tuple[str, ...]]
    release_pending: NotRequired[tuple[str, ...]]
    frame_id: NotRequired[int]
    timestamp: NotRequired[float]
    ramune_state: NotRequired[str]
    uchimizu_state: NotRequired[str]
    fanning_score: NotRequired[float]
    uchimizu_score: NotRequired[float]
    motion_speed: NotRequired[float | None]
    still_seconds: NotRequired[float]


@dataclass(frozen=True, slots=True)
class GestureSample:
    """Recognition output sent to unity_bridge. Times are host monotonic seconds."""

    gesture: ContinuousGesture
    tracking: bool
    observed_at: float
    # (kind, occurred_at) for each occurrence pulse in this result.
    occurrences: tuple[tuple[OccurrenceGesture, float], ...]
    frame_id: int | None = None
    source_timestamp: float | None = None

    @classmethod
    def from_result(cls, result: PoseResult, observed_at: float) -> Self:
        """observed_at is capture time, not inference completion or video time."""
        current = result.get("current", {"gesture": "NONE", "tracking": False})
        timestamps = result.get("occurrence_timestamps", {})
        occurrences = []
        for name in result.get("occurrences", ()):
            kind = _OCCURRENCES.get(name)
            if kind is None:
                raise ValueError("Unknown occurrence")
            occurrences.append((kind, timestamps.get(name, observed_at)))
        return cls(
            gesture=_CONTINUOUS.get(current["gesture"], "NONE"),
            tracking=current["tracking"],
            observed_at=observed_at,
            occurrences=tuple(occurrences),
            frame_id=result.get("frame_id"),
            source_timestamp=result.get("timestamp"),
        )
