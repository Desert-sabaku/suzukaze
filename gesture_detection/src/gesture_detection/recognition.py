"""Temporal recognition and arbitration; independent of camera and MediaPipe."""

from typing import Any

from .config import FPS, RAMUNE_DETECTOR, RAMUNE_LEARNED_MODEL_PATH
from .hand_gesture import HandGestureAnalyzer
from .learned_ramune import LearnedRamuneAnalyzer
from .ramune import RamuneAnalyzer
from .recognition_types import PoseResult
from .relaxing import RelaxingAnalyzer


class RecognitionCoordinator:
    """Own detector lifetimes and resolve recognition conflicts, not scene policy."""

    def __init__(self, *, ramune_detector: str = RAMUNE_DETECTOR, source_fps: float = FPS) -> None:
        if ramune_detector not in {"rules", "learned"}:
            raise ValueError("Unknown Ramune detector")
        self.hands = [HandGestureAnalyzer(15), HandGestureAnalyzer(16)]
        self.ramune = (
            LearnedRamuneAnalyzer(RAMUNE_LEARNED_MODEL_PATH, fps=source_fps)
            if ramune_detector == "learned"
            else RamuneAnalyzer()
        )
        self.learned_mask = (
            self.ramune.metadata["central_mask"]
            if isinstance(self.ramune, LearnedRamuneAnalyzer)
            else None
        )
        self.relaxing = RelaxingAnalyzer()

        self.relaxing_state = False
        self._reset_gesture_state()

    def _reset_gesture_state(self, *, preserve_ramune: bool = False):
        if not preserve_ramune:
            self.ramune.reset()
        for hand in self.hands:
            hand._reset_gesture_state()
        self.selected_action = "NONE"
        self.uchimizu_state = "IDLE"
        self.uchimizu_score = 0.0
        self.fanning_score = 0.0

    def _update_gesture_scores(
        self, landmarks, timestamp: float, *, aspect_ratio: float = 1.0, frame_id: int | None = None
    ) -> None:
        if isinstance(self.ramune, LearnedRamuneAnalyzer):
            opened = self.ramune.update(
                landmarks, timestamp, aspect_ratio=aspect_ratio, frame_id=frame_id
            )
        else:
            opened = self.ramune.update(landmarks, timestamp)
        if opened or self.ramune.state in ("FORMING", "READY"):
            # Keep the press from leaking into the single-hand classifiers.
            for hand in self.hands:
                hand._reset_gesture_state()
            self.selected_action = "RAMUNE" if opened else "NONE"
            self.fanning_score = self.uchimizu_score = 0.0
            self.uchimizu_state = "IDLE"
            return
        for hand in self.hands:
            if landmarks[hand.wrist_index].visibility > 0.5:
                hand._update_gesture_scores(landmarks, timestamp)
            else:
                hand._reset_gesture_state()
        # Preserve the existing priority when hands perform different gestures.
        priority = {"NONE": 0, "FANNING": 1, "UCHIMIZU": 2}
        selected = max(self.hands, key=lambda hand: priority[hand.selected_action])
        self.selected_action = selected.selected_action
        # The other hand can also produce a transient fanning score while one
        # hand prepares/releases water. Apply the same priority at pose level.
        preparing_or_recovering = any(
            hand.uchimizu_state == "READY" or timestamp < hand.fanning_suppressed_until
            for hand in self.hands
        )
        confirmed_fanning = any(
            hand.selected_action == "FANNING" and hand._has_repeated_fanning()
            for hand in self.hands
        )
        if self.selected_action == "FANNING" and preparing_or_recovering and not confirmed_fanning:
            self.selected_action = "NONE"
        self.fanning_score = max(hand.fanning_score for hand in self.hands)
        self.uchimizu_score = max(hand.uchimizu_score for hand in self.hands)
        self.uchimizu_state = max(
            self.hands,
            key=lambda hand: {"IDLE": 0, "READY": 1, "SWING": 2}[hand.uchimizu_state],
        ).uchimizu_state

    def _reset_tracking_state(self, *, preserve_ramune: bool = False):
        self._reset_gesture_state(preserve_ramune=preserve_ramune)
        self.relaxing.reset()
        self.relaxing_state = False

    def process(
        self, landmarks: Any, timestamp: float, frame_id: int, *, aspect_ratio: float
    ) -> PoseResult:
        previous_ramune = self.ramune.state
        previous_water = [hand.uchimizu.completed_at for hand in self.hands]
        if landmarks:
            self._update_gesture_scores(
                landmarks, timestamp, aspect_ratio=aspect_ratio, frame_id=frame_id
            )
            self.relaxing_state = self.relaxing.update(
                landmarks, timestamp, aspect_ratio=aspect_ratio
            )
        else:
            learned = isinstance(self.ramune, LearnedRamuneAnalyzer)
            if isinstance(self.ramune, LearnedRamuneAnalyzer):
                self.ramune.update([], timestamp, aspect_ratio=aspect_ratio, frame_id=frame_id)
            self._reset_tracking_state(preserve_ramune=learned)
        current = self.selected_action
        if current == "NONE" and self.relaxing_state:
            current = "RELAXING"
        occurrences: tuple[str, ...] = ()
        ramune_event = (
            self.ramune.just_opened
            if isinstance(self.ramune, LearnedRamuneAnalyzer)
            else previous_ramune != "OPENED"
        )
        if self.selected_action == "RAMUNE" and ramune_event:
            occurrences = ("RAMUNE",)
        elif self.selected_action == "UCHIMIZU" and any(
            hand.uchimizu.completed_at is not None and hand.uchimizu.completed_at != previous
            for hand, previous in zip(self.hands, previous_water, strict=True)
        ):
            # Simultaneous releases retain the existing single-action policy.
            occurrences = ("UCHIMIZU",)
        return {
            "landmarks": [(p.x, p.y, p.visibility) for p in landmarks],
            "frame_id": frame_id,
            "timestamp": timestamp,
            "current": {"gesture": current, "tracking": bool(landmarks)},
            "occurrences": occurrences,
            "selected_action": self.selected_action,
            "relaxing_state": self.relaxing_state,
            "ramune_state": self.ramune.state,
            "uchimizu_state": self.uchimizu_state,
            "fanning_score": self.fanning_score,
            "uchimizu_score": self.uchimizu_score,
            "motion_speed": self.relaxing.motion_speed,
            "still_seconds": self.relaxing.still_seconds,
        }
