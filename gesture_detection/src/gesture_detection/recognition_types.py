"""Recognition snapshots and diagnostic data; no scene or device state."""

import math
from dataclasses import dataclass
from typing import NotRequired, Self, TypedDict

from .gesture_types import ACTION_PHASES, CONTINUOUS_GESTURES, OCCURRENCE_GESTURES, Gesture, Phase

type Landmark = tuple[float, float, float]
type ContinuousGesture = Gesture | str
type OccurrenceGesture = Gesture | str


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
    booth_present: NotRequired[bool]
    selected_action: str
    relaxing_state: bool
    bow_state: NotRequired[bool]
    bow_angle: NotRequired[float | None]
    bow_head_deviation: NotRequired[float | None]
    bow_head_aligned: NotRequired[bool]
    bow_hold_seconds: NotRequired[float]
    current: NotRequired[RecognitionState]
    # Per-input occurrence pulses; consume before the latest-value IPC queue.
    occurrences: NotRequired[tuple[str, ...]]
    occurrence_evidence: NotRequired[dict[str, OccurrenceEvidence]]
    occurrence_timestamps: NotRequired[dict[str, float]]
    action_accuracy: NotRequired[float | None]
    occurrence_accuracies: NotRequired[dict[str, float | None]]
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
    action: NotRequired[str | None]
    phase: NotRequired[str | None]


def recognition_phase(result: PoseResult) -> tuple[str | None, str | None]:
    """Select detector progress, including preparation before an occurrence.

    The current action wins; otherwise prefer Ramune preparation to Uchimizu.
    Explicit fields carry the selected camera's phase through fusion.
    """
    current = result.get("current", {"gesture": Gesture.NONE, "tracking": False})
    if not current["tracking"]:
        return None, None
    if "action" in result:
        return result.get("action"), result.get("phase")
    action = current["gesture"]
    phases: dict[str, str] = {}
    ramune = result.get("ramune_state", Phase.IDLE)
    water = result.get("uchimizu_state", Phase.IDLE)
    if ramune in ACTION_PHASES[Gesture.RAMUNE]:
        phases[Gesture.RAMUNE] = ramune
    if water in ACTION_PHASES[Gesture.UCHIMIZU]:
        phases[Gesture.UCHIMIZU] = water
    if action in CONTINUOUS_GESTURES - {Gesture.NONE}:
        phases[action] = Phase.HOLD if action == Gesture.BOW else Phase.ACTIVE
    # Holding still after opening is part of Ramune, not a new action.
    if action in phases and not (action == Gesture.RELAXING and Gesture.RAMUNE in phases):
        return action, phases[action]
    for candidate in (Gesture.RAMUNE, Gesture.UCHIMIZU):
        if candidate in phases:
            return candidate, phases[candidate]
    return None, None


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
    action: str | None = None
    phase: str | None = None
    booth_present: bool = False
    action_accuracy: float | None = None
    # Parallel to occurrences, so repeated kinds cannot overwrite a score.
    occurrence_accuracies: tuple[float | None, ...] = ()

    def __post_init__(self) -> None:
        """Normalize string input at the IPC boundary to the shared enums."""
        gesture = Gesture(self.gesture)
        if gesture not in CONTINUOUS_GESTURES:
            raise ValueError("Unknown continuous gesture")
        occurrences = tuple((Gesture(kind), when) for kind, when in self.occurrences)
        if any(kind not in OCCURRENCE_GESTURES for kind, _ in occurrences):
            raise ValueError("Unknown occurrence")
        object.__setattr__(self, "gesture", gesture)
        object.__setattr__(self, "occurrences", occurrences)
        scores = self.occurrence_accuracies or (None,) * len(occurrences)
        if len(scores) != len(occurrences):
            raise ValueError("Occurrence scores must match occurrences")
        for score in (self.action_accuracy, *scores):
            if score is not None and (
                type(score) not in (int, float) or not 0 <= score <= 1 or not math.isfinite(score)
            ):
                raise ValueError("action_accuracy must be finite and in [0, 1]")
        if self.action_accuracy is not None and (not self.tracking or gesture == Gesture.NONE):
            raise ValueError("State accuracy requires a tracked gesture")
        object.__setattr__(self, "occurrence_accuracies", tuple(scores))
        if self.action is not None:
            object.__setattr__(self, "action", Gesture(self.action))
        if self.phase is not None:
            object.__setattr__(self, "phase", Phase(self.phase))

    @classmethod
    def from_result(cls, result: PoseResult, observed_at: float) -> Self:
        """observed_at is capture time, not inference completion or video time."""
        current = result.get("current", {"gesture": Gesture.NONE, "tracking": False})
        action, phase = recognition_phase(result)
        timestamps = result.get("occurrence_timestamps", {})
        occurrences = []
        for name in result.get("occurrences", ()):
            if name not in OCCURRENCE_GESTURES:
                raise ValueError("Unknown occurrence")
            occurrences.append((Gesture(name), timestamps.get(name, observed_at)))
        return cls(
            gesture=Gesture(current["gesture"])
            if current["gesture"] in CONTINUOUS_GESTURES
            else Gesture.NONE,
            tracking=current["tracking"],
            observed_at=observed_at,
            occurrences=tuple(occurrences),
            frame_id=result.get("frame_id"),
            source_timestamp=result.get("timestamp"),
            action=action,
            phase=phase,
            booth_present=result.get("booth_present", False),
            action_accuracy=result.get("action_accuracy")
            if current["tracking"] and current["gesture"] in CONTINUOUS_GESTURES - {Gesture.NONE}
            else None,
            occurrence_accuracies=tuple(
                result.get("occurrence_accuracies", {}).get(name)
                for name in result.get("occurrences", ())
            ),
        )
