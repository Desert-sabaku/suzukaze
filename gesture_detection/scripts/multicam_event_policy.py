"""Research-only evidence and rearming policies for discrete gestures."""

from __future__ import annotations

import math
from collections import Counter, deque

import numpy as np

from gesture_detection import config
from gesture_detection.gesture_position import normalized_wrist_distances
from gesture_detection.uchimizu import UchimizuAnalyzer

EVENT_LABELS = {"UCHIMIZU", "RAMUNE"}
MIN_MOTION_SECONDS = 0.08
NEUTRAL_SECONDS = 0.3


def apply_gesture_policy(metrics: dict) -> dict:
    """State re-detection is permitted; discrete actions require a single event/run."""
    result = dict(metrics)
    result["trials"] = [
        dict(
            t,
            kind="event" if t["label"] in EVENT_LABELS else "state",
            accepted=(
                t["detected"] and t["extra_events"] == 0 and t["output_runs"] == 1
                if t["label"] in EVENT_LABELS
                else t["detected"]
            ),
            penalized_reappearances=t["reappearances"] if t["label"] in EVENT_LABELS else 0,
        )
        for t in metrics["trials"]
    ]
    return result


class AnchoredUchimizu(UchimizuAnalyzer):
    """Require actual image-space rise/drop, in a fixed low-pose torso scale.

    The existing normalized-height detector supplies the candidate. This check
    prevents a moving shoulder/hip estimate alone from forming the scoop.
    """

    audit: Counter = Counter()

    def reset(self) -> None:
        super().reset()
        self.low_positions: deque = deque()
        self.anchor_scale: float | None = None
        self.absolute_peak = 0.0
        self.peak_time = 0.0

    def update(self, landmarks, now: float) -> bool:
        if len(landmarks) < 25:
            self.reset()
            return False
        needed = [landmarks[j] for j in (0, 11, 12, 23, 24, self.wrist_index)]
        if any(
            p.visibility <= 0.5 or not math.isfinite(p.x) or not math.isfinite(p.y) for p in needed
        ):
            self.reset()
            return False
        shoulder_y = (landmarks[11].y + landmarks[12].y) / 2
        scale = (landmarks[23].y + landmarks[24].y) / 2 - shoulder_y
        if scale <= 1e-6:
            self.reset()
            return False
        if (
            self.last_time is not None
            and not 0 < now - self.last_time <= config.UCHIMIZU_MAX_FRAME_GAP
        ):
            self.reset()
        wrist = landmarks[self.wrist_index]
        height = (wrist.y - shoulder_y) / scale
        margin = abs(landmarks[11].x - landmarks[12].x) * config.UCHIMIZU_X_MARGIN
        xs = [landmarks[j].x for j in (11, 12, 23, 24)]
        central = min(xs) - margin <= wrist.x <= max(xs) + margin
        away = (
            normalized_wrist_distances(landmarks, self.wrist_index)[0]
            >= config.READY_FACE_EXCLUSION_DISTANCE
        )
        while (
            self.low_positions
            and now - self.low_positions[0][0] > config.UCHIMIZU_RAISE_WINDOW_SECONDS
        ):
            self.low_positions.popleft()
        before = self.state
        previous_completed = self.completed_at
        history_before = list(self.history)
        if before == "READY" and wrist.y < self.absolute_peak:
            self.absolute_peak, self.peak_time = wrist.y, now
        result = super().update(landmarks, now)
        if self.state == "READY" and before != "READY":
            candidates = [
                (t, y, s)
                for t, y, s in self.low_positions
                if (y - wrist.y) / s >= config.UCHIMIZU_MIN_RAISE and now - t >= MIN_MOTION_SECONDS
            ]
            if not candidates:
                type(self).audit["ready_without_absolute_rise"] += 1
                # Keep observing the same low-to-high movement. Resetting its
                # history here would repeatedly lose legitimate fast-sampled
                # raises before they reach the minimum observed duration.
                self.state = "IDLE"
                self.history.extend(history_before)
                return False
            _, _, self.anchor_scale = max(candidates, key=lambda v: (v[1] - wrist.y) / v[2])
            self.absolute_peak, self.peak_time = wrist.y, now
        if result and self.completed_at != previous_completed:
            if (
                self.anchor_scale is None
                or (wrist.y - self.absolute_peak) / self.anchor_scale < config.UCHIMIZU_MIN_DROP
            ):
                type(self).audit["release_without_absolute_drop"] += 1
                self.reset()
                return False
            if now - self.peak_time < MIN_MOTION_SECONDS:
                type(self).audit["release_too_fast"] += 1
                self.reset()
                return False
            type(self).audit["accepted_release"] += 1
        if self.state == "IDLE" and self.completed_at is None:
            if central and away:
                if height >= config.UCHIMIZU_LOW_HEIGHT:
                    self.low_positions.append((now, wrist.y, scale))
            else:
                self.low_positions.clear()
        return result


