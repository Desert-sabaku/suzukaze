"""Shared recognition vocabulary and valid progress states.

StrEnum keeps diagnostic JSON, annotation labels and IPC values readable.
The bridge maps these names to the enums in proto/gesture/v1/gesture.proto.
"""

from enum import StrEnum


class Gesture(StrEnum):
    NONE = "NONE"
    FANNING = "FANNING"
    RELAXING = "RELAXING"
    BOW = "BOW"
    RAMUNE = "RAMUNE"
    UCHIMIZU = "UCHIMIZU"


class Phase(StrEnum):
    IDLE = "IDLE"
    FORMING = "FORMING"
    READY = "READY"
    OPENED = "OPENED"
    WAIT_RELEASE = "WAIT_RELEASE"
    SWING = "SWING"
    ACTIVE = "ACTIVE"
    HOLD = "HOLD"
    # Annotation-only stages; current detectors do not publish these phases.
    POSITION = "POSITION"
    DWELL = "DWELL"
    BENDING = "BENDING"
    RETURNING = "RETURNING"


CONTINUOUS_GESTURES = frozenset({Gesture.NONE, Gesture.FANNING, Gesture.RELAXING, Gesture.BOW})
OCCURRENCE_GESTURES = frozenset({Gesture.RAMUNE, Gesture.UCHIMIZU})
ACTION_PHASES: dict[str, frozenset[Phase]] = {
    Gesture.RAMUNE: frozenset({Phase.FORMING, Phase.READY, Phase.OPENED, Phase.WAIT_RELEASE}),
    Gesture.UCHIMIZU: frozenset({Phase.READY, Phase.SWING}),
    Gesture.FANNING: frozenset({Phase.ACTIVE}),
    Gesture.RELAXING: frozenset({Phase.ACTIVE}),
    Gesture.BOW: frozenset({Phase.HOLD}),
}


def valid_action_phase(action: str | None, phase: str | None) -> bool:
    return action is not None and phase in ACTION_PHASES.get(action, frozenset())
