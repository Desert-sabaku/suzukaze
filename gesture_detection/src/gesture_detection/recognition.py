"""Temporal recognition and arbitration; independent of camera and MediaPipe."""

from typing import Any

from .bow import BowAnalyzer
from .config import FPS, RAMUNE_DETECTOR, RAMUNE_LEARNED_MODEL_PATH
from .gesture_types import Gesture, Phase
from .hand_gesture import HandGestureAnalyzer
from .learned_ramune import LearnedRamuneAnalyzer
from .ramune import FollowingRamuneAnalyzer, RamuneAnalyzer
from .recognition_types import OccurrenceEvidence, PoseResult
from .relaxing import RelaxingAnalyzer


class RecognitionCoordinator:
    """Own detector lifetimes and resolve recognition conflicts, not scene policy."""

    def __init__(
        self,
        *,
        ramune_detector: str = RAMUNE_DETECTOR,
        source_fps: float = FPS,
        profile: str = "default",
    ) -> None:
        if ramune_detector not in {"rules", "learned"}:
            raise ValueError("Unknown Ramune detector")
        if profile not in {"default", "multicam"} or (
            profile == "multicam" and ramune_detector != "rules"
        ):
            raise ValueError("The multicam profile requires rule-based recognition")
        self.hands = [
            HandGestureAnalyzer(i, anchored_scoop=profile == "multicam") for i in (15, 16)
        ]
        self.ramune = (
            LearnedRamuneAnalyzer(RAMUNE_LEARNED_MODEL_PATH, fps=source_fps)
            if ramune_detector == "learned"
            else FollowingRamuneAnalyzer()
            if profile == "multicam"
            else RamuneAnalyzer()
        )
        self.learned_mask = (
            self.ramune.metadata["central_mask"]
            if isinstance(self.ramune, LearnedRamuneAnalyzer)
            else None
        )
        self.relaxing = RelaxingAnalyzer()
        self.bow = BowAnalyzer()

        self.relaxing_state = False
        self.bow_state = False
        self._reset_gesture_state()

    def _reset_gesture_state(self, *, preserve_ramune: bool = False):
        if not preserve_ramune:
            self.ramune.reset()
        for hand in self.hands:
            hand._reset_gesture_state()
        self.selected_action = Gesture.NONE
        self.uchimizu_state = Phase.IDLE
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
        if opened or self.ramune.state in (Phase.FORMING, Phase.READY):
            # Keep the press from leaking into the single-hand classifiers.
            for hand in self.hands:
                hand._reset_gesture_state()
            self.selected_action = Gesture.RAMUNE if opened else Gesture.NONE
            self.fanning_score = self.uchimizu_score = 0.0
            self.uchimizu_state = Phase.IDLE
            return
        for hand in self.hands:
            if landmarks[hand.wrist_index].visibility > 0.5:
                hand._update_gesture_scores(landmarks, timestamp)
            else:
                hand._reset_gesture_state()
        # Preserve the existing priority when hands perform different gestures.
        priority = {Gesture.NONE: 0, Gesture.FANNING: 1, Gesture.UCHIMIZU: 2}
        selected = max(self.hands, key=lambda hand: priority[hand.selected_action])
        self.selected_action = selected.selected_action
        # The other hand can also produce a transient fanning score while one
        # hand prepares/releases water. Apply the same priority at pose level.
        preparing_or_recovering = any(
            hand.uchimizu_state == Phase.READY or timestamp < hand.fanning_suppressed_until
            for hand in self.hands
        )
        confirmed_fanning = any(
            hand.selected_action == Gesture.FANNING and hand._has_repeated_fanning()
            for hand in self.hands
        )
        if (
            self.selected_action == Gesture.FANNING
            and preparing_or_recovering
            and not confirmed_fanning
        ):
            self.selected_action = Gesture.NONE
        self.fanning_score = max(hand.fanning_score for hand in self.hands)
        self.uchimizu_score = max(hand.uchimizu_score for hand in self.hands)
        self.uchimizu_state = max(
            self.hands,
            key=lambda hand: {Phase.IDLE: 0, Phase.READY: 1, Phase.SWING: 2}[hand.uchimizu_state],
        ).uchimizu_state

    def _reset_tracking_state(self, *, preserve_ramune: bool = False):
        self._reset_gesture_state(preserve_ramune=preserve_ramune)
        self.relaxing.reset()
        self.relaxing_state = False
        self.bow.reset()
        self.bow_state = False

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
            self.bow_state = self.bow.update(landmarks, timestamp, aspect_ratio)
        else:
            learned = isinstance(self.ramune, LearnedRamuneAnalyzer)
            if isinstance(self.ramune, LearnedRamuneAnalyzer):
                self.ramune.update([], timestamp, aspect_ratio=aspect_ratio, frame_id=frame_id)
            self._reset_tracking_state(preserve_ramune=learned)
        current = self.selected_action
        if current == Gesture.NONE:
            if self.bow_state:
                current = Gesture.BOW
            elif self.relaxing_state:
                current = Gesture.RELAXING
        occurrences: tuple[str, ...] = ()
        evidence: dict[str, OccurrenceEvidence] = {}
        ramune_event = (
            self.ramune.just_opened
            if isinstance(self.ramune, LearnedRamuneAnalyzer)
            else previous_ramune != Phase.OPENED
        )
        if self.selected_action == Gesture.RAMUNE and ramune_event:
            occurrences = (Gesture.RAMUNE,)
            if (
                isinstance(self.ramune, RamuneAnalyzer)
                and self.ramune.base_index is not None
                and self.ramune.setup_started_at is not None
            ):
                evidence[Gesture.RAMUNE] = {
                    "wrist_index": 31 - self.ramune.base_index,
                    "setup_timestamp": self.ramune.setup_started_at,
                }
        elif self.selected_action == Gesture.UCHIMIZU and any(
            hand.uchimizu.completed_at is not None and hand.uchimizu.completed_at != previous
            for hand, previous in zip(self.hands, previous_water, strict=True)
        ):
            # Simultaneous releases retain the existing single-action policy.
            occurrences = (Gesture.UCHIMIZU,)
            for hand, previous in zip(self.hands, previous_water, strict=True):
                if (
                    hand.uchimizu.completed_at is not None
                    and hand.uchimizu.completed_at != previous
                    and hand.uchimizu.setup_started_at is not None
                ):
                    evidence[Gesture.UCHIMIZU] = {
                        "wrist_index": hand.wrist_index,
                        "setup_timestamp": hand.uchimizu.setup_started_at,
                    }
        return {
            "landmarks": [(p.x, p.y, p.visibility) for p in landmarks],
            "frame_id": frame_id,
            "timestamp": timestamp,
            "current": {"gesture": current, "tracking": bool(landmarks)},
            "occurrences": occurrences,
            "occurrence_evidence": evidence,
            "selected_action": self.selected_action,
            "relaxing_state": self.relaxing_state,
            "bow_state": self.bow_state,
            "bow_angle": self.bow.torso_angle,
            "bow_head_deviation": self.bow.head_deviation,
            "bow_head_aligned": self.bow.head_aligned,
            "bow_hold_seconds": self.bow.hold_seconds,
            "ramune_state": self.ramune.state,
            "uchimizu_state": self.uchimizu_state,
            "fanning_score": self.fanning_score,
            "uchimizu_score": self.uchimizu_score,
            "motion_speed": self.relaxing.motion_speed,
            "still_seconds": self.relaxing.still_seconds,
        }