def neutral_pose(points: np.ndarray, label: str, event_wrist: int | None = None) -> bool:
    indices = [11, 12, 23, 24] + ([event_wrist] if event_wrist in (15, 16) else [15, 16])
    if not points.any() or (points[indices, 2] <= 0.5).any():
        return False
    selected = points[indices, :2]
    if not np.isfinite(selected).all() or not ((selected >= 0) & (selected <= 1)).all():
        return False
    shoulder = points[[11, 12], 1].mean()
    scale = points[[23, 24], 1].mean() - shoulder
    width = abs(points[11, 0] - points[12, 0])
    if min(scale, width) <= 1e-6:
        return False
    wrists = [event_wrist] if event_wrist in (15, 16) else [15, 16]
    lowered = bool(
        ((points[wrists, 1] - shoulder) / scale >= config.FANNING_EXIT_TORSO_HEIGHT).all()
    )
    if label == "UCHIMIZU":
        return lowered
    separated = (
        (points[[15, 16], 2] > 0.5).all()
        and ((points[[15, 16], :2] >= 0) & (points[[15, 16], :2] <= 1)).all()
        and abs(points[15, 0] - points[16, 0]) / width > 1.0
    )
    return lowered or bool(separated)


class EventLatch:
    """A discrete event requires observed neutral to rearm; missing data cannot.

    Feedback has a fixed bounded duration. State gestures are not latched.
    """

    def __init__(
        self, *, active_hand_release: bool = False, require_new_setup: bool = False
    ) -> None:
        self.active_hand_release = active_hand_release
        self.require_new_setup = require_new_setup
        self.release_observed_at: dict[str, float] = {}
        self.event_wrists: dict[str, int] = {}
        self.locked = set()
        self.neutral_since: dict[str, float] = {}
        self.last_observed: dict[str, float] = {}
        self.feedback_end: dict[str, float] = {}
        self.active: str | None = None
        self.audit = Counter()

    def update(
        self,
        row: dict,
        points: np.ndarray,
        event_wrists: dict[str, int] | None = None,
        *,
        release_views: list[np.ndarray] | None = None,
        event_setups: dict[str, float] | None = None,
    ) -> dict:
        now = row["seconds"]
        for label in tuple(self.locked):
            wrist = self.event_wrists.get(label) if self.active_hand_release else None
            views = release_views if release_views is not None else [points]
            if any(neutral_pose(view, label, wrist) for view in views):
                if label not in self.last_observed or now - self.last_observed[label] > 0.25:
                    self.neutral_since.pop(label, None)
                self.last_observed[label] = now
                self.neutral_since.setdefault(label, now)
                if (
                    now - self.neutral_since[label] + 1e-9 >= NEUTRAL_SECONDS
                    and now >= self.feedback_end[label]
                ):
                    if self.require_new_setup:
                        if label not in self.release_observed_at:
                            self.release_observed_at[label] = now
                            self.audit["release_observed_" + label] += 1
                    else:
                        self.locked.remove(label)
                        self.audit["rearmed_" + label] += 1
                    self.neutral_since.pop(label, None)
            else:
                self.neutral_since.pop(label, None)
                self.last_observed.pop(label, None)
        accepted = []
        for label in row["events"]:
            if (
                self.require_new_setup
                and label in self.locked
                and label in self.release_observed_at
                and event_setups is not None
                and event_setups.get(label, -math.inf) > self.release_observed_at[label]
            ):
                self.locked.remove(label)
                self.audit["rearmed_new_setup_" + label] += 1
            if label not in EVENT_LABELS:
                accepted.append(label)
            elif label in self.locked:
                self.audit["suppressed_" + label] += 1
            else:
                accepted.append(label)
                self.locked.add(label)
                self.release_observed_at.pop(label, None)
                self.neutral_since.pop(label, None)
                self.last_observed.pop(label, None)
                self.feedback_end[label] = now + (
                    config.RAMUNE_HOLD_SECONDS
                    if label == "RAMUNE"
                    else config.UCHIMIZU_FEEDBACK_SECONDS
                )
                self.active = label
                if event_wrists is not None and label in event_wrists:
                    self.event_wrists[label] = event_wrists[label]
        gesture = row["gesture"]
        if self.active is not None and now < self.feedback_end[self.active]:
            gesture = self.active
        elif gesture in EVENT_LABELS:
            # The event pulse owns feedback; a raw hold must not restart it.
            gesture = "NONE"
        return dict(row, gesture=gesture, events=accepted)
